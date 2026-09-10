from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from fastapi.responses import Response
from silicon.contracts.storage import Store
from silicon.identity.access import audit
from urllib.parse import quote
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Request,Header,Depends
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from . import service as s
from .models import SupplierView,LocationView,ContractView,OrderView,ReceiptView,StockView,MovementView,\
    SupplierInput,Tracking,PurchaseContract,PurchaseOrder,Location,Receipt,Transfer,OpeningConfig,CSVInput,Cancel,Amendment

from .models import InventoryVersion as Version

def router(engine,settings):
    def storage(a):return Store(str(Path(settings.file_root)/str(a.tenant_id)) if settings.file_root else "",settings.file_max_bytes)
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    routes=APIRouter(prefix='/api/v1/inventory',tags=['inventory'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='inventory.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                s.guard(db,a,write)
                if permission in ('purchase.write','purchase.activate'):a.require('inventory.cost')
                yield db,a
        except IntegrityError as ex:
            if ex.orig.sqlstate in ('23503','23505','23514'):raise Denied(422,'INVENTORY_CONSTRAINT') from None
            raise
    @routes.get('/suppliers',response_model=list[SupplierView],response_model_exclude_unset=True)
    def suppliers(request:Request):
        with tx(request,'purchase.read') as (db,a):return s.serial([dict(x) for x in db.execute(text('SELECT * FROM inv_suppliers ORDER BY name,id')).mappings()])
    @routes.post('/suppliers')
    def create_supplier(body:SupplierInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):return s.command(db,a,'supplier.create',idempotency_key,body.model_dump(),request.state.request_id,lambda:s.supplier(db,a,body))
    @routes.post('/suppliers/{id}')
    def update_supplier(id:UUID,body:SupplierInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):
            s.row(db,'inv_suppliers',id)
            return s.command(db,a,'supplier.save:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.supplier(db,a,body,id))
    @routes.post('/tracking/{id}')
    def tracking(id:UUID,body:Tracking,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.configure',True) as (db,a):
            s.row(db,'catalog_skus',id)
            return s.command(db,a,'tracking:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.tracking(db,a,id,body))
    @routes.get('/contracts',response_model=list[ContractView],response_model_exclude_unset=True)
    def contracts(request:Request):
        with tx(request,'purchase.read') as (db,a):return s.serial(s.cost_filter(a,[s.contract_detail(db,x['id']) for x in s.rows(db,'inv_contracts')]))
    @routes.get('/contracts/{id}',response_model=ContractView,response_model_exclude_unset=True)
    def contract(id:UUID,request:Request):
        with tx(request,'purchase.read') as (db,a):return s.serial(s.cost_filter(a,s.contract_detail(db,id)))
    @routes.post('/contracts')
    def new_contract(body:PurchaseContract,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):return s.command(db,a,'purchase.create',idempotency_key,body.model_dump(),request.state.request_id,lambda:s.contract_save(db,a,body))
    @routes.post('/contracts/{id}')
    def edit_contract(id:UUID,body:PurchaseContract,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):
            s.row(db,'inv_contracts',id)
            return s.command(db,a,'purchase.save:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.contract_save(db,a,body,id))
    @routes.post('/contracts/{id}/activate')
    def activate(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.activate',True) as (db,a):
            s.row(db,'inv_contracts',id)
            return s.command(db,a,'purchase.activate:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.contract_activate(db,a,id,body))
    @routes.get('/orders',response_model=list[OrderView],response_model_exclude_unset=True)
    def orders(request:Request):
        with tx(request) as (db,a):return s.serial(s.cost_filter(a,[s.order_detail(db,x['id']) for x in s.rows(db,'inv_orders')]))
    @routes.post('/orders')
    def new_order(body:PurchaseOrder,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):
            s.row(db,'inv_contracts',body.contract_id)
            return s.command(db,a,'order.create:'+str(body.contract_id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.order_create(db,a,body))
    @routes.post('/orders/{id}/confirm')
    def confirm_order(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.activate',True) as (db,a):
            s.row(db,'inv_orders',id)
            return s.command(db,a,'order.confirm:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.order_confirm(db,a,id,body))
    @routes.get('/locations',response_model=list[LocationView],response_model_exclude_unset=True)
    def locations(request:Request):
        with tx(request) as (db,a):return s.serial(s.rows(db,'inv_locations'))
    @routes.post('/locations')
    def new_location(body:Location,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.configure',True) as (db,a):return s.command(db,a,'location.create',idempotency_key,body.model_dump(),request.state.request_id,lambda:s.location(db,a,body))
    @routes.get('/stock',response_model=StockView,response_model_exclude_unset=True)
    def stock(request:Request,as_of:datetime|None=None):
        with tx(request) as (db,a):return s.serial(s.cost_filter(a,s.stock(db,as_of)))
    @routes.get('/receipts',response_model=list[ReceiptView],response_model_exclude_unset=True)
    def receipts(request:Request):
        with tx(request) as (db,a):return s.serial(s.cost_filter(a,[s.receipt_detail(db,x['id']) for x in s.rows(db,'inv_receipts')]))
    @routes.post('/receipts')
    def new_receipt(body:Receipt,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.receive',True) as (db,a):
            s.row(db,'inv_orders',body.order_id)
            if any(l.cost_status!='unknown' or l.unit_cost is not None or l.deductible_tax is not None for l in body.lines):a.require('inventory.cost')
            return s.cost_filter(a,s.command(db,a,'receipt.create:'+str(body.order_id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.receipt_create(db,a,body)))
    @routes.post('/receipts/{id}/post')
    def post_receipt(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.receive',True) as (db,a):
            s.row(db,'inv_receipts',id)
            return s.cost_filter(a,s.command(db,a,'receipt.post:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.receipt_post(db,a,id,body,request.state.request_id)))
    @routes.post('/transfers')
    def transfer(body:Transfer,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.read',True) as (db,a):
            a.require('inventory.inspect' if body.source_state!=body.target_state else 'inventory.move')
            s.row(db,'inv_layers',body.layer_id)
            return s.command(db,a,'stock.transfer:'+str(body.layer_id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.transfer(db,a,body,request.state.request_id))
    @routes.get('/movements',response_model=list[MovementView],response_model_exclude_unset=True)
    def movements(request:Request):
        with tx(request) as (db,a):return s.serial([s.movement_detail(db,x['id']) for x in s.rows(db,'inv_movements')])
    @routes.get('/movements/{id}',response_model=MovementView,response_model_exclude_unset=True)
    def get_movement(id:UUID,request:Request):
        with tx(request) as (db,a):return s.serial(s.movement_detail(db,id))
    @routes.post('/movements/{id}/reverse')
    def reverse(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.reverse',True) as (db,a):
            s.row(db,'inv_movements',id)
            return s.command(db,a,'stock.reverse:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.reverse(db,a,id,body,request.state.request_id))
    @routes.post('/opening/configure')
    def opening_config(body:OpeningConfig,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.opening',True) as (db,a):return s.command(db,a,'opening.configure',idempotency_key,body.model_dump(),request.state.request_id,lambda:s.opening_config(db,a,body))
    @routes.get('/opening/configure')
    def opening_state(request:Request):
        with tx(request,'inventory.opening') as (db,a):
            row=db.execute(text('SELECT * FROM inv_opening_policy')).mappings().first();return s.serial(dict(row) if row else None)
    @routes.post('/opening/preview')
    def preview(body:CSVInput,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.opening',True) as (db,a):
            a.require('inventory.cost')
            return s.command(db,a,'opening.preview',idempotency_key,body.model_dump(),request.state.request_id,lambda:s.preview_import(db,a,body,storage(a)))
    @routes.post('/opening/{id}/commit')
    def commit_import(id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'inventory.opening',True) as (db,a):
            a.require('inventory.cost');s.row(db,'inv_imports',id)
            return s.command(db,a,'opening.commit:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.commit_import(db,a,id,body,request.state.request_id,storage(a)))
    @routes.post('/orders/{id}/cancel')
    def cancel(id:UUID,body:Cancel,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.write',True) as (db,a):
            s.row(db,'inv_orders',id)
            return s.command(db,a,'order.cancel:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.cancel_order(db,a,id,body))
    @routes.post('/contracts/{id}/amend')
    def amend(id:UUID,body:Amendment,request:Request,idempotency_key:str=Header('')):
        with tx(request,'purchase.activate',True) as (db,a):
            s.row(db,'inv_contracts',id)
            return s.command(db,a,'purchase.amend:'+str(id),idempotency_key,body.model_dump(),request.state.request_id,lambda:s.amend(db,a,id,body))
    @routes.get('/reconciliation')
    def reconciliation(request:Request,as_of:datetime|None=None):
        with tx(request) as (db,a):return s.serial(s.cost_filter(a,s.reconciliation(db,as_of)))
    @routes.get('/opening/template')
    def template(request:Request):
        with tx(request,'inventory.opening') as (db,a):return Response(','.join(s.CSV_COLUMNS)+'\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="opening-template.csv"'})
    @routes.get('/opening/{id}/file')
    def import_file(id:UUID,request:Request):
        with tx(request,'inventory.opening') as (db,a):
            a.require('inventory.cost');r=s.row(db,'inv_imports',id);data=storage(a).read(r)
            audit(db,a.actor_id,a.tenant_id,'opening.download',id,'allowed',request.state.request_id)
            return Response(data,media_type='text/csv',headers={'Content-Disposition':'attachment; filename="opening-original.csv"','X-Content-Type-Options':'nosniff'})
    @routes.get('/attachments')
    def attachments(request:Request):
        with tx(request,'inventory.download') as (db,a):return s.serial(s.rows(db,'inv_attachments'))
    @routes.post('/attachments/{kind}/{id}')
    async def upload_attachment(kind:Literal['contract','receipt'],id:UUID,request:Request,name:str,expected_version:int,idempotency_key:str=Header('')):
        data=await request.body()
        with tx(request,'purchase.write' if kind=='contract' else 'inventory.receive',True) as (db,a):
            r=s.row(db,'inv_contracts' if kind=='contract' else 'inv_receipts',id)
            body={'name':name,'sha256':__import__('hashlib').sha256(data).hexdigest(),'expected_version':expected_version}
            def perform():
                s.c.expected(r,expected_version)
                if r['state']!='draft':raise Denied(409,'FROZEN_ATTACHMENTS')
                store=storage(a);metadata=store.put(name,data)
                try:
                    fid=__import__('uuid').uuid4();s.insert(db,a,'inv_attachments',{'id':fid,kind+'_id':id,'actor_id':a.actor_id,**metadata})
                    return s.row(db,'inv_attachments',fid)
                finally:store.release()
            return s.command(db,a,'attachment.'+kind+':'+str(id),idempotency_key,body,request.state.request_id,perform)
    @routes.get('/attachments/{id}/download')
    def download_attachment(id:UUID,request:Request):
        with tx(request,'inventory.download') as (db,a):
            r=s.row(db,'inv_attachments',id)
            if r['contract_id']:a.require('purchase.read')
            data=storage(a).read(r);audit(db,a.actor_id,a.tenant_id,'inventory.download',id,'allowed',request.state.request_id)
            return Response(data,media_type=r['media_type'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r['name'],safe=''),'X-Content-Type-Options':'nosniff'})
    @routes.get('/context')
    def inventory_context(request:Request):
        with tx(request) as (db,a):return {'permissions':sorted(a.permissions),'tracking':s.serial(s.rows(db,'inv_tracking'))}
    @routes.get('/summary')
    def summary(request:Request):
        with tx(request) as (db,a):return s.serial(s.summary(db,a))
    return routes
