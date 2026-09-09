import hashlib
import secrets
from uuid import UUID, uuid4
from urllib.parse import urlencode
import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from silicon.identity.access import Denied, audit, authorize
from silicon.identity.oidc import OIDC

SESSION = '__Host-silicon'
BROWSER = '__Host-silicon-login'
CSRF = '__Host-silicon-csrf'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cookie(response, name, value, seconds, httponly=True):
    response.set_cookie(name, value, max_age=seconds, secure=True, httponly=httponly, samesite='lax', path='/')


def authenticated(db, request):
    row = db.execute(text('''SELECT s.*,u.display_name FROM sessions s JOIN identity_users u ON u.id=s.user_id
        WHERE s.token_hash=:hash AND s.expires_at>now() AND u.active FOR UPDATE OF s'''),
        {'hash':digest(request.cookies.get(SESSION,''))}).mappings().first()
    if row is None:
        raise Denied(401,'UNAUTHENTICATED')
    request.state.actor_id = row['user_id']
    request.state.tenant_id = row['tenant_id']
    return row


def csrf(request, session, origin):
    token = request.headers.get('X-CSRF-Token','')
    if request.headers.get('Origin') != origin or not token or not secrets.compare_digest(digest(token),session['csrf_hash']):
        raise Denied(403,'CSRF_REJECTED')


class UserInfo(BaseModel):
    id: UUID
    name: str


class TenantInfo(BaseModel):
    id: UUID
    name: str
    role: str


class SessionInfo(BaseModel):
    user: UserInfo
    tenant_id: UUID | None
    memberships: list[TenantInfo]


class SelectedTenant(BaseModel):
    tenant_id: UUID


class LogoutInfo(BaseModel):
    logout_url: str


class TenantSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tenant_id: UUID


