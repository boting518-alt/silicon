"""TASK-013 review regressions: real PG/API; only login fixture replaces OIDC."""
import pytest
from sqlalchemy import text
from test_identity import identities
from test_contracts import client,file_root
from test_inventory import ok
from test_delivery import setup,passing,make_ship,send
from test_analytics import report,metrics,detail,fixture_date

@pytest.mark.parametrize('shipped',[0,1,2])
def test_r1_unauthorized_metadata_never_contains_delivery_counts(engine,database,identities,shipped):
    i=identities;o,loc,ids=setup(engine,database,i,2)
    with client(engine,database,i.user,i.a) as c:
        for id in ids[:shipped]:passing(c,id)
        if shipped:send(c,make_ship(c,o,ids[:shipped]))
        authorized=report(c);m=metrics(authorized)['completion_to_ship']
        assert m['basis']==f'经营样本{shipped}个；未发{2-shipped}个；非财务周转率'
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='delivery.read'"))
        try:
            r=report(c);m=metrics(r)['completion_to_ship']
            assert m['status']=='unauthorized' and m['value'] is None and m['groups']==[]
            assert m['basis']=='需具备来源权限后查看指标口径'
            assert m['reason']=='没有来源数据权限' and not m['drillable']
            assert detail(c,authorized,'completion_to_ship').status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','delivery.read')"))

from test_assembly import order
from test_finance import get,new_cash,new_plan,cmd,version
from test_inventory import setup_purchase
from decimal import Decimal

def refund_at(c,cash,amount,at):
    r=ok(cmd(c,'/refunds',{'cash_id':cash['id'],'amount':amount,'occurred_at':at,'account':'虚构账户','reason':'虚构实退'}))
    return ok(cmd(c,'/refunds/'+r['id']+'/confirm',version(r,cash_version=cash['version'])))

def test_r2_period_flows_independent_of_balance_cutoff(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        setup_purchase(c,i);sources={s['direction']:s for s in get(c,'sources')}
        cashes=[new_cash(c,sources[d],amount,occurred_at='2026-02-10T00:00:00Z') for d,amount in [('receivable','100'),('payable','60')]]
        refunds=[refund_at(c,cash,amount,'2026-02-20T00:00:00Z') for cash,amount in zip(cashes,['20','5'])]
        for x in cashes:fixture_date(i,'analytics_confirmations',x['id'],'confirmed_at','2026-02-11T00:00:00Z')
        for x in refunds:fixture_date(i,'analytics_confirmations',x['id'],'confirmed_at','2026-02-21T00:00:00Z')
        for cutoff,receivable,payable in [('2026-01-31','0.00','0.00'),('2026-02-15','100.00','60.00'),('2026-02-28','80.00','55.00')]:
            r=report(c,start='2026-02-01',end='2026-03-01',as_of=cutoff);m=metrics(r)
            for id,amount in [('receipts','100.00'),('payments','60.00'),('customer_refunds','20.00'),('supplier_refunds','5.00'),('net_cash','25.00')]:
                assert m[id]['value']==amount and m[id]['status']=='complete',(cutoff,id,m[id])
                d=ok(detail(c,r,id));assert sum((Decimal(x['value']) for x in d['items']),Decimal(0))==Decimal(amount)
            assert m['unallocated_receipts']['value']==receivable
            assert m['unallocated_payments']['value']==payable

def reverse_at(c,i,kind,item,date):
    result=ok(cmd(c,'/'+kind+'/'+item['id']+'/reverse',version(get(c,kind,item['id']))))
    column={'cash':'cash_id','refunds':'refund_id'}[kind]
    with i.owner.begin() as db:
        db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
        rid=db.scalar(text(f'SELECT id FROM fin_reversals WHERE {column}=:id'),{'id':item['id']})
    fixture_date(i,'fin_reversals',rid,'created_at',date)
    return result

def test_r2_cross_period_cash_and_refund_reversals_use_their_own_date(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        setup_purchase(c,i);sources={s['direction']:s for s in get(c,'sources')}
        for direction,amount,returned in [('receivable','100','20'),('payable','60','5')]:
            cash=new_cash(c,sources[direction],amount,occurred_at='2026-01-10T00:00:00Z')
            refund=refund_at(c,cash,returned,'2026-01-20T00:00:00Z')
            fixture_date(i,'analytics_confirmations',cash['id'],'confirmed_at','2026-01-11T00:00:00Z')
            fixture_date(i,'analytics_confirmations',refund['id'],'confirmed_at','2026-01-21T00:00:00Z')
            reverse_at(c,i,'refunds',refund,'2026-02-10T00:00:00Z')
            reverse_at(c,i,'cash',cash,'2026-02-11T00:00:00Z')
        for cutoff in ['2026-01-01','2026-01-31','2026-02-28']:
            for start,end,sign in [('2026-01-01','2026-02-01',1),('2026-02-01','2026-03-01',-1)]:
                r=report(c,start=start,end=end,as_of=cutoff);m=metrics(r)
                for id,amount in [('receipts',100),('payments',60),('customer_refunds',20),('supplier_refunds',5),('net_cash',25)]:
                    assert Decimal(m[id]['value'])==amount*sign,(cutoff,id,m[id])
                    assert sum((Decimal(x['value']) for x in ok(detail(c,r,id))['items']),Decimal(0))==amount*sign
        assert metrics(report(c,as_of='2026-01-31'))['unallocated_receipts']['value']=='80.00'
        assert metrics(report(c,as_of='2026-02-28'))['unallocated_receipts']['value']=='0.00'

@pytest.mark.parametrize('missing_kind',['plans','cash','refunds'])
def test_r2_late_registered_or_missing_confirmation_time_does_not_erase_period_flow(engine,database,identities,missing_kind):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'50');cash=new_cash(c,s,'100',occurred_at='2026-01-10T00:00:00Z')
        refund=refund_at(c,cash,'20','2026-01-20T00:00:00Z')
        # These are genuinely confirmed today, with earlier business dates.
        # No confirmation-date backdating is needed for period flow eligibility.
        before=metrics(report(c,start='2026-01-01',end='2026-02-01',as_of='2026-01-31'))
        assert before['net_cash']['value']=='80.00' and before['unallocated_receipts']['value']=='0.00'
        chosen={'plans':p,'cash':cash,'refunds':refund}[missing_kind]
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text('ALTER TABLE analytics_confirmations DISABLE TRIGGER frozen'))
            db.execute(text('DELETE FROM analytics_confirmations WHERE kind=:kind AND id=:id'),{'kind':missing_kind,'id':chosen['id']})
            db.execute(text('ALTER TABLE analytics_confirmations ENABLE TRIGGER frozen'))
        ok(cmd(c,'/cash',{'direction':'receivable','party_id':s['party_id'],'amount':'999','occurred_at':'2026-01-10T00:00:00Z','method':'人工登记','account':'虚构账户','notes':'未确认夹具，不纳入现金流'}))
        r=report(c,start='2026-01-01',end='2026-02-01',as_of='2026-01-31');m=metrics(r)
        for id,amount in [('receipts','100.00'),('customer_refunds','20.00'),('net_cash','80.00')]:
            assert m[id]['value']==amount and m[id]['status']=='complete'
            assert sum((Decimal(x['value']) for x in ok(detail(c,r,id))['items']),Decimal(0))==Decimal(amount)
        assert m['receivables']['status']=='unavailable'  # existing conservative history policy
        assert metrics(report(c))['net_cash']['value']=='80.00'
