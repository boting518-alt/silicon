from contextlib import contextmanager
from uuid import UUID
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter,Depends,Header,Request,Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied,audit
from silicon.publication import service as pub
from silicon.quotes import service as q
from . import service as s
from .models import Workspace,Save,Sign,Version,Signed,Order,File
from .storage import Store

def router(engine,settings):
    def storage(a):return Store(str(Path(settings.file_root)/str(a.tenant_id)) if settings.file_root else "",settings.file_max_bytes)
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    routes=APIRouter(prefix='/api/v1/contracts',tags=['contracts'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='contract.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                people=pub.prelock(db,a);q.guard(db,a,write);yield db,a,people
        except IntegrityError as exc:
            if exc.orig.sqlstate in ('23503','23505','23514'):raise Denied(422,'INVALID_CONTRACT_RELATION') from None
            raise
    def run(db,a,op,key,body,request,perform,render):return s.command(db,a,op,key,body.model_dump(mode='json'),request.state.request_id,perform,render)
    @routes.get('',response_model=list[Workspace])
    def listing(request:Request):
        with tx(request) as (db,a,people):
            return pub.listing(db,a,'contract_drafts',lambda id:s.detail(db,a,id,people))
    @routes.get('/orders',response_model=list[Order])
    def orders(request:Request):
        with tx(request) as (db,a,_):
            ids=db.scalars(text("SELECT o.id FROM sales_orders o JOIN signed_contracts s ON s.id=o.contract_version_id JOIN contract_drafts d ON d.id=s.contract_id JOIN crm_customers c ON c.id=(d.content->'config'->>'customer_id')::uuid WHERE (:all OR c.owner_id=:actor) ORDER BY o.number,o.id LIMIT 100"),{'all':a.data_scope=='all','actor':a.actor_id})
            return [s.order(db,a,id) for id in ids]
    @routes.get('/orders/{id}',response_model=Order)
    def order(id:UUID,request:Request):
        with tx(request) as (db,a,_):return s.order(db,a,id)
    @routes.get('/signed/{id}',response_model=Signed)
    def signed(id:UUID,request:Request):
        with tx(request) as (db,a,_):return s.signed(db,a,id)
    @routes.get('/files/{id}/download')
    def download(id:UUID,request:Request):
        with tx(request,'contract.download') as (db,a,_):
            row=s.file_row(db,a,id)
            if row['state']!='linked':raise Denied(404,'NOT_FOUND')
            data=storage(a).read(row);audit(db,a.actor_id,a.tenant_id,'contract.download',id,'allowed',request.state.request_id)
            return Response(data,media_type=row['media_type'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name'],safe=''),'X-Content-Type-Options':'nosniff'})
    @routes.get('/{id}',response_model=Workspace)
    def detail(id:UUID,request:Request):
        with tx(request) as (db,a,people):return s.detail(db,a,id,people)
    @routes.post('/{id}/save',response_model=Workspace)
    def save(id:UUID,body:Save,request:Request,idempotency_key:str=Header('')):
        with tx(request,'contract.write',True) as (db,a,people):
            s.source(db,a,id)
            return run(db,a,'contract.save:'+str(id),idempotency_key,body,request,lambda:s.save(db,a,id,body,people),lambda result:s.detail(db,a,result,people))
    @routes.post('/{id}/sign',response_model=Signed,status_code=201)
    def sign(id:UUID,body:Sign,request:Request,idempotency_key:str=Header('')):
        with tx(request,'contract.sign',True) as (db,a,people):
            s.source(db,a,id)
            def perform():
                # Bytes checked while same business lock excludes attachment mutation.
                for f in s.files(db,id):
                    if f.state=='linked' and not s.signed_id(db,id):storage(a).revalidate(s.file_row(db,a,f.id))
                return s.sign(db,a,id,body,people)
            return run(db,a,'contract.sign:'+str(id),idempotency_key,body,request,perform,lambda result:s.signed(db,a,result))
    @routes.post('/{id}/uploads',response_model=File,status_code=201)
    async def upload(id:UUID,request:Request,name:str=Query(...,max_length=160),category:Literal['contract','proof','technical','other']='contract',expected_version:int=Query(...,ge=0),idempotency_key:str=Header('')):
        with tx(request,'contract.write',True) as (db,a,_):
            s.source(db,a,id);store=storage(a)
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>store.limit:raise Denied(413,'FILE_SIZE_LIMIT')
            data.extend(chunk)
        metadata=store.put(name,bytes(data));metadata['category']=category;kept=False
        try:
            with tx(request,'contract.write',True) as (db,a,_):
                s.source(db,a,id)
                body={k:v for k,v in metadata.items() if k!='storage_id'}|{'expected_version':expected_version}
                def render(result):
                    row=s.file_row(db,a,result)
                    nonlocal kept
                    kept=row['storage_id']==metadata['storage_id']
                    return File(**{k:row[k] for k in File.model_fields})
                result=s.command(db,a,'contract.upload:'+str(id),idempotency_key,body,request.state.request_id,lambda:s.upload(db,a,id,metadata,expected_version),render)
            return result
        except Exception:
            # A transaction with uncertain commit is handled by orphan reconciliation;
            # never remove a potentially committed object on an ambiguous DB failure.
            kept=True
            raise
        finally:
            if not kept:store.remove(metadata['storage_id'])
            store.release()
    @routes.post('/{id}/files/{file_id}/attach',response_model=Workspace)
    def attach(id:UUID,file_id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'contract.write',True) as (db,a,people):
            s.source(db,a,id);row=s.file_row(db,a,file_id);storage(a).revalidate(row)
            return run(db,a,'contract.attach:'+str(id)+':'+str(file_id),idempotency_key,body,request,lambda:s.associate(db,a,id,file_id,body),lambda result:s.detail(db,a,result,people))
    @routes.post('/{id}/files/{file_id}/delete',response_model=Workspace)
    def remove(id:UUID,file_id:UUID,body:Version,request:Request,idempotency_key:str=Header('')):
        with tx(request,'contract.write',True) as (db,a,people):
            s.source(db,a,id)
            return run(db,a,'contract.delete:'+str(id)+':'+str(file_id),idempotency_key,body,request,lambda:s.associate(db,a,id,file_id,body,True),lambda result:s.detail(db,a,result,people))
    return routes
