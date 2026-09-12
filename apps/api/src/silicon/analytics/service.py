"""Read-only, batch-loaded operating projections; no parallel transaction ledger."""
import hashlib,json
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID
from sqlalchemy import text
from silicon.identity.access import Denied
from .models import Metric,Contribution,AnalyticsGroup,AnalyticsReport
from .regions import REGIONS,normalize,name
from .time import day,today
D=Decimal
TABLES=('crm_customers','signed_contracts','sales_orders','inv_contracts','inv_suppliers',
'inv_movements','inv_entries','inv_layers','inv_lots','inv_units','inv_locations','catalog_skus',
'asm_completions','asm_devices','asm_works','del_lines','del_shipments','del_returns','del_reversals',
'fin_plans','fin_cash','fin_refunds','fin_adjustments','fin_adjustment_corrections','fin_allocations','fin_reversals','fin_releases','analytics_confirmations',
'svc_events','svc_works','svc_receipts','svc_returns','svc_rmas','svc_rma_lines','svc_old_parts','svc_rma_returns','svc_rma_inspections','svc_dispositions','svc_charges')

def sid(value):return str(value) if value is not None else None
def money(value):return format(D(value),'.2f')
def grouped(values,key):
    result=defaultdict(list)
    for x in values:result[x[key]].append(x)
    return result

