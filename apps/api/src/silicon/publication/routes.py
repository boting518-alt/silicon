from contextlib import contextmanager
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Request
from sqlalchemy.exc import IntegrityError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from silicon.quotes import service as q
from silicon.quotes.models import QuoteDetail
from silicon.catalog import service as c
from . import service as s
from .models import Submit,Decide,Issue,Withdraw,Convert,VersionCommand,Candidate,Published,Contract


def router(engine,settings):
    def context(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    routes=APIRouter(prefix='/api/v1/publication',tags=['publication'],dependencies=[Depends(context)])
    @contextmanager
    def tx(request,permission='quote.read',write=False):
        try:
            with request_tenant(engine,request,settings,permission,write=write,require_context=True) as (db,a):
                people=s.prelock(db,a);q.guard(db,a,write);yield db,a,people
        except IntegrityError as exc:
            if exc.orig.sqlstate in ('23503','23505','23514'):raise Denied(422,'INVALID_PUBLICATION_RELATION') from None
            raise
    @routes.get('/candidates',response_model=list[Candidate])
    def candidates(request:Request):
        with tx(request) as (db,a,people):return s.listing(db,a,'publication_candidates',lambda id:s.candidate(db,a,id,people))
    @routes.get('/candidates/{id}',response_model=Candidate)
    def candidate(id:UUID,request:Request):
        with tx(request) as (db,a,people):return s.candidate(db,a,id,people)
    @routes.post('/drafts/{id}/submit',response_model=Candidate,status_code=201)
    def submit(id:UUID,body:Submit,request:Request,idempotency_key:str=Header('')):
        with tx(request,'quote.submit',True) as (db,a,people):
            q.customer(db,a,q.configuration(db,c.row(db,'quote_drafts',id)))
            return s.command(db,a,'quote.submit:'+str(id),idempotency_key,body,request.state.request_id,
               lambda:s.submit(db,a,id,body),lambda result:s.candidate(db,a,result,people))
    @routes.post('/candidates/{id}/decide',response_model=Candidate)
    def decide(id:UUID,body:Decide,request:Request,idempotency_key:str=Header('')):
        with tx(request,'quote.approve',True) as (db,a,people):
            s.candidate_row(db,a,id)
            return s.command(db,a,'quote.decide:'+str(id),idempotency_key,body,request.state.request_id,
               lambda:s.decide(db,a,id,body,people),lambda result:s.candidate(db,a,result,people))
    @routes.post('/candidates/{id}/issue',response_model=Published,status_code=201)
    def issue(id:UUID,body:Issue,request:Request,idempotency_key:str=Header('')):
        with tx(request,'quote.issue',True) as (db,a,people):
            row,content=s.candidate_row(db,a,id);customer=s.visible(db,a,content)
            s.participant(people,row['submitter_id'],'quote.submit',customer)
            dec=s.decision(db,id)
            if dec:s.participant(people,dec['actor_id'],'quote.approve',customer)
            return s.command(db,a,'quote.issue:'+str(id),idempotency_key,body,request.state.request_id,
               lambda:s.issue(db,a,id,body,people),lambda result:s.published(db,a,result))
    @routes.get('/versions',response_model=list[Published])
    def versions(request:Request):
        with tx(request) as (db,a,_):return s.listing(db,a,'quote_versions',lambda id:s.published(db,a,id))
    @routes.get('/versions/{id}',response_model=Published)
    def version(id:UUID,request:Request):
        with tx(request) as (db,a,_):return s.published(db,a,id)
    @routes.post('/versions/{id}/withdraw',response_model=Published)
    def withdraw(id:UUID,body:Withdraw,request:Request,idempotency_key:str=Header('')):
        with tx(request,'quote.withdraw',True) as (db,a,_):
            s.published(db,a,id)
            return s.command(db,a,'quote.withdraw:'+str(id),idempotency_key,body,request.state.request_id,
              lambda:s.withdraw(db,a,id,body),lambda result:s.published(db,a,result))
    @routes.post('/versions/{id}/revise',response_model=QuoteDetail,status_code=201)
    def revise(id:UUID,body:VersionCommand,request:Request,idempotency_key:str=Header('')):
        with tx(request,'quote.write',True) as (db,a,_):
            s.published(db,a,id)
            return s.command(db,a,'quote.revise:'+str(id),idempotency_key,body,request.state.request_id,
              lambda:s.revise(db,a,id,body,idempotency_key,request.state.request_id),lambda result:q.detail(db,a,result))
    @routes.post('/contracts/from-quote',response_model=Contract,status_code=201)
    def convert(body:Convert,request:Request,idempotency_key:str=Header('')):
        with tx(request,'contract.create',True) as (db,a,_):
            source=s.published(db,a,body.quote_version_id)
            if source.state!='issued':raise Denied(409,'SOURCE_NOT_ACTIVE')
            return s.command(db,a,'contract.from-quote',idempotency_key,body,request.state.request_id,
              lambda:s.convert(db,a,body),lambda result:s.contract(db,a,result))
    @routes.get('/contracts',response_model=list[Contract])
    def contracts(request:Request):
        with tx(request,'contract.read') as (db,a,_):return s.listing(db,a,'contract_drafts',lambda id:s.contract(db,a,id))
    @routes.get('/contracts/{id}',response_model=Contract)
    def contract(id:UUID,request:Request):
        with tx(request,'contract.read') as (db,a,_):return s.contract(db,a,id)
    return routes
