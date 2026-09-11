"""R1: real PG/API correction commands; login alone uses the existing test fixture."""
from test_finance import identities, client, file_root, order, setup_purchase, get, ok, cmd, version, new_plan, new_cash, alloc, D, uuid4
import pytest

@pytest.mark.parametrize('direction',['receivable','payable'])
def test_original_allowance_recovers_without_commercial_increase(engine,database,identities,direction):
    i=identities
    if direction=='receivable':order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        if direction=='payable':setup_purchase(c,i)
        s=get(c,'sources')[0]
        # Establish a fictional 1000 contract cap BEFORE any plan; never increase it for correction.
        s=ok(cmd(c,'/source-adjustments',{'direction':direction,'source_id':s['id'],'expected_version':s['version'],'amount':str(D('1000')-D(s['amount'])),'basis_ref':'测试原约定1000','reason':'虚构既有商业约定','confirmed':True}))
        p=new_plan(c,s,'1000');p=ok(cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount='-200',basis_ref='误减录入')))
        assert p['effective']=='800.00'
        assert cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount='200',basis_ref='普通加额仍受限')).json()['code']=='FIN_SOURCE_CAP_EXCEEDED'
        original=p['adjustments'][0];key=str(uuid4());body=version(p,adjustment_id=original['id'],basis_ref='撤销误录依据')
        fixed=ok(cmd(c,'/plans/'+p['id']+'/correct-adjustment',body,key))
        assert fixed['effective']=='1000.00' and fixed['adjustment']=='0.00'
        assert fixed['adjustments']==p['adjustments']
        assert fixed['corrections'][0]['adjustment_id']==original['id'] and fixed['corrections'][0]['amount']=='200.00'
        assert ok(cmd(c,'/plans/'+p['id']+'/correct-adjustment',body,key))==fixed
        assert get(c,'sources/'+direction,s['id'])['source']==s
        funds=new_cash(c,s,'1000');ok(alloc(c,funds,(fixed,'1000')))
        assert get(c,'plans',p['id'])['remaining']=='0.00' and get(c,'reconciliation')['matches']

def reduction(c,p,amount='-200'):
    return ok(cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount=amount,basis_ref=str(uuid4()))))

def test_concurrent_correction_unique_and_no_new_allowance(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=reduction(c,new_plan(c,s,'300'));original=p['adjustments'][0]
        extra=ok(cmd(c,'/plans',{'direction':s['direction'],'source_id':s['id'],'node':'不能复用减额','amount':'1','due_date':'2026-01-01'}))
        assert cmd(c,'/plans/'+extra['id']+'/confirm',version(extra)).json()['code']=='FIN_SOURCE_CAP_EXCEEDED'
    gate=Barrier(2);body=version(p,adjustment_id=original['id'],basis_ref='误减更正')
    def worker():
        with client(engine,database,i.user,i.a) as c:
            gate.wait(5);return cmd(c,'/plans/'+p['id']+'/correct-adjustment',body)
    with ThreadPoolExecutor(2) as pool:
        fs=[pool.submit(worker) for _ in range(2)];results=[f.result(timeout=15) for f in fs]
    assert sorted(x.status_code for x in results)==[200,409]
    with client(engine,database,i.user,i.a) as c:
        p=get(c,'plans',p['id']);assert p['effective']=='300.00' and len(p['corrections'])==1
        assert cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=original['id'],basis_ref='重复')).json()['code']=='FIN_ADJUSTMENT_ALREADY_CORRECTED'
        assert cmd(c,'/plans/'+extra['id']+'/confirm',version(extra)).json()['code']=='FIN_SOURCE_CAP_EXCEEDED'
        assert get(c,'reconciliation')['matches']

def test_correction_visibility_permissions_and_foreign_plan(engine,database,identities):
    from sqlalchemy import text
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=reduction(c,new_plan(c,s,'200'),'-100');other=new_plan(c,s,'100');original=p['adjustments'][0]
        path='/plans/'+p['id']+'/correct-adjustment';body=version(p,adjustment_id=original['id'],basis_ref='复核依据');key=str(uuid4())
        assert cmd(c,'/plans/'+other['id']+'/correct-adjustment',version(other,adjustment_id=original['id'],basis_ref='非法跨计划')).status_code==404
        fixed=ok(cmd(c,path,body,key))
        with i.owner.begin() as db:db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='finance.correct'"))
        try:assert cmd(c,path,body,key).status_code==403
        finally:
            with i.owner.begin() as db:db.execute(text("INSERT INTO role_permissions VALUES('admin','finance.correct')"))
        assert ok(cmd(c,path,body,key))==fixed
        c.headers['X-Expected-Tenant']=str(i.b);assert cmd(c,path,body,key).status_code==409
    with client(engine,database,i.other,i.b) as c:
        assert cmd(c,path,body).status_code==404
        setup_purchase(c,i);s=get(c,'sources')[0];pb=new_plan(c,s,'100')
        assert cmd(c,'/plans/'+pb['id']+'/correct-adjustment',version(pb,adjustment_id=original['id'],basis_ref='跨租户原调整')).status_code==404

def test_only_original_negative_full_correction_and_remaining_floor(engine,database,identities):
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=new_plan(c,s,'200');p=ok(cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount='100',basis_ref='普通合法增额')))
        pos=p['adjustments'][0]
        assert cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=pos['id'],basis_ref='不能撤销正调整')).status_code==422
        p=reduction(c,p);original=next(x for x in p['adjustments'] if x['amount']=='-200.00')
        assert cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=original['id'],basis_ref='不能指定金额',amount='999')).status_code==422
        p=ok(cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=original['id'],basis_ref='完整恢复')))
        funds=new_cash(c,s,'300');ok(alloc(c,funds,(p,'300')));p=get(c,'plans',p['id'])
        assert cmd(c,'/plans/'+p['id']+'/adjust',version(p,amount='-1',basis_ref='不可减到已核销以下')).json()['code']=='FIN_DEALLOCATE_FIRST'
        assert get(c,'reconciliation')['matches']

def test_0013_upgrade_preserves_old_adjustment_and_correction_downgrade_blocked(engine,database,identities):
    from conftest import ROOT,run
    import sys,subprocess
    i=identities;order(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        s=get(c,'sources')[0];p=reduction(c,new_plan(c,s,'300'))
        env={**database.env,'DATABASE_URL':database.migration_url}
        run(sys.executable,'infra/migrate.py','downgrade','0013_finance',cwd=ROOT,env=env)
        up=run(sys.executable,'infra/migrate.py','upgrade','head',cwd=ROOT,env=env);assert up.returncode==0,up.stdout+up.stderr
        assert get(c,'plans',p['id'])==p
        fixed=ok(cmd(c,'/plans/'+p['id']+'/correct-adjustment',version(p,adjustment_id=p['adjustments'][0]['id'],basis_ref='迁移后更正')))
        blocked=subprocess.run([sys.executable,'infra/migrate.py','downgrade','0013_finance'],cwd=ROOT,env=env,text=True,capture_output=True)
        assert blocked.returncode!=0 and 'finance history prevents downgrade' in blocked.stderr
        assert get(c,'plans',p['id'])==fixed
