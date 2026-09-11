from contextlib import contextmanager
import hashlib,json
from uuid import UUID
from fastapi import APIRouter,Request,Header,Depends
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from . import service as s
from .models import *

def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    api=APIRouter(prefix='/api/v1/finance',tags=['finance'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='finance.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                # A command response contains finance data; writers need read too.
                a.require('finance.read');s.guard(db,a,write);yield db,a
        except IntegrityError as e:
            if e.orig.sqlstate in ('23503','23505','23514'):raise Denied(409,'FIN_CONSTRAINT') from None
            raise
    def execute(request,body,key,action,permission,check,perform):
        with tx(request,permission,True) as (db,a):
            check(db,a) # visibility checked before all idempotent replays
            return s.command(db,a,'finance.'+action,key,body.model_dump(),request.state.request_id,lambda:perform(db,a))
    @api.get('/context',response_model=FinanceContext)
    def permissions(request:Request):
        with tx(request) as (db,a):return {'permissions':sorted(p for p in a.permissions if p.startswith('finance.'))}
    @api.get('/sources',response_model=list[SourceView])
    def sources(request:Request):
        with tx(request) as (db,a):return s.sources(db,a)
    @api.get('/sources/{direction}/{id}',response_model=SourceSummary)
    def source(direction:Direction,id:UUID,request:Request):
        with tx(request) as (db,a):return s.source_summary(db,a,direction,id)
    @api.get('/parties',response_model=list[PartyView])
    def parties(request:Request):
        with tx(request) as (db,a):
            result=[]
            for d,t in [('receivable','crm_customers'),('payable','inv_suppliers')]:
                for p in s.rows(db,t):
                    try:s.party(db,a,d,p['id']);result.append({'id':p['id'],'name':p['name'],'direction':d})
                    except Denied as e:
                        if e.code!='NOT_FOUND':raise
            return result
    @api.get('/summary',response_model=SummaryView)
    def summary(request:Request):
        with tx(request) as (db,a):return s.summary(db,a)
    @api.get('/reconciliation',response_model=FinanceReconciliation)
    def reconciliation(request:Request):
        with tx(request) as (db,a):return s.reconciliation(db,a)
    @api.post('/plans',response_model=PlanView)
    def plan(body:PlanInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'plan.create:'+str(body.source_id),'finance.plan',lambda db,a:s.source(db,a,body.direction,body.source_id),lambda db,a:s.create_plan(db,a,body))
    @api.post('/plans/import',response_model=list[PlanView])
    def import_plans(body:ImportInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'plan.import:'+str(body.source_id),'finance.plan',lambda db,a:s.source(db,a,'receivable',body.source_id),lambda db,a:s.import_plans(db,a,body))
    @api.post('/source-adjustments',response_model=SourceView)
    def source_adjust(body:SourceAdjustment,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'source.adjust:'+str(body.source_id),'finance.correct',lambda db,a:s.source(db,a,body.direction,body.source_id),lambda db,a:s.source_adjustment(db,a,body))
    @api.post('/plans/{id}/correct-adjustment',response_model=PlanView)
    def correct_adjustment(id:UUID,body:AdjustmentCorrectionInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'plan.correct-adjustment:'+str(id)+':'+str(body.adjustment_id),'finance.correct',lambda db,a:s.correction_original(db,a,id,body.adjustment_id),lambda db,a:s.correct_adjustment(db,a,id,body))
    @api.post('/cash',response_model=CashView)
    def cash(body:CashInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'cash.create:'+str(body.party_id),'finance.cash',lambda db,a:s.party(db,a,body.direction,body.party_id),lambda db,a:s.create_cash(db,a,body))
    @api.post('/refunds',response_model=RefundView)
    def refund(body:RefundInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'refund.create:'+str(body.cash_id),'finance.correct',lambda db,a:s.cash(db,a,body.cash_id),lambda db,a:s.create_refund(db,a,body))
    @api.post('/invoices',response_model=InvoiceView)
    def invoice(body:InvoiceInput,request:Request,idempotency_key:str=Header('')):
        def check(db,a):
            s.party(db,a,body.direction,body.party_id)
            for l in body.lines:s.source(db,a,body.direction,l.source_id)
            if body.original_id:s.invoice(db,a,body.original_id)
        scope=hashlib.sha256(json.dumps([body.direction,str(body.party_id),str(body.original_id),sorted(str(l.source_id) for l in body.lines)]).encode()).hexdigest()
        return execute(request,body,idempotency_key,'invoice.create:'+scope,'finance.invoice',check,lambda db,a:s.create_invoice(db,a,body))
    # Each generated route closes over immutable metadata, with concrete body and response types.
    def collection(kind,view,detail):
        def listing(request:Request):
            with tx(request) as (db,a):return s.listing(db,a,kind)
        def get(id:UUID,request:Request):
            with tx(request) as (db,a):return detail(db,a,id)
        api.add_api_route('/'+kind,listing,methods=['GET'],response_model=list[view],name='finance_'+kind)
        api.add_api_route('/'+kind+'/{id}',get,methods=['GET'],response_model=view,name='finance_'+kind+'_detail')
    for kind,view,fn in [('plans',PlanView,s.plan),('cash',CashView,s.cash),('refunds',RefundView,s.refund),('invoices',InvoiceView,s.invoice)]:collection(kind,view,fn)
    def action(kind,name,model,view,permission,fn,detail,extra=None):
        def endpoint(id:UUID,body,request:Request,idempotency_key:str=Header('')):
            def check(db,a):
                detail(db,a,id)
                if extra:extra(db,a,body)
            return execute(request,body,idempotency_key,kind+'.'+name+':'+str(id),permission,check,lambda db,a:fn(db,a,id,body))
        endpoint.__annotations__['body']=model
        api.add_api_route('/'+kind+'/{id}/'+name,endpoint,methods=['POST'],response_model=view,name='finance_'+kind+'_'+name)
    action('plans','confirm',Version,PlanView,'finance.confirm',s.confirm_plan,s.plan)
    action('plans','adjust',AdjustmentInput,PlanView,'finance.correct',s.adjust,s.plan,lambda db,a,b:s.row(db,'del_returns',b.return_id) if b.return_id else None)
    action('plans','release',ReleaseInput,PlanView,'finance.confirm',s.release,s.plan)
    action('cash','confirm',Version,CashView,'finance.cash',s.confirm_cash,s.cash)
    action('cash','allocate',AllocateInput,CashView,'finance.allocate',s.allocate,s.cash,lambda db,a,b:[s.plan(db,a,l.plan_id) for l in b.lines])
    action('cash','reverse',Version,CashView,'finance.correct',s.reverse_cash,s.cash)
    action('refunds','confirm',RefundConfirm,RefundView,'finance.correct',s.confirm_refund,s.refund)
    action('refunds','reverse',Version,RefundView,'finance.correct',s.reverse_refund,s.refund)
    action('invoices','confirm',Version,InvoiceView,'finance.invoice',s.confirm_invoice,s.invoice)
    action('invoices','reverse',Version,InvoiceView,'finance.invoice',s.reverse_invoice,s.invoice)
    def allocation_visible(db,a,id):
        l=s.row(db,'fin_allocations',id);s.plan(db,a,l['plan_id']);s.cash(db,a,l['cash_id'])
    action('allocations','reverse',Version,CashView,'finance.correct',s.reverse_allocation,allocation_visible)
    for kind,view,detail,permission in [('plans',PlanView,s.plan,'finance.plan'),('cash',CashView,s.cash,'finance.cash'),('refunds',RefundView,s.refund,'finance.correct'),('invoices',InvoiceView,s.invoice,'finance.invoice')]:
        action(kind,'cancel',Version,view,permission,lambda db,a,id,b,k=kind:s.cancel(db,a,k,id,b),detail)
    return api