class Projection:
    def __init__(self,db,a,f):
        self.a,self.f=a,f;self.metrics=[];self.details={}
        # Fixed bounded set of bulk queries, never queries per customer/stock layer.
        self.tables={}
        for table in TABLES:
            if (table.startswith('fin_') or table=='analytics_confirmations') and 'finance.read' not in a.permissions:
                self.tables[table]=[];continue
            rows=[dict(x) for x in db.execute(text(f'SELECT * FROM {table} WHERE tenant_id=:tenant LIMIT 100001'),{'tenant':a.tenant_id}).mappings()]
            if len(rows)>100000:raise Denied(413,'ANALYTICS_DATA_LIMIT')
            self.tables[table]=rows
        self.index={t:{sid(x['id']):x for x in xs if 'id' in x} for t,xs in self.tables.items()}
        self.customers={k:v for k,v in self.index['crm_customers'].items() if a.owns(v['owner_id'])}
        if f.customer_id and str(f.customer_id) not in self.customers:raise Denied(404,'NOT_FOUND')
        if f.region and f.region not in {r['code'] for r in REGIONS}:raise Denied(422,'ANALYTICS_REGION_INVALID')
        self.customer_filter=bool(f.customer_id or f.region)
        self.orders={k:v for k,v in self.index['sales_orders'].items() if self.customer(v['content']['commercial']['config']['customer_id'])}
        self.confirmed={(x['kind'],sid(x['id'])):day(x['confirmed_at']) for x in self.tables['analytics_confirmations']}
    def rows(self,t):return self.tables[t]
    def obj(self,t,id):return self.index[t].get(sid(id))
    def customer(self,id):
        c=self.customers.get(sid(id))
        return c if c and (not self.f.customer_id or sid(id)==str(self.f.customer_id)) and (not self.f.region or normalize(c['province'])==self.f.region) else None
    def period(self,date):return self.f.start<=day(date)<self.f.end
    def cutoff(self,date):return day(date)<=self.f.as_of
    def contribution(self,id,label,value,date=None,customer=None,group='',note='',target=None):
        c=self.customers.get(sid(customer),{})
        return Contribution(id=str(id),label=label,value=str(value),date=day(date) if date else None,customer_id=sid(customer),region=normalize(c.get('province')),group=group,note=note,target=target)
    def metric(self,id,label,unit,permission,rows=(),*,basis='',status='complete',reason='',value=None,group='group',unsupported=False):
        allowed=all(p in self.a.permissions for p in permission.split('+'))
        xs=list(rows) if allowed else []
        if not allowed:
            status='unauthorized';reason='没有来源数据权限'
            # Metadata is an output channel too: dynamic sample explanations
            # must not disclose facts when the source permission is missing.
            basis='需具备来源权限后查看指标口径'
        elif unsupported:status='not_applicable';reason=reason or '当前筛选或负责人范围不适用于此来源';xs=[]
        if status in ('unauthorized','not_applicable','unavailable'):val=None;xs=[]
        else:
            n=sum((D(x.value) for x in xs),D(0)) if value is None else D(value)
            val=money(n) if unit in ('CNY','天','%') else str(n)
        buckets=defaultdict(list)
        for x in xs:
            if unit not in ('%','天'):buckets[getattr(x,group)].append(x)
        gs=[AnalyticsGroup(key=k,label=name(k) if group=='region' else k or '未分类',value=money(sum((D(x.value) for x in v),D(0))) if unit=='CNY' else str(sum((D(x.value) for x in v),D(0))),count=len(v)) for k,v in sorted(buckets.items())]
        if id in ('customer_rank','customer_receivable_rank'):
            for g in gs:g.label=self.customers[g.key]['name']+' · '+self.customers[g.key]['number']
        if id.endswith('_rank'):gs.sort(key=lambda g:(-D(g.value),g.key))
        m=Metric(id=id,name=label,unit=unit,value=val,status=status,reason=reason,basis=basis or label,start=self.f.start,end=self.f.end,as_of=self.f.as_of,drillable=allowed and bool(xs),groups=gs)
        self.metrics.append(m);self.details[id]=xs
        return m
    def sales(self):
        all_contracts=[]
        for s in self.rows('signed_contracts'):
            content=s['content'];commercial=content['commercial'];cid=commercial['config']['customer_id'];c=self.customer(cid)
            if not c:continue
            date=day(content['fields'].get('signing_date') or s['registered_at'])
            amount=commercial['calculation']['total']
            all_contracts.append((s,cid,date,amount))
        contracts=[self.contribution(s['id'],s['number'],amount,date,cid,note='冻结商业总额，按当前客户地区',target={'kind':'contract','id':sid(s['contract_id'])}) for s,cid,date,amount in all_contracts if self.period(date)]
        self.metric('contracts','本期签约金额','CNY','contract.read',contracts,basis='冻结签约商业金额；不含自动税费换算；签订日期；地区按当前客户资料',group='region')
        self.metric('contract_count','本期签约合同','份','contract.read',[x.model_copy(update={'value':'1'}) for x in contracts])
        self.metric('customer_distribution','当前客户地区分布','家','crm.read',[self.contribution(k,c['name'],1,customer=k,target={'kind':'customer','id':k}) for k,c in self.customers.items() if self.customer(k)],basis='当前客户明确省份字段，不是历史分布',group='region')
        first={}
        for _,cid,date,_ in all_contracts:first[sid(cid)]=min(date,first.get(sid(cid),date))
        customer_totals=defaultdict(lambda:D(0))
        for x in contracts:customer_totals[x.customer_id]+=D(x.value)
        rank=[self.contribution(k,self.customers[k]['name'],v,customer=k,group=k,target={'kind':'customer','id':k} if 'crm.read' in self.a.permissions else None) for k,v in customer_totals.items()]
        self.metric('customer_rank','客户签约排行','CNY','contract.read',rank)
        self.metric('business_customers','本期有签约客户','家','contract.read',[x.model_copy(update={'value':'1'}) for x in rank])
        self.metric('new_customers','本期新增成交客户','家','contract.read',[x.model_copy(update={'value':'1'}) for x in rank if self.period(first[x.id])])
        total=sum(customer_totals.values(),D(0));top=sum(sorted(customer_totals.values(),reverse=True)[:self.f.top_n],D(0))
        self.metric('concentration',f'前{self.f.top_n}客户签约集中度','%','contract.read',rank,value=(top/total*100).quantize(D('.01'),rounding=ROUND_HALF_UP) if total else None,status='complete' if total else 'unavailable',reason='' if total else '期间签约额为零',basis='前N客户签约额 / 期间签约额；明细列出各客户原金额')
        for id,label,selector in [('product_rank','冻结主机产品签约结构',lambda s:s['content']['commercial']['host'].get('name','未知产品')),('brand_rank','冻结销售品牌签约结构',lambda s:str(s['content']['commercial']['host'].get('brand') or '品牌未配置')),('manager_rank','冻结销售负责人签约结构',lambda s:s['content']['fields'].get('sales',{}).get('name') or '负责人未配置')]:
            facts=[self.contribution(s['id'],s['number'],amount,date,cid,selector(s),target={'kind':'contract','id':sid(s['contract_id'])}) for s,cid,date,amount in all_contracts if self.period(date)]
            self.metric(id,label,'CNY','contract.read',facts,basis='按每份合同冻结主机/负责人归组一次，不按部件重复金额')
    def delivery(self):
        shipped=[];returned=[];net_by_order=defaultdict(int);first_ship={}
        reversals={sid(x['shipment_id']):x for x in self.rows('del_reversals')}
        for l in self.rows('del_lines'):
            order=self.orders.get(sid(l['order_id']));m=self.obj('inv_movements',l['movement_id'])
            if not order or not m:continue
            cid=order['content']['commercial']['config']['customer_id'];target={'kind':'shipment','id':sid(l['shipment_id'])}
            original=self.contribution(l['id'],order['number'],1,m['effective_on'],cid,target=target)
            if self.period(original.date):shipped.append(original)
            reverse=reversals.get(sid(l['shipment_id']))
            if self.cutoff(original.date):
                net_by_order[sid(order['id'])]+=1
                if not reverse or not self.cutoff(self.obj('inv_movements',reverse['movement_id'])['effective_on']):first_ship[sid(l['completion_id'])]=min(original.date,first_ship.get(sid(l['completion_id']),original.date))
            if reverse:
                date=self.obj('inv_movements',reverse['movement_id'])['effective_on']
                if self.period(date):shipped.append(original.model_copy(update={'id':str(reverse['id'])+':'+str(l['id']),'date':date,'value':'-1','note':'误操作冲销，归属逆向日期'}))
                if self.cutoff(date):net_by_order[sid(order['id'])]-=1
        for r in self.rows('del_returns'):
            l=self.obj('del_lines',r['line_id']);o=self.orders.get(sid(l['order_id']))
            if not o:continue
            date=self.obj('inv_movements',r['movement_id'])['effective_on']
            if self.period(date):returned.append(self.contribution(r['id'],o['number'],1,date,o['content']['commercial']['config']['customer_id'],target={'kind':'shipment','id':sid(l['shipment_id'])}))
            if self.cutoff(date):net_by_order[sid(o['id'])]-=1
        for id,label,xs in [('dispatched','本期发出（扣误冲销）',shipped),('returned','本期实际退回',returned),('net_delivery','本期净交付',[*shipped,*[x.model_copy(update={'value':str(-D(x.value))}) for x in returned]])]:self.metric(id,label,'台','delivery.read',xs,basis='库存移动经营日期；按当前客户地区，不是历史收货省份',group='region')
        delayed=[]
        for o in self.orders.values():
            s=self.obj('signed_contracts',o['contract_version_id']);date=day(s['content']['fields'].get('signing_date') or s['registered_at']);left=o['content']['commercial']['config']['quantity']-net_by_order[sid(o['id'])]
            if self.cutoff(date) and (self.f.as_of-date).days>=self.f.overdue_days and left>0:delayed.append(self.contribution(o['id'],o['number'],left,date,o['content']['commercial']['config']['customer_id'],target={'kind':'order','id':sid(o['id'])} if 'contract.read' in self.a.permissions else None))
        self.metric('overdue_orders','长期待履约设备','台','delivery.read',delayed,basis=f'距签约至少{self.f.overdue_days}天且尚未净交付')
        samples=[];waiting=[]
        for comp in self.rows('asm_completions'):
            work=self.obj('asm_works',comp['work_id']);o=self.orders.get(sid(work['order_id']))
            if not o:continue
            m=self.obj('inv_movements',comp['movement_id']);date=m['effective_on']
            if not self.cutoff(date):continue
            rev=self.obj('inv_movements',comp.get('reversed_by'))
            if rev and self.cutoff(rev['effective_on']):continue
            sent=first_ship.get(sid(comp['id']));cid=o['content']['commercial']['config']['customer_id']
            if sent and self.period(sent) and sent>=date:samples.append(self.contribution(comp['id'],o['number'],(sent-date).days,sent,cid,target={'kind':'order','id':sid(o['id'])} if 'contract.read' in self.a.permissions else None))
            elif not sent:waiting.append(self.contribution(comp['id'],o['number'],1,date,cid,target={'kind':'order','id':sid(o['id'])} if 'contract.read' in self.a.permissions else None))
        mean=(sum((D(x.value) for x in samples),D(0))/len(samples)).quantize(D('.01')) if samples else None
        self.metric('completion_to_ship','完工至首次发货平均天数','天','delivery.read',samples,value=mean,status='complete' if samples else 'unavailable',reason='' if samples else '没有期间内已发的完整样本',basis=f'经营样本{len(samples)}个；未发{len(waiting)}个；非财务周转率')
        self.metric('unshipped_completions','完工尚未发货样本','台','delivery.read',waiting)
    def finance(self):
        managed_suppliers={sid(x['supplier_id']) for t in ('inv_contracts','svc_rmas') for x in self.rows(t) if self.a.owns(x['manager_id'])}
        def party(direction,id):
            if direction=='receivable':return self.customer(id)
            if self.customer_filter:return None
            p=self.obj('inv_suppliers',id)
            return p if p and (self.a.data_scope=='all' or sid(id) in managed_suppliers) else None
        def visible_plan(p):
            if not party(p['direction'],p['party_id']):return False
            if p['direction']=='receivable':return True
            if p.get('purchase_contract_id'):
                s=self.obj('inv_contracts',p['purchase_contract_id']);return s['state']=='active' and self.a.owns(s['manager_id'])
            charge=self.obj('svc_charges',p.get('service_source_id'))
            return bool(charge and self.a.owns(self.obj('svc_rmas',charge['rma_id'])['manager_id']))
        plans={sid(p['id']):p for p in self.rows('fin_plans') if visible_plan(p)}
        allocations=grouped(self.rows('fin_allocations'),'cash_id')
        cash={sid(c['id']):c for c in self.rows('fin_cash') if party(c['direction'],c['party_id']) and all(sid(x['plan_id']) in plans for x in allocations[c['id']])}
        refunds=[r for r in self.rows('fin_refunds') if sid(r['cash_id']) in cash]
        missing=any(x['state']=='confirmed' and (kind,sid(x['id'])) not in self.confirmed for kind,xs in [('plans',plans.values()),('cash',cash.values()),('refunds',refunds)] for x in xs)
        uncertain=missing and self.f.as_of<today()
        status='unavailable' if uncertain else 'partial' if missing else 'complete'
        reason='旧记录缺少可靠确认时间，无法重建该历史截止日' if uncertain else '部分旧记录无确认时间；仅按当前已确认状态统计' if missing else ''
        def confirmed(kind,x):
            at=self.confirmed.get((kind,sid(x['id'])))
            return x['state']=='confirmed' and (self.cutoff(at) if at else self.f.as_of==today())
        reversals={}
        for r in self.rows('fin_reversals'):
            for kind in ('allocation','cash','refund'):
                if r.get(kind+'_id'):reversals[kind,sid(r[kind+'_id'])]=r
        def reversed_at(kind,id):
            r=reversals.get((kind,sid(id)));return bool(r and self.cutoff(r['created_at']))
        used=defaultdict(lambda:D(0));used_cash=defaultdict(lambda:D(0))
        for x in self.rows('fin_allocations'):
            if self.cutoff(x['created_at']) and not reversed_at('allocation',x['id']):used[sid(x['plan_id'])]+=x['amount'];used_cash[sid(x['cash_id'])]+=x['amount']
        adjustments=defaultdict(lambda:D(0))
        for x in self.rows('fin_adjustments'):
            if self.cutoff(x['created_at']):adjustments[sid(x['plan_id'])]+=x['amount']
        for x in self.rows('fin_adjustment_corrections'):
            if self.cutoff(x['created_at']):adjustments[sid(x['plan_id'])]-=self.obj('fin_adjustments',x['adjustment_id'])['amount']
        releases={sid(x['plan_id']):x for x in self.rows('fin_releases') if self.cutoff(x['created_at'])}
        balances={'receivable':[],'payable':[]};overdue=[];due=[]
        for p in plans.values():
            if not confirmed('plans',p):continue
            left=p['amount']+adjustments[sid(p['id'])]-used[sid(p['id'])]
            cid=p['party_id'] if p['direction']=='receivable' else None
            r=releases.get(sid(p['id']));date=r['due_date'] if r else p['due_date'] if not p['retention'] and not p['release_condition'] else None
            x=self.contribution(p['id'],p['node'],left,date,cid,group=('待释放/到期日未知' if not date else '未到期' if date>=self.f.as_of else next(label for bound,label in [(30,'逾期1–30天'),(60,'逾期31–60天'),(90,'逾期61–90天'),(1000000,'逾期90天以上')] if (self.f.as_of-date).days<=bound)),note='已确认计划＋调整及更正－有效核销；不是现金流',target={'kind':'finance','id':'plans/'+sid(p['id'])})
            if left:balances[p['direction']].append(x)
            if left>0 and date:
                if p['direction']=='receivable' and date<self.f.as_of:overdue.append(x)
                if p['direction']=='payable' and self.f.as_of<=date<=self.f.as_of+timedelta(days=self.f.due_days):due.append(x)
        for id,label,rows in [('receivables','应收未核销',balances['receivable']),('payables','应付未核销',balances['payable']),('overdue_receivables','逾期应收',overdue),('due_payables','即将到期应付',due)]:
            self.metric(id,label,'CNY','finance.read',rows,status=status,reason=reason,unsupported=self.customer_filter and id in ('payables','due_payables'),basis='截止日计划余额；依实际确认、调整、核销及逆向时间',group='region' if id in ('receivables','overdue_receivables') else 'group')
        for direction,label in [('receivable','应收'),('payable','应付')]:self.metric(direction+'_age',label+'账龄','CNY','finance.read',balances[direction],status=status,reason=reason,unsupported=self.customer_filter and direction=='payable',basis='按有效到期日与截止日；未释放或无日期单列')
        self.metric('customer_receivable_rank','客户应收余额排行','CNY','finance.read',[x.model_copy(update={'group':x.customer_id}) for x in balances['receivable']],status=status,reason=reason)
        flows={k:[] for k in ('receipts','payments','customer_refunds','supplier_refunds')};available=defaultdict(list);refunded=defaultdict(lambda:D(0))
        def flow(kind,x,metric,cid,label,target):
            # Period flows use facts known to be confirmed at query time.
            # Confirmation chronology is needed for historical balances only;
            # a late-entered fact retains its recorded business occurrence date.
            if x['state']!='confirmed':return
            if self.period(x['occurred_at']):flows[metric].append(self.contribution(x['id'],label,x['amount'],x['occurred_at'],cid,target=target))
            r=reversals.get((kind,sid(x['id'])))
            if r and self.period(r['created_at']):flows[metric].append(self.contribution(r['id'],label,-x['amount'],r['created_at'],cid,note='逆向事实归属逆向登记日',target=target))
        for r in refunds:
            c=cash[sid(r['cash_id'])];cid=c['party_id'] if c['direction']=='receivable' else None
            flow('refund',r,'customer_refunds' if cid else 'supplier_refunds',cid,'退款',{'kind':'finance','id':'refunds/'+sid(r['id'])})
            if confirmed('refunds',r) and self.cutoff(r['occurred_at']) and not reversed_at('refund',r['id']):refunded[sid(c['id'])]+=r['amount']
        for c in cash.values():
            cid=c['party_id'] if c['direction']=='receivable' else None;target={'kind':'finance','id':'cash/'+sid(c['id'])}
            flow('cash',c,'receipts' if cid else 'payments',cid,'收付款 '+sid(c['id'])[:8],target)
            if confirmed('cash',c) and self.cutoff(c['occurred_at']) and not reversed_at('cash',c['id']):
                left=c['amount']-used_cash[sid(c['id'])]-refunded[sid(c['id'])]
                if left:available[(c['purpose'],c['direction'])].append(self.contribution(c['id'],'收付款 '+sid(c['id'])[:8],left,c['occurred_at'],cid,target=target))
        for id,label in [('receipts','本期实际收款'),('payments','本期实际付款'),('customer_refunds','本期客户退款'),('supplier_refunds','本期供应商退款')]:self.metric(id,label,'CNY','finance.read',flows[id],unsupported=self.customer_filter and id in ('payments','supplier_refunds'),basis='按查询时已确认事实的发生日；冲销按逆向登记日；余额截止日不截断期间流量；核销不产生现金流',group='region')
        net=[x.model_copy(update={'id':key+':'+x.id,'value':str(D(x.value)*sign)}) for key,sign in [('receipts',1),('payments',-1),('customer_refunds',-1),('supplier_refunds',1)] for x in flows[key]]
        self.metric('net_cash','本期经营净现金流','CNY','finance.read',net,unsupported=self.customer_filter,basis='期间实际收款－付款－客户退款＋供应商退款；余额截止日不截断期间流量；不等同利润')
        for purpose,prefix in [('advance','advance'),('unallocated','unallocated')]:
            for direction,suffix,label in [('receivable','receipts','收款'),('payable','payments','付款')]:self.metric(prefix+'_'+suffix,('预' if purpose=='advance' else '未分配')+label+'余额','CNY','finance.read',available[(purpose,direction)],status=status,reason=reason,unsupported=self.customer_filter and direction=='payable')

    def inventory(self):
        quantities=defaultdict(int)
        for e in self.rows('inv_entries'):
            if self.cutoff(self.obj('inv_movements',e['movement_id'])['effective_on']):quantities[(sid(e['layer_id']),sid(e['location_id']),e['state'])]+=e['quantity']
        self.stock=quantities
        known=[];unknown=[];quantity=[];old=[];age=[];custody=[];structure=[]
        completed={sid(c['layer_id']) for c in self.rows('asm_completions')}
        last_return={}
        for r in self.rows('del_returns'):
            date=self.obj('inv_movements',r['movement_id'])['effective_on'];lid=sid(self.obj('del_lines',r['line_id'])['layer_id'])
            if self.cutoff(date):last_return[lid]=max(date,last_return.get(lid,date))
        for (lid,location,state),qty in quantities.items():
            if qty<=0:continue
            layer=self.obj('inv_layers',lid)
            if layer['ownership']!='own':
                custody.append(self.contribution(lid+':'+location+':'+state,'客户所有库存',qty,group=state,target={'kind':'inventory','id':lid}))
                continue
            sku=self.obj('catalog_skus',layer['sku_id']);date=self.obj('inv_movements',layer['source_movement'])['effective_on']
            # WIP is a stage, not a second asset. Supplier/service-issued own goods remain stock assets.
            stage='在制' if state=='wip' else '成品' if lid in completed else '零件/商品'
            label=sku['name']+' · '+self.obj('inv_locations',location)['name']+' · '+state
            x=self.contribution(lid+':'+location+':'+state,label,qty,date,group=stage,note=f'原成本层账龄{(self.f.as_of-date).days}天；数量单位按SKU，不作等价台数',target={'kind':'inventory','id':lid})
            quantity.append(x)
            if lid in last_return:x.note+=f'；最近销售退回{last_return[lid]}，本次重新在库{(self.f.as_of-last_return[lid]).days}天'
            structure.append(x.model_copy(update={'group':stage+' · '+state}))
            age.append(x.model_copy(update={'group':next(label for bound,label in [(30,'0–30天'),(60,'31–60天'),(90,'61–90天'),(180,'91–180天'),(1000000,'180天以上')] if (self.f.as_of-date).days<=bound)}))
            if layer['unit_cost'] is None:unknown.append(x)
            else:known.append(x.model_copy(update={'value':money(layer['unit_cost']*qty)}))
            if (self.f.as_of-date).days>=self.f.old_stock_days:old.append(x)
        unsupported=self.customer_filter or self.a.data_scope!='all'
        self.metric('inventory_quantity','自有库存数量','件','inventory.read',quantity,unsupported=unsupported,basis='截止日移动台账；含零件/在制/成品，排除客户代管；不同SKU件数不是产能')
        self.metric('inventory_age_bands','自有库存库龄分档','件','inventory.read',age,unsupported=unsupported,basis='原成本层经营日期至截止日；移库不重置；成品从完工入账起算')
        self.metric('inventory_structure','自有库存阶段与质量','件','inventory.read',structure,unsupported=unsupported)
        self.metric('customer_custody','客户所有库存（不计自有成本）','件','inventory.read',custody,unsupported=unsupported)
        self.metric('inventory_known_cost','已知自有库存成本','CNY','inventory.read+inventory.cost',known,unsupported=unsupported,status='partial' if unknown else 'complete',reason='存在未知成本层，金额仅为已知成本部分' if unknown else '',basis='原成本层单价×截止日数量；零件、在制和成品不重复')
        self.metric('inventory_unknown','未知成本库存数量','件','inventory.read+inventory.cost',unknown,unsupported=unsupported)
        self.metric('inventory_age','长期库存数量','件','inventory.read',old,unsupported=unsupported,basis=f'原成本层入账日起至少{self.f.old_stock_days}天；不是标准周转天数')
        for id in ('DIO','DSO','DPO','CCC'):self.metric(id,id+' 标准财务指标','天','finance.read+inventory.cost',status='unavailable',reason='未实现会计销售收入、销货成本期间确认及可靠每日平均余额；不以期末余额替代',basis='暂不可计算')
    def service(self):
        held=[];outside=[];overdue=[];unhandled=[]
        returns={sid(r['receipt_id']) for r in self.rows('svc_returns') if self.cutoff(r['performed_at'])}
        def work_customer(w):
            l=self.obj('del_lines',w['line_id']);o=self.orders.get(sid(l['order_id']))
            return o['content']['commercial']['config']['customer_id'] if o else None
        works={sid(w['id']):w for w in self.rows('svc_works') if work_customer(w)}
        for r in self.rows('svc_receipts'):
            w=works.get(sid(r['work_id']))
            if w and self.cutoff(r['performed_at']) and sid(r['id']) not in returns:held.append(self.contribution(r['id'],w['number'],1,r['performed_at'],work_customer(w),target={'kind':'service','id':sid(w['id'])}))
        sent={sid(e['details'].get('rma_id')):self.obj('inv_movements',e['details'].get('movement_id')) for e in self.rows('svc_events') if e['action']=='rma.sent'}
        rma_returned=defaultdict(int)
        for x in self.rows('svc_rma_returns'):
            if self.cutoff(self.obj('inv_movements',x['movement_id'])['effective_on']):rma_returned[x['line_id']]+=x['quantity']
        for l in self.rows('svc_rma_lines'):
            r=self.obj('svc_rmas',l['rma_id']);w=works.get(sid(r['work_id']));movement=sent.get(sid(r['id']))
            if not w or not movement or not self.cutoff(movement['effective_on']):continue
            returned=rma_returned[l['id']]
            qty=l['quantity']-returned
            if qty>0:
                x=self.contribution(l['id'],r['number'],qty,r['expected_on'],work_customer(w),target={'kind':'service','id':sid(w['id'])});outside.append(x)
                if r['expected_on']<self.f.as_of:overdue.append(x)
        inspected={sid(x['return_id']) for x in self.rows('svc_rma_inspections') if self.cutoff(self.obj('inv_movements',x['movement_id'])['effective_on']) and x['disposition']!='hold'}
        disposed={sid(x['return_id']) for x in self.rows('svc_dispositions') if x['return_id'] and self.cutoff(self.obj('inv_movements',x['movement_id'])['effective_on'])}
        for r in self.rows('svc_rma_returns'):
            l=self.obj('svc_rma_lines',r['line_id']);parent=self.obj('svc_rmas',l['rma_id']);w=works.get(sid(parent['work_id']))
            if w and self.cutoff(self.obj('inv_movements',r['movement_id'])['effective_on']) and sid(r['id']) not in inspected|disposed:unhandled.append(self.contribution(r['id'],parent['number'],r['quantity'],r['performed_at'],work_customer(w),target={'kind':'service','id':sid(w['id'])}))
        for id,label,xs in [('held_devices','售后在手客户设备',held),('rma_outside','供应商RMA在外数量',outside),('rma_overdue','供应商RMA逾期未回',overdue),('rma_held','RMA返还待检/未处置',unhandled)]:self.metric(id,label,'件','service.read',xs,basis='截至日收交/移动事实；不计入自有库存成本',group='region')
    def report(self):
        self.sales();self.delivery();self.finance();self.inventory();self.service()
        # Hash only authorized response facts, stable irrespective of SQL row order.
        canonical={'filters':self.f.model_dump(mode='json'),'permissions':sorted(self.a.permissions),'scope':self.a.data_scope,'metrics':[m.model_dump(mode='json') for m in self.metrics],'details':{k:sorted([x.model_dump(mode='json') for x in xs],key=lambda x:x['id']) for k,xs in self.details.items()}}
        snapshot=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        return AnalyticsReport(customers=[{'id':k,'name':c['name']} for k,c in self.customers.items()] if 'crm.read' in self.a.permissions else [],snapshot=snapshot,calculated_at=datetime.now(timezone.utc),filters=self.f,metrics=self.metrics,regions=REGIONS,scope_note='Asia/Shanghai 自然日；期间左闭右开。按查询时已知事实重建经营日期；负责人和客户地区按当前资料。无权限和缺失资料不记作零。')
