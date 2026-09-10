from contextlib import contextmanager
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Request
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from . import service as s
from .models import QuoteInput,QuoteUpdate,QuoteDetail,QuoteSummary,Calculation,DiscountCode,DiscountRef


def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    routes=APIRouter(prefix='/api/v1/quotes',tags=['quote-drafts'],dependencies=[Depends(context)])
    @contextmanager
    def transaction(request,write=False):
        try:
            with request_tenant(engine,request,settings,'quote.write' if write else 'quote.read',write=write,require_context=True) as (db,access):
                s.guard(db,access,write);yield db,access
        except IntegrityError as exc:
            if exc.orig.sqlstate in ('23503','23505','23514'):raise Denied(422,'INVALID_QUOTE_RELATION') from None
            raise
    @routes.get('',response_model=list[QuoteSummary])
    def listing(request:Request):
        with transaction(request) as (db,a):return s.listing(db,a)
    @routes.post('/evaluate',response_model=Calculation)
    def evaluate(body:QuoteInput,request:Request):
        with transaction(request,True) as (db,a):return s.evaluate(db,a,body,applying=True)
    @routes.post('/discount',response_model=DiscountRef)
    def discount(body:DiscountCode,request:Request):
        with transaction(request,True) as (db,a):return s.resolve_discount(db,a,body.code)
    @routes.get('/{id}',response_model=QuoteDetail)
    def detail(id:UUID,request:Request):
        with transaction(request) as (db,a):return s.detail(db,a,id)
    @routes.post('',response_model=QuoteDetail,status_code=201)
    def create(body:QuoteInput,request:Request,idempotency_key:str=Header('')):
        with transaction(request,True) as (db,a):return s.save(db,a,body,idempotency_key,request.state.request_id)
    @routes.put('/{id}',response_model=QuoteDetail)
    def update(id:UUID,body:QuoteUpdate,request:Request,idempotency_key:str=Header('')):
        with transaction(request,True) as (db,a):return s.save(db,a,body,idempotency_key,request.state.request_id,id)
    return routes
