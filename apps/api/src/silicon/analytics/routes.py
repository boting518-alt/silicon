from typing import Literal
from datetime import date
from uuid import UUID
from pydantic import ValidationError
from fastapi import APIRouter,Request,Header,Depends,Query
from sqlalchemy.exc import DBAPIError
from silicon.identity.routes import request_tenant
from silicon.identity.access import Denied
from silicon.finance.service import guard
from .models import AnalyticsFilter,AnalyticsReport,AnalyticsDetails
from .service import Projection,D

def router(engine,settings):
    snapshot_engine=engine.execution_options(isolation_level='REPEATABLE READ')
    def headers(x_expected_tenant:str|None=Header(None),x_session_context:str|None=Header(None)):pass
    api=APIRouter(prefix='/api/v1/analytics',tags=['analytics'],dependencies=[Depends(headers)])
    def calculate(request,f):
        try:
            with request_tenant(snapshot_engine,request,settings,'analytics.read',require_context=True) as (db,a):
                guard(db,a,False)
                p=Projection(db,a,f);return p,p.report()
        except DBAPIError as e:
            if getattr(e.orig,'sqlstate',None)=='40001':raise Denied(409,'CONTEXT_CHANGED') from None
            raise
    def filters(start:date,end:date,as_of:date,customer_id:UUID|None=None,region:str|None=Query(None,max_length=20),overdue_days:int=Query(90,ge=1,le=3650),old_stock_days:int=Query(180,ge=1,le=3650),due_days:int=Query(7,ge=0,le=90),top_n:int=Query(5,ge=1,le=20)):
        try:return AnalyticsFilter(start=start,end=end,as_of=as_of,customer_id=customer_id,region=region,overdue_days=overdue_days,old_stock_days=old_stock_days,due_days=due_days,top_n=top_n)
        except ValidationError:raise Denied(422,'ANALYTICS_FILTER_INVALID') from None
    @api.get('/overview',response_model=AnalyticsReport)
    def overview(request:Request,f:AnalyticsFilter=Depends(filters)):return calculate(request,f)[1]
    @api.get('/details',response_model=AnalyticsDetails)
    def details(request:Request,metric:str,snapshot:str=Query(min_length=64,max_length=64),page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),sort:Literal['date','label','value']='date',descending:bool=True,f:AnalyticsFilter=Depends(filters)):
        p,r=calculate(request,f)
        m=next((m for m in r.metrics if m.id==metric),None)
        if not m:raise Denied(404,'NOT_FOUND')
        if m.status=='unauthorized':raise Denied(403,'FORBIDDEN')
        if snapshot!=r.snapshot:raise Denied(409,'REPORT_CHANGED')
        xs=p.details[metric]
        xs=sorted(xs,key=lambda x:(D(x.value) if sort=='value' else getattr(x,sort) or f.start,x.id),reverse=descending)
        return AnalyticsDetails(snapshot=r.snapshot,filters=f,metric=m,total=len(xs),page=page,page_size=page_size,items=xs[(page-1)*page_size:page*page_size])
    return api