def router(engine, settings):
    routes = APIRouter(prefix='/api/v1')
    oidc = OIDC(settings)

    @routes.get('/auth/login', operation_id='login')
    def login():
        state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        try:
            target = oidc.authorization(state, nonce, verifier)
        except (ValueError, KeyError, httpx.HTTPError):
            raise Denied(503, 'OIDC_UNAVAILABLE')
        with engine.begin() as db:
            db.execute(text('DELETE FROM login_attempts WHERE expires_at <= now()'))
            db.execute(text('''INSERT INTO login_attempts VALUES (:state,:browser,:nonce,:verifier,now()+interval '5 minutes')'''),
                       dict(state=digest(state),browser=digest(browser),nonce=nonce,verifier=verifier))
        response = RedirectResponse(target, status_code=302)
        cookie(response,BROWSER,browser,300)
        return response

    @routes.get('/auth/callback', operation_id='callback')
    def callback(request: Request, state: str = '', code: str = ''):
        actor = None
        try:
            with engine.begin() as db:
                attempt = db.execute(text('''DELETE FROM login_attempts WHERE state_hash=:state
                    AND browser_hash=:browser AND expires_at>now() RETURNING nonce,verifier'''),
                    dict(state=digest(state),browser=digest(request.cookies.get(BROWSER,'')))).mappings().first()
            if attempt is None or not code:
                raise ValueError('invalid callback')
            claims = oidc.exchange(code,attempt['verifier'],attempt['nonce'])
            token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with engine.begin() as db:
                db.execute(text('''INSERT INTO identity_users(id,issuer,subject,display_name)
                    VALUES (:id,:issuer,:subject,:name) ON CONFLICT(issuer,subject) DO NOTHING'''),
                    dict(id=uuid4(),issuer=oidc.issuer,subject=claims['sub'],name=str(claims.get('name',claims['sub']))[:200]))
                actor = db.scalar(text('SELECT id FROM identity_users WHERE issuer=:issuer AND subject=:subject AND active'),
                                  dict(issuer=oidc.issuer,subject=claims['sub']))
                if actor is None:
                    raise ValueError('inactive identity')
                # Rotate any previous local session; no token or IdP credential is stored in audit.
                db.execute(text('DELETE FROM sessions WHERE token_hash=:hash'),{'hash':digest(request.cookies.get(SESSION,''))})
                db.execute(text('''INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at)
                    VALUES (:hash,:actor,:csrf,LEAST(now()+make_interval(secs=>:seconds),to_timestamp(:expiry)))'''),
                    dict(hash=digest(token),actor=actor,csrf=digest(csrf_token),seconds=settings.session_seconds,expiry=claims['exp']))
                audit(db,actor,None,'login',actor,'allowed',request.state.request_id)
        except (ValueError, KeyError, jwt.PyJWTError, httpx.HTTPError):
            with engine.begin() as db:
                audit(db,actor,None,'login','callback','denied',request.state.request_id)
            request.state.denial_audited = True
            raise Denied(401,'OIDC_REJECTED')
        response = RedirectResponse(settings.public_origin + '/',status_code=303)
        cookie(response,SESSION,token,settings.session_seconds)
        cookie(response,CSRF,csrf_token,settings.session_seconds,httponly=False)
        response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
        return response

    @routes.get('/session', operation_id='session', response_model=SessionInfo)
    def session(request: Request):
        with engine.begin() as db:
            user = authenticated(db,request)
            memberships = db.execute(text('''SELECT t.id,t.name,m.role FROM memberships m JOIN tenants t ON t.id=m.tenant_id
                WHERE m.user_id=:user AND m.active ORDER BY t.name,t.id'''),{'user':user['user_id']}).mappings().all()
            tenant = user['tenant_id'] if any(m['id']==user['tenant_id'] for m in memberships) else None
            return {'user':{'id':str(user['user_id']),'name':user['display_name']},
                    'tenant_id':str(tenant) if tenant else None,
                    'memberships':[{'id':str(m['id']),'name':m['name'],'role':m['role']} for m in memberships]}

    @routes.post('/session/tenant', operation_id='selectTenant', response_model=SelectedTenant)
    def select_tenant(selection: TenantSelection, request: Request):
        actor = None
        try:
            with engine.begin() as db:
                user = authenticated(db,request)
                actor = user['user_id']
                csrf(request,user,settings.public_origin)
                authorize(db,actor,selection.tenant_id)
                db.execute(text('UPDATE sessions SET tenant_id=:tenant WHERE token_hash=:hash'),
                           {'tenant':selection.tenant_id,'hash':user['token_hash']})
                audit(db,actor,selection.tenant_id,'tenant.switch',selection.tenant_id,'allowed',request.state.request_id)
        except Denied:
            with engine.begin() as db:
                audit(db,actor,selection.tenant_id,'tenant.switch',selection.tenant_id,'denied',request.state.request_id)
            request.state.denial_audited = True
            raise
        return {'tenant_id':str(selection.tenant_id)}

    @routes.post('/auth/logout', operation_id='logout', response_model=LogoutInfo)
    def logout(request: Request):
        with engine.begin() as db:
            user = authenticated(db,request)
            csrf(request,user,settings.public_origin)
            db.execute(text('DELETE FROM sessions WHERE token_hash=:hash'),{'hash':user['token_hash']})
            audit(db,user['user_id'],user['tenant_id'],'logout',user['user_id'],'allowed',request.state.request_id)
        # Local revocation succeeds even when the IdP is down. The UI follows this front-channel URL.
        target = oidc.issuer + '/protocol/openid-connect/logout?' + urlencode(
            {'client_id':settings.oidc_client_id,'post_logout_redirect_uri':settings.public_origin+'/'})
        from fastapi.responses import JSONResponse
        response = JSONResponse({'logout_url':target})
        for name in (SESSION,CSRF,BROWSER):
            response.delete_cookie(name,path='/',secure=True,samesite='lax')
        return response

    return routes


from contextlib import contextmanager


@contextmanager
def request_tenant(engine, request, settings, permission, *, write=False):
    """Future HTTP adapters derive tenant and actor from the session, never a body/header ID."""
    actor = tenant = None
    try:
        with engine.begin() as db:
            user = authenticated(db,request)
            actor, tenant = user['user_id'], user['tenant_id']
            if write:
                csrf(request,user,settings.public_origin)
            if tenant is None:
                raise Denied(403,'TENANT_REQUIRED')
            access = authorize(db,actor,tenant)
            access.require(permission)
            db.execute(text("SELECT set_config('silicon.tenant_id',:tenant,true),set_config('silicon.user_id',:actor,true)"),
                       {'tenant':str(tenant),'actor':str(actor)})
            yield db, access
            audit(db,actor,tenant,permission,tenant,'allowed',request.state.request_id)
    except Denied:
        with engine.begin() as db:
            audit(db,actor,tenant,permission,tenant or 'unselected','denied',request.state.request_id)
        request.state.denial_audited = True
        raise
