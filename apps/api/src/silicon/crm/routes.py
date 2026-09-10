from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from silicon.identity.access import Denied
from silicon.identity.routes import request_tenant
from silicon.crm.models import CustomerInput,CustomerUpdate,CustomerDetail,CustomerPage,Member
from silicon.crm import service


def router(engine,settings):
    def declared_context(x_expected_tenant: str | None=Header(None,description='Page expected tenant, checked against locked server session; not authorization'),
                         x_session_context: str | None=Header(None,description='Opaque context_id from session; changes on every tenant selection')):
        # Validation happens inside request_tenant, after authentication under the session lock.
        pass
    routes=APIRouter(prefix='/api/v1/crm',tags=['customers'],dependencies=[Depends(declared_context)])

    @routes.get('/members',response_model=list[Member],operation_id='crmMembers')
    def members(request:Request):
        with request_tenant(engine,request,settings,'crm.read',require_context=True) as (db,access):
            return list(db.execute(text('''SELECT u.id,u.display_name AS name FROM memberships m JOIN identity_users u ON u.id=m.user_id
                WHERE m.tenant_id=:tenant AND m.active AND u.active ORDER BY u.display_name,u.id'''),{'tenant':access.tenant_id}).mappings())

    @routes.get('/customers',response_model=CustomerPage,operation_id='customers')
    def customers(request:Request,q:str=Query('',max_length=160),page:int=Query(1,ge=1,le=100000),page_size:int=Query(25,ge=1,le=100)):
        with request_tenant(engine,request,settings,'crm.read',require_context=True) as (db,access):
            return service.listing(db,access,q.strip(),page,page_size)

    @routes.get('/customers/{customer_id}',response_model=CustomerDetail,operation_id='customer')
    def customer(customer_id:UUID,request:Request):
        with request_tenant(engine,request,settings,'crm.read',require_context=True) as (db,access):return service.detail(db,access,customer_id)

    def write(request,body,key,customer_id=None):
        try:
            with request_tenant(engine,request,settings,'crm.write',write=True,require_context=True) as (db,access):
                return service.save(db,access,body,key,request.state.request_id,customer_id)
        except IntegrityError as exc:
            # A concurrent unique insert or invalid tenant relation rolls back the whole aggregate.
            if exc.orig.sqlstate=='23505':raise Denied(409,'CUSTOMER_NUMBER_EXISTS') from None
            if exc.orig.sqlstate in ('23503','23514'):raise Denied(422,'INVALID_RELATIONSHIP') from None
            raise

    @routes.post('/customers',response_model=CustomerDetail,status_code=201,operation_id='createCustomer')
    def create(body:CustomerInput,request:Request,idempotency_key:str=Header('',alias='Idempotency-Key')):
        return write(request,body,idempotency_key)

    @routes.put('/customers/{customer_id}',response_model=CustomerDetail,operation_id='updateCustomer')
    def update(customer_id:UUID,body:CustomerUpdate,request:Request,idempotency_key:str=Header('',alias='Idempotency-Key')):
        return write(request,body,idempotency_key,customer_id)

    return routes
