from contextlib import contextmanager
from uuid import UUID
from fastapi import APIRouter,Request,Header,Depends
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from silicon.inventory import service as inv
from . import service as s
from .models import WorkInput,Version,Reserve,Issue,Complete,Reverse,WorkView,DeviceView,SalesSourceView,WorkEdit,ReconciliationView

def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    api=APIRouter(prefix='/api/v1/assembly',tags=['assembly'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='assembly.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                s.guard(db,a,write);yield db,a
        except IntegrityError as e:
            if e.orig.sqlstate in ('23503','23505','23514'):raise Denied(409,'ASSEMBLY_CONSTRAINT') from None
            raise
    @api.get('/orders',response_model=list[SalesSourceView])
    def orders(request:Request):
        with tx(request) as (db,a):return inv.serial(s.orders(db))
    @api.get('/works',response_model=list[WorkView],response_model_exclude_unset=True)
    def works(request:Request):
        with tx(request) as (db,a):return inv.serial(s.public(a,[s.detail(db,x['id']) for x in inv.rows(db,'asm_works')]))
    @api.get('/works/{id}',response_model=WorkView,response_model_exclude_unset=True)
    def detail(id:UUID,request:Request):
        with tx(request) as (db,a):return inv.serial(s.public(a,s.detail(db,id)))
    @api.post('/works',response_model=WorkView,response_model_exclude_unset=True)
    def create(body:WorkInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'assembly.write',True) as (db,a):
            inv.row(db,'sales_orders',body.order_id)
            return s.public(a,inv.command(db,a,'assembly.create:'+str(body.order_id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.create(db,a,body)))
    @api.post('/works/{id}/ready',response_model=WorkView,response_model_exclude_unset=True)
    def ready(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.write',id,body,idempotency_key,'ready',lambda db,a:s.ready(db,a,id,body))
    @api.post('/works/{id}/reserve',response_model=WorkView,response_model_exclude_unset=True)
    def reserve(id:UUID,body:Reserve,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.reserve',id,body,idempotency_key,'reserve',lambda db,a:s.reserve(db,a,id,body,request.state.request_id))
    @api.post('/works/{id}/release',response_model=WorkView,response_model_exclude_unset=True)
    def release(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.release',id,body,idempotency_key,'release',lambda db,a:s.release(db,a,id,body))
    @api.post('/works/{id}/cancel',response_model=WorkView,response_model_exclude_unset=True)
    def cancel(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.write',id,body,idempotency_key,'cancel',lambda db,a:s.release(db,a,id,body,True))
    @api.post('/works/{id}/issue',response_model=WorkView,response_model_exclude_unset=True)
    def issue(id:UUID,body:Issue,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.issue',id,body,idempotency_key,'issue',lambda db,a:s.issue(db,a,id,body,request.state.request_id))
    @api.post('/works/{id}/complete',response_model=WorkView,response_model_exclude_unset=True)
    def complete(id:UUID,body:Complete,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.complete',id,body,idempotency_key,'complete',lambda db,a:s.complete(db,a,id,body,request.state.request_id))
    @api.post('/works/{id}/reverse',response_model=WorkView,response_model_exclude_unset=True)
    def reverse(id:UUID,body:Reverse,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.reverse',id,body,idempotency_key,'reverse',lambda db,a:s.reverse(db,a,id,body,request.state.request_id))
    @api.get('/devices',response_model=list[DeviceView],response_model_exclude_unset=True)
    def devices(request:Request,q:str=''):
        with tx(request,'device.read') as (db,a):
            values=[s.device(db,x['id']) for x in inv.rows(db,'asm_devices')]
            return inv.serial(s.public(a,[d for d in values if q.casefold() in str([d['serial'],d['product']['name'],d['customer_name'],d['contract_number'],d['order_number'],[x['serial'] for x in d['installations']]]).casefold()]))
    @api.get('/devices/{id}',response_model=DeviceView,response_model_exclude_unset=True)
    def device(id:UUID,request:Request):
        with tx(request,'device.read') as (db,a):return inv.serial(s.public(a,s.device(db,id)))
    @api.post('/works/{id}/save',response_model=WorkView,response_model_exclude_unset=True)
    def save(id:UUID,body:WorkEdit,request:Request,idempotency_key:str=Header('')):
        return execute(request,'assembly.write',id,body,idempotency_key,'save',lambda db,a:s.edit(db,a,id,body))
    @api.get('/works/{id}/reconciliation',response_model=ReconciliationView,response_model_exclude_unset=True)
    def reconciliation(id:UUID,request:Request):
        with tx(request) as (db,a):return inv.serial(s.public(a,s.reconciliation(db,id)))
    def execute(request,permission,id,body,key,action,fn):
        with tx(request,permission,True) as (db,a):
            inv.row(db,'asm_works',id)
            return s.public(a,inv.command(db,a,'assembly.'+action+':'+str(id),key,body.model_dump(),request.state.request_id,lambda:fn(db,a)))
    return api
