from contextlib import contextmanager
from uuid import UUID
from fastapi import APIRouter,Request,Header,Depends
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from silicon.inventory import service as inv
from silicon.assembly import service as asm
from . import service as s
from .models import TestInput,ShipmentInput,Version,AcceptInput,CorrectInput,ReturnInput,DeliveryDeviceView,DeliveryProgress,ShipmentView,DeliveryReconciliation

def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    api=APIRouter(prefix='/api/v1/delivery',tags=['delivery'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='delivery.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                asm.guard(db,a,write);yield db,a
        except IntegrityError as e:
            if e.orig.sqlstate in ('23503','23505','23514'):raise Denied(409,'DELIVERY_CONSTRAINT') from None
            raise
    def public(a,value):return inv.serial(asm.public(a,value))
    @api.get('/devices',response_model=list[DeliveryDeviceView],response_model_exclude_unset=True)
    def devices(request:Request):
        with tx(request) as (db,a):return public(a,[s.device(db,x['id']) for x in inv.rows(db,'asm_devices')])
    @api.get('/devices/{id}',response_model=DeliveryDeviceView,response_model_exclude_unset=True)
    def device(id:UUID,request:Request):
        with tx(request) as (db,a):return public(a,s.device(db,id))
    @api.get('/orders',response_model=list[DeliveryProgress],response_model_exclude_unset=True)
    def orders(request:Request):
        with tx(request) as (db,a):return public(a,[s.progress(db,x['id']) for x in inv.rows(db,'sales_orders')])
    @api.get('/shipments',response_model=list[ShipmentView],response_model_exclude_unset=True)
    def shipments(request:Request):
        with tx(request) as (db,a):return public(a,[s.shipment(db,x['id']) for x in inv.rows(db,'del_shipments')])
    @api.get('/shipments/{id}',response_model=ShipmentView,response_model_exclude_unset=True)
    def shipment(id:UUID,request:Request):
        with tx(request) as (db,a):return public(a,s.shipment(db,id))
    @api.post('/devices/{id}/tests',response_model=DeliveryDeviceView,response_model_exclude_unset=True)
    def test(id:UUID,body:TestInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'delivery.test',True) as (db,a):
            inv.row(db,'asm_devices',id)
            return public(a,inv.command(db,a,'delivery.test:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.test(db,a,id,body)))
    @api.post('/shipments',response_model=ShipmentView,response_model_exclude_unset=True)
    def create(body:ShipmentInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'delivery.ship',True) as (db,a):
            inv.row(db,'sales_orders',body.order_id)
            return public(a,inv.command(db,a,'delivery.create:'+str(body.order_id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.create(db,a,body)))
    @api.post('/shipments/{id}/confirm',response_model=ShipmentView,response_model_exclude_unset=True)
    def confirm(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'delivery.ship',True) as (db,a):
            inv.row(db,'del_shipments',id)
            return public(a,inv.command(db,a,'delivery.confirm:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.confirm(db,a,id,body,request.state.request_id)))
    def execute(request,id,body,key,action,permission,fn):
        with tx(request,permission,True) as (db,a):
            inv.row(db,'del_shipments',id)
            return public(a,inv.command(db,a,'delivery.'+action+':'+str(id),key,body.model_dump(),request.state.request_id,lambda:fn(db,a)))
    @api.post('/shipments/{id}/accept',response_model=ShipmentView,response_model_exclude_unset=True)
    def accept(id:UUID,body:AcceptInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,id,body,idempotency_key,'accept','delivery.accept',lambda db,a:s.accept(db,a,id,body))
    @api.post('/shipments/{id}/correct-acceptance',response_model=ShipmentView,response_model_exclude_unset=True)
    def correct(id:UUID,body:CorrectInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,id,body,idempotency_key,'correct','delivery.correct',lambda db,a:s.correct_acceptance(db,a,id,body))
    @api.post('/shipments/{id}/return',response_model=ShipmentView,response_model_exclude_unset=True)
    def receive(id:UUID,body:ReturnInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,id,body,idempotency_key,'return','delivery.return',lambda db,a:s.receive_return(db,a,id,body,request.state.request_id))
    @api.post('/shipments/{id}/cancel',response_model=ShipmentView,response_model_exclude_unset=True)
    def cancel(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        return execute(request,id,body,idempotency_key,'cancel','delivery.ship',lambda db,a:s.cancel(db,a,id,body))
    @api.post('/shipments/{id}/reverse',response_model=ShipmentView,response_model_exclude_unset=True)
    def reverse(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        return execute(request,id,body,idempotency_key,'reverse','delivery.correct',lambda db,a:s.reverse(db,a,id,body,request.state.request_id))
    @api.get('/reconciliation',response_model=DeliveryReconciliation,response_model_exclude_unset=True)
    def reconciliation(request:Request):
        with tx(request) as (db,a):return public(a,s.reconciliation(db))
    return api
