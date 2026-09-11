"""Real PG authorization tests. HTTP probe routes/tables exist ONLY in this test module.

Session rows here are explicit authentication substitutes. Real OIDC is a separate suite.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import Request
from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from silicon.main import create_app
from silicon.settings import Settings
from silicon.shared.db import make_engine
from silicon.identity.access import Denied, audit, tenant_transaction
from silicon.identity.routes import SESSION, CSRF, digest, request_tenant
from silicon.identity import tenant_jobs
from silicon.shared import jobs


@pytest.fixture
def identities(engine, database):
    owner = make_engine(database.migration_url)
    a,b,user,other,doc = (uuid4() for _ in range(5))
    with owner.begin() as db:
        db.execute(text('TRUNCATE jobs,sessions,login_attempts,memberships,identity_users,tenants,audit_events CASCADE'))
        db.execute(text("INSERT INTO tenants VALUES (:a,'企业 A'),(:b,'企业 B')"),dict(a=a,b=b))
        db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:u,'test-substitute','one','虚构甲'),(:v,'test-substitute','two','虚构乙')"),dict(u=user,v=other))
        db.execute(text("INSERT INTO memberships VALUES (:a,:u,'admin',true),(:b,:u,'member',true),(:b,:v,'admin',true)"),dict(a=a,b=b,u=user,v=other))
        db.execute(text('''CREATE TABLE IF NOT EXISTS test_resources (
          tenant_id uuid REFERENCES tenants, id uuid, number text NOT NULL, owner_id uuid,
          cost numeric NOT NULL, PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,number),
          FOREIGN KEY(tenant_id,owner_id) REFERENCES memberships(tenant_id,user_id));
          CREATE TABLE IF NOT EXISTS test_attachments (
          tenant_id uuid, id uuid, resource_id uuid, body text,
          PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,resource_id) REFERENCES test_resources(tenant_id,id));
          ALTER TABLE test_resources ENABLE ROW LEVEL SECURITY;
          ALTER TABLE test_resources FORCE ROW LEVEL SECURITY;
          ALTER TABLE test_attachments ENABLE ROW LEVEL SECURITY;
          ALTER TABLE test_attachments FORCE ROW LEVEL SECURITY;'''))
        for table in ('test_resources','test_attachments'):
            db.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON {table}'))
            db.execute(text(f'CREATE POLICY tenant_isolation ON {table} USING (tenant_visible(tenant_id)) WITH CHECK (tenant_visible(tenant_id))'))
            db.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO silicon_app'))
    for tenant,actor in [(a,user),(b,other)]:
        with tenant_transaction(engine,actor,tenant,'resource.write','fixture') as (db,access):
            db.execute(text("INSERT INTO test_resources VALUES (:t,:id,'SAME-001',:u,123)"),dict(t=tenant,id=doc,u=actor))
            db.execute(text("INSERT INTO test_attachments VALUES (:t,:id,:id,'test-only bytes')"),dict(t=tenant,id=doc))
    yield SimpleNamespace(a=a,b=b,user=user,other=other,doc=doc,owner=owner)
    with owner.begin() as db:
        db.execute(text('DROP TABLE test_attachments,test_resources'))
    owner.dispose()


def session_insert(engine, user, tenant=None, token=None, expired=False):
    token = token or str(uuid4())
    csrf = str(uuid4())
    with engine.begin() as db:
        db.execute(text('''INSERT INTO sessions(token_hash,user_id,tenant_id,csrf_hash,expires_at)
         VALUES (:h,:u,:t,:c,:e)'''),dict(h=digest(token),u=user,t=tenant,c=digest(csrf),
         e=datetime.now(timezone.utc)+timedelta(seconds=-1 if expired else 300)))
    return token,csrf


class ProbeChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str | None = None
    cost: Decimal | None = None


@contextmanager
def client_for(engine,database,identity,tenant=None,expired=False):
    settings=Settings(database.url,'test')
    app=create_app(settings)
    # Test-only resources cover future HTTP adapters without adding production endpoints.
    @app.get('/test/resources')
    def resources(request: Request, q: str='', mode: str='list'):
        with request_tenant(engine,request,settings,'resource.read') as (db,access):
            rows=db.execute(text('SELECT * FROM test_resources WHERE number LIKE :q ORDER BY id'),{'q':'%'+q+'%'}).mappings()
            values=[access.fields(dict(r),{'cost':'field.cost'}) for r in rows if access.owns(r['owner_id'])]
            return {'count':len(values)} if mode=='aggregate' else values
    @app.get('/test/resources/{resource_id}')
    def detail(resource_id: str,request: Request):
        with request_tenant(engine,request,settings,'resource.read') as (db,access):
            row=db.execute(text('SELECT * FROM test_resources WHERE id=:id'),{'id':resource_id}).mappings().first()
            if row is None or not access.owns(row['owner_id']):raise Denied(404,'NOT_FOUND')
            return access.fields(dict(row),{'cost':'field.cost'})
    @app.get('/test/attachments/{attachment_id}')
    def attachment(attachment_id: str,request: Request,download: bool=False):
        with request_tenant(engine,request,settings,'attachment.read') as (db,access):
            row=db.execute(text('''SELECT a.id,a.body,r.owner_id FROM test_attachments a JOIN test_resources r
              ON (a.tenant_id,a.resource_id)=(r.tenant_id,r.id) WHERE a.id=:id'''),{'id':attachment_id}).mappings().first()
            if row is None or not access.owns(row['owner_id']):raise Denied(404,'NOT_FOUND')
            return {'body':row['body']} if download else {'id':str(row['id'])}
    @app.post('/test/resources/{resource_id}')
    def modify(resource_id: str, change: ProbeChange, request: Request):
        with request_tenant(engine,request,settings,'resource.write',write=True) as (db,access):
            row=db.execute(text('SELECT * FROM test_resources WHERE id=:id FOR UPDATE'),{'id':resource_id}).mappings().first()
            if row is None or not access.owns(row['owner_id']): raise Denied(404,'NOT_FOUND')
            values=change.model_dump(exclude_unset=True)
            access.require_fields(values,{'cost':'field.cost'})
            for column,value in values.items():
                db.execute(text(f'UPDATE test_resources SET {column}=:value WHERE id=:id'),{'value':value,'id':resource_id})
            audit(db,access.actor_id,access.tenant_id,'resource.update',resource_id,'allowed',request.state.request_id)
            return {'updated':True}
    token,csrf=session_insert(engine,identity.user,tenant,expired=expired)
    with TestClient(app,base_url=settings.public_origin) as client:
        client.cookies.set(SESSION,token)
        client.cookies.set(CSRF,csrf)
        client.headers.update({'Origin':settings.public_origin,'X-CSRF-Token':csrf})
        yield client


def test_runtime_rls_default_deny_pool_and_exception(engine,identities):
    i=identities
    with engine.connect() as db:
        role=db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        assert not any(role)
        assert db.scalar(text("SELECT tableowner FROM pg_tables WHERE tablename='test_resources'"))!='silicon_app'
        assert db.scalar(text('SELECT count(*) FROM test_resources'))==0
        assert db.scalar(text("SELECT relforcerowsecurity AND relrowsecurity FROM pg_class WHERE relname='test_resources'"))
    with pytest.raises(DBAPIError):
        with engine.begin() as db:db.execute(text("INSERT INTO test_resources VALUES (:a,:id,'NOCTX',:u,1)"),dict(a=i.a,id=uuid4(),u=i.user))
    pids=[]
    for tenant in (i.a,i.b,i.a):
        with tenant_transaction(engine,i.user,tenant,'resource.read','reuse') as (db,access):
            pids.append(db.scalar(text('SELECT pg_backend_pid()')))
            assert db.scalars(text('SELECT DISTINCT tenant_id FROM test_resources')).all()==[tenant]
        with engine.connect() as db:
            assert db.scalar(text('SELECT count(*) FROM test_resources'))==0
            assert db.scalar(text("SELECT NULLIF(current_setting('silicon.tenant_id',true),'')")) is None
    assert len(set(pids))==1  # Reused the same physical PG connection across A/B/A.
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.user,i.a,'resource.read','rollback') as (db,_):db.execute(text('SELECT 1/0'))
    with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM test_resources'))==0


def test_composite_fk_and_cross_tenant_writes(engine,identities):
    i=identities
    unique=uuid4()
    with tenant_transaction(engine,i.user,i.a,'resource.write','new') as (db,_):
        db.execute(text("INSERT INTO test_resources VALUES (:t,:id,'ONLY-A',:u,1)"),dict(t=i.a,id=unique,u=i.user))
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.other,i.b,'resource.write','fk') as (db,_):
            db.execute(text('INSERT INTO test_attachments VALUES (:t,:id,:ref,\'test\')'),dict(t=i.b,id=uuid4(),ref=unique))
    with pytest.raises(DBAPIError):
        with tenant_transaction(engine,i.user,i.a,'resource.write','rls') as (db,_):
            db.execute(text("INSERT INTO test_resources VALUES (:t,:id,'FORGED',:u,1)"),dict(t=i.b,id=uuid4(),u=i.user))


def test_session_memberships_csrf_switch_and_logout(engine,database,identities):
    i=identities
    with TestClient(create_app(Settings(database.url,'test')),base_url='https://localhost:5173') as client:
        assert client.get('/api/v1/session').status_code==401
        client.cookies.set(SESSION,'forged')
        assert client.get('/api/v1/session').status_code==401
    with client_for(engine,database,i,expired=True) as client:assert client.get('/api/v1/session').status_code==401
    with client_for(engine,database,i) as client:
        assert len(client.get('/api/v1/session').json()['memberships'])==2
        assert client.get('/test/resources').status_code==403
        for headers in ({'X-CSRF-Token':''},{'X-CSRF-Token':'wrong'},{'Origin':'https://evil.invalid'}):
            assert client.post('/api/v1/session/tenant',json={'tenant_id':str(i.a)},headers=headers).status_code==403
        assert client.post('/api/v1/session/tenant',json={'tenant_id':str(uuid4())}).status_code==403
        assert client.post('/api/v1/session/tenant',json={'tenant_id':str(i.a),'user_id':str(i.other)}).status_code==422
        assert client.post('/api/v1/session/tenant',json={'tenant_id':str(i.a)}).status_code==200
        assert client.get('/api/v1/session').json()['tenant_id']==str(i.a)
        stolen=client.cookies.get(SESSION)
        assert client.post('/api/v1/auth/logout').status_code==200
        client.cookies.set(SESSION,stolen)
        assert client.get('/api/v1/session').status_code==401


def test_lists_details_fields_attachments_and_revocation(engine,database,identities):
    i=identities
    with client_for(engine,database,i,i.a) as client:
        for mode in ('list','search','export'):
            rows=client.get('/test/resources',params={'mode':mode,'q':'SAME','tenant_id':str(i.b)}).json()
            assert len(rows)==1 and rows[0]['tenant_id']==str(i.a) and 'cost' in rows[0]
        assert client.get('/test/resources?mode=aggregate').json()=={'count':1}
        assert client.get(f'/test/resources/{uuid4()}').status_code==404
        assert client.get(f'/test/attachments/{i.doc}').status_code==200
        assert client.get(f'/test/attachments/{i.doc}?download=true').status_code==200
        assert client.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)}).status_code==200
        # Member data scope own: B resource belongs to another actor.
        assert client.get('/test/resources').json()==[]
        assert client.get(f'/test/resources/{i.doc}').status_code==404
        assert client.get(f'/test/attachments/{i.doc}?download=true').status_code==404
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),dict(t=i.b,u=i.user))
        row=client.get(f'/test/resources/{i.doc}').json()
        assert row['tenant_id']==str(i.b) and 'cost' not in row
        assert client.get(f'/test/attachments/{i.doc}').status_code==403
        with i.owner.begin() as db:db.execute(text('UPDATE memberships SET active=false WHERE tenant_id=:t AND user_id=:u'),dict(t=i.b,u=i.user))
        assert client.get('/test/resources').status_code==403
        assert client.get('/api/v1/session').json()['tenant_id'] is None
        assert client.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)}).status_code==403


def test_tenant_jobs_authorization_fencing_and_audit(engine,identities):
    i=identities
    a=tenant_jobs.enqueue(engine,i.user,i.a,'same','request-a')
    assert tenant_jobs.enqueue(engine,i.user,i.a,'same','request-a')==a
    b=tenant_jobs.enqueue(engine,i.user,i.b,'same','request-b')
    assert a!=b
    with pytest.raises(Denied):tenant_jobs.enqueue(engine,i.other,i.a,'forged','denied')
    first=jobs.claim(engine)
    with engine.begin() as db:db.execute(text("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=:id"),first)
    replacement=jobs.claim(engine)
    assert not tenant_jobs.execute(engine,first)
    assert tenant_jobs.execute(engine,replacement)
    with i.owner.begin() as db:db.execute(text('UPDATE memberships SET active=false WHERE tenant_id=:t AND user_id=:u'),dict(t=i.b,u=i.user))
    assert jobs.run_once(engine)
    with engine.connect() as db:
        assert db.scalar(text('SELECT status FROM jobs WHERE id=:id'),{'id':b})=='failed'
    with engine.begin() as db:
        db.execute(text("INSERT INTO jobs(id,kind,dedupe_key) VALUES (:id,'identity.check','missing-context')"),{'id':uuid4()})
    assert jobs.run_once(engine)
    with tenant_transaction(engine,i.user,i.a,'resource.read','audit') as (db,_):
        records=db.execute(text('SELECT action,outcome,request_id,object_id FROM audit_events')).mappings().all()
        assert any(r['action']=='job.execute' and r['outcome']=='allowed' and r['request_id']=='request-a' for r in records)
        assert any(r['action']=='job.enqueue' and r['outcome']=='denied' for r in records)
        assert not any('token' in str(r).lower() for r in records)
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM jobs WHERE error_code='TENANT_AUTHORIZATION_DENIED'"))==2


def test_upgrade_from_task001_preserves_queue(database):
    """A second database in the same disposable cluster; no resident connection."""
    import os, subprocess, sys
    from pathlib import Path
    from sqlalchemy.engine import make_url
    bootstrap=make_engine(str(make_url(database.url).set(username='silicon_bootstrap',database='postgres')))
    name='silicon_upgrade_test'
    with bootstrap.connect().execution_options(isolation_level='AUTOCOMMIT') as db:
        db.execute(text(f'CREATE DATABASE {name} OWNER silicon_migrator'))
    url=str(make_url(database.migration_url).set(database=name))
    owner=make_engine(url)
    root=Path(__file__).resolve().parents[3]
    env={**database.env,'MIGRATION_DATABASE_URL':url}
    try:
        with owner.begin() as db:db.execute(text('GRANT USAGE ON SCHEMA public TO silicon_app'))
        for revision in ['0001_platform','head']:
            result=subprocess.run([sys.executable,'infra/migrate.py','upgrade',revision],cwd=root,env=env,capture_output=True,text=True)
            assert result.returncode==0,result.stderr
            if revision=='0001_platform':
                with owner.begin() as db:
                    db.execute(text("INSERT INTO jobs(id,kind,dedupe_key) VALUES (:id,'smoke','legacy')"),{'id':uuid4()})
        with owner.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0012_delivery'
            row=db.execute(text("SELECT status,tenant_id,actor_id FROM jobs WHERE dedupe_key='legacy'")).one()
            assert tuple(row)==('queued',None,None)
    finally:
        owner.dispose()
        with bootstrap.connect().execution_options(isolation_level='AUTOCOMMIT') as db:db.execute(text(f'DROP DATABASE {name}'))
        bootstrap.dispose()


def test_tenant_worker_lease_expiry_rolls_back_audit(engine,identities,monkeypatch):
    i=identities
    job_id=tenant_jobs.enqueue(engine,i.user,i.a,'late','late-request')
    job=jobs.claim(engine)
    original=tenant_jobs.authorize
    def expiry_during_authorization(db,actor,tenant):
        result=original(db,actor,tenant)
        db.execute(text("UPDATE jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':job_id})
        return result
    monkeypatch.setattr(tenant_jobs,'authorize',expiry_during_authorization)
    assert not tenant_jobs.execute(engine,job)
    with tenant_transaction(engine,i.user,i.a,'resource.read','inspect') as (db,_):
        assert db.scalar(text("SELECT count(*) FROM audit_events WHERE action='job.execute' AND request_id='late-request'"))==0
        assert db.scalar(text('SELECT status FROM jobs WHERE id=:id'),{'id':job_id})=='running'


def test_field_write_permissions_and_controlled_audit(engine,database,identities):
    i=identities
    with i.owner.begin() as db:
        db.execute(text("UPDATE memberships SET role='member' WHERE user_id=:u AND tenant_id=:t"),dict(u=i.user,t=i.a))
    with client_for(engine,database,i,i.a) as client:
        assert client.post(f'/test/resources/{i.doc}',json={'cost':'999'}).status_code==403
        assert client.post(f'/test/resources/{i.doc}',json={'number':'OWN-UPDATED'},headers={'X-CSRF-Token':''}).status_code==403
        response=client.post(f'/test/resources/{i.doc}',json={'number':'OWN-UPDATED'})
        assert response.status_code==200
        with tenant_transaction(engine,i.user,i.a,'resource.read','read') as (db,_):
            assert db.scalar(text('SELECT cost FROM test_resources'))==123
            assert db.scalar(text('SELECT number FROM test_resources'))=='OWN-UPDATED'
            event=db.execute(text("SELECT actor_id,tenant_id,object_id,outcome,request_id FROM audit_events WHERE action='resource.update'")).one()
            assert tuple(event)==(i.user,i.a,str(i.doc),'allowed',response.headers['X-Request-ID'])


def test_cross_tenant_unique_detail_and_attachment_are_404(engine,database,identities):
    i=identities
    unique=uuid4()
    with tenant_transaction(engine,i.user,i.a,'resource.write','fixture') as (db,_):
        db.execute(text("INSERT INTO test_resources VALUES (:t,:id,'ONLY-A',:u,1)"),dict(t=i.a,id=unique,u=i.user))
        db.execute(text("INSERT INTO test_attachments VALUES (:t,:id,:id,'A-only')"),dict(t=i.a,id=unique))
    with i.owner.begin() as db:
        db.execute(text("UPDATE memberships SET role='admin' WHERE user_id=:u AND tenant_id=:t"),dict(u=i.user,t=i.b))
    with client_for(engine,database,i,i.b) as client:
        assert client.get(f'/test/resources/{unique}').status_code==404
        assert client.get(f'/test/attachments/{unique}').status_code==404
        assert client.get(f'/test/attachments/{unique}?download=true').status_code==404
        assert client.get('/test/resources?q=ONLY-A').json()==[]


def test_expired_callback_and_inactive_user(engine,database,identities):
    i=identities
    from silicon.identity.routes import BROWSER
    with engine.begin() as db:
        db.execute(text("INSERT INTO login_attempts VALUES (:s,:b,'nonce','verifier',now()-interval '1 second')"),dict(s=digest('expired-state'),b=digest('browser')))
    with client_for(engine,database,i,i.a) as client:
        client.cookies.set(BROWSER,'browser')
        assert client.get('/api/v1/auth/callback?state=expired-state&code=any').status_code==401
        with i.owner.begin() as db:db.execute(text('UPDATE identity_users SET active=false WHERE id=:u'),{'u':i.user})
        assert client.get('/api/v1/session').status_code==401


def test_dev_provisioning_is_idempotent_and_does_not_authenticate(engine,database):
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    issuer='https://localhost:8443/realms/silicon-dev'
    env={**database.env,'SILICON_ENV':'development','OIDC_ISSUER':issuer}
    for _ in range(2):
        result=subprocess.run([sys.executable,'infra/provision_dev_identity.py'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
        assert result.returncode==0,result.stderr
    with engine.connect() as db:
        user=db.scalar(text("SELECT id FROM identity_users WHERE issuer=:issuer AND subject='11111111-1111-4111-8111-111111111111'"),{'issuer':issuer})
        assert user is not None
        assert db.scalar(text('SELECT count(*) FROM memberships WHERE user_id=:u'),{'u':user})==2
        assert db.scalar(text('SELECT count(*) FROM sessions WHERE user_id=:u'),{'u':user})==0
    result=subprocess.run([sys.executable,'infra/provision_dev_identity.py'],cwd=root,env={**env,'SILICON_ENV':'production'},capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and 'production hardening' in result.stderr
