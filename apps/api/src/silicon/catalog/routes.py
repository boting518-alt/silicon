from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Header, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from . import service as s
from .models import SkuInput,SkuUpdate,Sku,RuleInput,RuleRevision,Rule,BomInput,BomUpdate,Bom,VersionCommand,PriceInput,PriceUpdate,PriceBook,CurrentPrice


def router(engine,settings):
    def declared_context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):
        """Required assertions checked inside the authenticated transaction, never credentials."""
    routes=APIRouter(prefix='/api/v1/catalog',tags=['catalog'],dependencies=[Depends(declared_context)])

    @contextmanager
    def transaction(request,write=False):
        try:
            with request_tenant(engine,request,settings,'catalog.write' if write else 'catalog.read',write=write,require_context=True) as (db,access):
                s.guard(db,access,write)
                yield db,access
        except IntegrityError as exc:
            if exc.orig.sqlstate=='23505':raise Denied(409,'CATALOG_DUPLICATE') from None
            if exc.orig.sqlstate in ('23503','23514'):raise Denied(422,'INVALID_CATALOG_RELATION') from None
            raise

    def execute(request,operation,key,body,perform):
        with transaction(request,True) as (db,access):
            return s.command(db,access,operation,key,body,request.state.request_id,lambda:perform(db,access))

    @routes.get('/skus',response_model=list[Sku])
    def skus(request:Request,q:str=Query('',max_length=160),page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=100)):
        with transaction(request) as (db,_):
            ids=db.scalars(text('SELECT id FROM catalog_skus WHERE number ILIKE :q OR name ILIKE :q ORDER BY number,id LIMIT :limit OFFSET :offset'),{'q':'%'+q+'%','limit':page_size,'offset':(page-1)*page_size}).all()
            return [s.sku(db,id) for id in ids]

    @routes.get('/skus/{id}',response_model=Sku)
    def sku(id:UUID,request:Request):
        with transaction(request) as (db,_):return s.sku(db,id)

    @routes.post('/skus',response_model=Sku,status_code=201)
    def create_sku(body:SkuInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,'sku.create',idempotency_key,body,lambda db,a:s.save_sku(db,a,body))

    @routes.put('/skus/{id}',response_model=Sku)
    def update_sku(id:UUID,body:SkuUpdate,request:Request,idempotency_key:str=Header('')):
        return execute(request,'sku.update:'+str(id),idempotency_key,body,lambda db,a:s.save_sku(db,a,body,id))

    @routes.get('/rules',response_model=list[Rule])
    def rules(request:Request):
        with transaction(request) as (db,_):return [s.rule(db,id) for id in db.scalars(text('SELECT id FROM catalog_rules ORDER BY family_id,revision LIMIT 100')).all()]

    @routes.post('/rules',response_model=Rule,status_code=201)
    def create_rule(body:RuleInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,'rule.create',idempotency_key,body,lambda db,a:s.new_rule(db,a,body))

    @routes.post('/rules/{id}/revise',response_model=Rule,status_code=201)
    def revise_rule(id:UUID,body:RuleRevision,request:Request,idempotency_key:str=Header('')):
        def perform(db,a):
            if s.rule(db,id).revision!=body.expected_version:raise Denied(409,'VERSION_CONFLICT')
            return s.new_rule(db,a,RuleInput.model_validate(body.model_dump(exclude={'expected_version'})),id)
        return execute(request,'rule.revise:'+str(id),idempotency_key,body,perform)

    @routes.get('/boms',response_model=list[Bom])
    def boms(request:Request):
        with transaction(request) as (db,_):return [s.bom(db,id) for id in db.scalars(text('SELECT id FROM catalog_boms ORDER BY family_id,revision LIMIT 100')).all()]

    @routes.get('/boms/{id}',response_model=Bom)
    def bom(id:UUID,request:Request):
        with transaction(request) as (db,_):return s.bom(db,id)

    @routes.post('/boms',response_model=Bom,status_code=201)
    def create_bom(body:BomInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,'bom.create',idempotency_key,body,lambda db,a:s.save_bom(db,a,body))

    @routes.put('/boms/{id}',response_model=Bom)
    def update_bom(id:UUID,body:BomUpdate,request:Request,idempotency_key:str=Header('')):
        return execute(request,'bom.update:'+str(id),idempotency_key,body,lambda db,a:s.save_bom(db,a,body,id))

    @routes.post('/boms/{id}/publish',response_model=Bom)
    def publish_bom(id:UUID,body:VersionCommand,request:Request,idempotency_key:str=Header('')):
        return execute(request,'bom.publish:'+str(id),idempotency_key,body,lambda db,a:s.publish_bom(db,id,body.expected_version))

    @routes.post('/boms/{id}/revise',response_model=Bom,status_code=201)
    def revise_bom(id:UUID,body:VersionCommand,request:Request,idempotency_key:str=Header('')):
        return execute(request,'bom.revise:'+str(id),idempotency_key,body,lambda db,a:s.revise_bom(db,a,id,body.expected_version))

    @routes.get('/price-books',response_model=list[PriceBook])
    def prices(request:Request):
        with transaction(request) as (db,_):return [s.price_book(db,id) for id in db.scalars(text('SELECT id FROM catalog_price_books ORDER BY family_id,revision LIMIT 100')).all()]

    @routes.get('/price-books/{id}',response_model=PriceBook)
    def price(id:UUID,request:Request):
        with transaction(request) as (db,_):return s.price_book(db,id)

    @routes.post('/price-books',response_model=PriceBook,status_code=201)
    def create_price(body:PriceInput,request:Request,idempotency_key:str=Header('')):
        return execute(request,'price.create',idempotency_key,body,lambda db,a:s.save_price(db,a,body))

    @routes.put('/price-books/{id}',response_model=PriceBook)
    def update_price(id:UUID,body:PriceUpdate,request:Request,idempotency_key:str=Header('')):
        return execute(request,'price.update:'+str(id),idempotency_key,body,lambda db,a:s.save_price(db,a,body,id))

    @routes.post('/price-books/{id}/publish',response_model=PriceBook)
    def publish_price(id:UUID,body:VersionCommand,request:Request,idempotency_key:str=Header('')):
        return execute(request,'price.publish:'+str(id),idempotency_key,body,lambda db,a:s.publish_price(db,id,body.expected_version))

    @routes.post('/price-books/{id}/revise',response_model=PriceBook,status_code=201)
    def revise_price(id:UUID,body:VersionCommand,request:Request,idempotency_key:str=Header('')):
        return execute(request,'price.revise:'+str(id),idempotency_key,body,lambda db,a:s.revise_price(db,a,id,body.expected_version))

    @routes.get('/current-price/{id}',response_model=CurrentPrice)
    def current_price(id:UUID,request:Request,scope:str=Query(...,min_length=1,max_length=40),tax_included:bool=True,as_of:AwareDatetime|None=None):
        with transaction(request) as (db,_):return s.current_price(db,id,scope,tax_included,as_of or datetime.now(timezone.utc))

    return routes
