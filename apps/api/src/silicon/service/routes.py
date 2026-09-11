from contextlib import contextmanager
from uuid import UUID
from fastapi import APIRouter,Request,Header,Depends
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from . import service as s
from .models import *

def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    api=APIRouter(prefix='/api/v1/service',tags=['service'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='service.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                a.require('service.read');s.guard(db,a,write);yield db,a
        except IntegrityError as e:
            if e.orig.sqlstate in ('23503','23505','23514'):raise Denied(409,'SERVICE_CONSTRAINT') from None
            raise
    def execute(request,body,key,op,permission,check,fn):
        with tx(request,permission,True) as (db,a):
            check(db,a)
            return s.inv.serial(s.public(a,s.inv.command(db,a,'service.'+op,key,body.model_dump(),request.state.request_id,lambda:fn(db,a))))
    @api.get('/context',response_model=ServiceContext)
    def permissions(request:Request):
        with tx(request) as (db,a):return {'permissions':sorted(a.permissions),'people':[dict(x) for x in db.execute(s.text('SELECT m.user_id AS id,u.display_name AS name FROM memberships m JOIN identity_users u ON u.id=m.user_id WHERE m.active AND tenant_visible(m.tenant_id)')).mappings()]}
    @api.get('/devices',response_model=list[ServiceDevice])
    def devices(request:Request):
        with tx(request) as (db,a):
            result=[]
            for x in s.rows(db,'asm_devices'):
                try:d=s.device(db,a,x['id']);l=s.source_line(d);result.append({**d,'line_id':l['id']})
                except Denied as e:
                    if e.code not in ('NOT_FOUND','SERVICE_SHIPPED_SOURCE_REQUIRED'):raise
            return s.inv.serial(result)
    @api.get('/works',response_model=list[ServiceWorkView],response_model_exclude_unset=True)
    def works(request:Request,device_id:UUID|None=None):
        with tx(request) as (db,a):
            result=[]
            for x in s.rows(db,'svc_works'):
                if device_id and x['device_id']!=device_id:continue
                try:result.append(s.detail(db,a,x['id']))
                except Denied as e:
                    if e.code!='NOT_FOUND':raise
            return s.inv.serial(s.public(a,result))
    @api.get('/works/{id}',response_model=ServiceWorkView,response_model_exclude_unset=True)
    def detail(id:UUID,request:Request):
        with tx(request) as (db,a):return s.inv.serial(s.public(a,s.detail(db,a,id)))
    @api.post('/works',response_model=ServiceWorkView,response_model_exclude_unset=True)
    def create(body:ServiceWorkInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,body,idempotency_key,'create:'+str(body.device_id),'service.manage',lambda db,a:s.device(db,a,body.device_id),lambda db,a:s.create(db,a,body))
    def action(name,model,permission,fn,with_request=False):
        def endpoint(id:UUID,body,request:Request,idempotency_key:str=Header('')):
            return execute(request,body,idempotency_key,name+':'+str(id),permission,lambda db,a:s.command_access(db,a,id,body),lambda db,a:fn(db,a,id,body,request.state.request_id) if with_request else fn(db,a,id,body))
        endpoint.__annotations__['body']=model
        api.add_api_route('/works/{id}/'+name,endpoint,methods=['POST'],response_model=ServiceWorkView,response_model_exclude_unset=True,name='service_'+name)
    action('receive',ServiceReceive,'service.custody',s.receive)
    action('return',ServiceReturnDevice,'service.custody',s.return_device)
    action('diagnose',ServiceDiagnose,'service.diagnose',s.diagnose)
    action('state',ServiceTransition,'service.manage',s.transition)
    action('test',ServiceTestInput,'service.diagnose',s.test)
    action('reserve',ServiceReserve,'service.spares',s.reserve)
    action('release',Version,'service.spares',s.release)
    action('issue',ServiceIssue,'service.spares',s.issue,True)
    action('spare-return',ServiceSpareReturn,'service.spares',s.spare_return,True)
    action('replace',ServiceReplace,'service.replace',s.replace,True)

    action('dispose',ServiceDispose,'service.rma',s.dispose,True)
    action('cost',ServiceCostInput,'service.fee',s.cost)
    @api.post('/works/{id}/charge',response_model=ServiceChargeView)
    def charge(id:UUID,body:ServiceChargeInput,request:Request,idempotency_key:str=Header('')):
        def check(db,a):
            a.require('finance.read');s.scoped(db,a,id)
            if body.rma_id:s.rma(db,a,body.rma_id)
        return execute(request,body,idempotency_key,'charge:'+str(id)+':'+body.kind,'service.fee',check,lambda db,a:s.charge(db,a,id,body))
    @api.get('/works/{id}/charges',response_model=list[ServiceChargeView])
    def charges(id:UUID,request:Request):
        with tx(request) as (db,a):
            a.require('finance.read');s.scoped(db,a,id);return s.inv.serial(s.rows(db,'svc_charges','work_id',id))
    @api.post('/rmas',response_model=RmaView)
    def create_rma(body:RmaInput,request:Request,idempotency_key:str=Header('')):
        def check(db,a):
            s.scoped(db,a,body.work_id)
            for id in body.old_part_ids:
                p=s.row(db,'svc_old_parts',id)
                if p['work_id']!=body.work_id:raise Denied(404,'NOT_FOUND')
                if s.procurement_supplier(db,s.row(db,'inv_layers',p['original_layer_id']))!=body.supplier_id:a.require('service.correct')
        return execute(request,body,idempotency_key,'rma.create:'+str(body.work_id),'service.rma',check,lambda db,a:s.create_rma(db,a,body))
    @api.get('/rmas/{id}',response_model=RmaView)
    def rma(id:UUID,request:Request):
        with tx(request,'service.rma') as (db,a):return s.inv.serial(s.rma(db,a,id))
    def rma_action(name,model,fn,with_request=True,permission='service.rma'):
        def endpoint(id:UUID,body,request:Request,idempotency_key:str=Header('')):
            return execute(request,body,idempotency_key,'rma.'+name+':'+str(id),permission,lambda db,a:s.rma_access(db,a,id,body),lambda db,a:fn(db,a,id,body,request.state.request_id) if with_request else fn(db,a,id,body))
        endpoint.__annotations__['body']=model
        api.add_api_route('/rmas/{id}/'+name,endpoint,methods=['POST'],response_model=RmaView,name='service_rma_'+name)
    rma_action('reopen',Version,s.rma_reopen,False,'service.correct')
    rma_action('send',Version,s.rma_send)
    rma_action('cancel',Version,s.rma_cancel,False)
    rma_action('return',RmaReturn,s.rma_return)
    rma_action('inspect',ServiceInspect,s.rma_inspect)
    action('reverse-change',ServiceReverseChange,'service.correct',s.reverse_change,True)
    @api.get('/options',response_model=ServiceOptions)
    def options(request:Request):
        with tx(request) as (db,a):
            stock=s.inv.stock(db)['items']
            return s.inv.serial({'locations':[{'id':x['id'],'name':x['warehouse']+' / '+x['name']} for x in s.rows(db,'inv_locations') if not s.rows(db,'svc_works','parts_location_id',x['id']) and not s.rows(db,'asm_works','wip_location_id',x['id'])],
              'suppliers':[{'id':x['id'],'name':x['name']} for x in s.rows(db,'inv_suppliers') if x['enabled']],
              'stock':[{k:x.get(k) for k in ('sku_id','number','name','serial_raw','batch','balance','reserved_quantity','layer_id','location_id','location_name')} for x in stock if x['ownership']=='own' and x['state']=='qualified']})
    @api.get('/reconciliation',response_model=ServiceReconciliation)
    def reconciliation(request:Request):
        with tx(request) as (db,a):return s.reconciliation(db,a)
    return api
