"""Real PostgreSQL request-context and aggregate-concurrency regressions.

Authentication is injected as in test_crm; authorization and CRM HTTP paths are real.
"""
from test_crm import client, payload, update_body
from test_identity import identities


def bind(c):
    session=c.get('/api/v1/session').json()
    c.headers.update({'X-Expected-Tenant':session['tenant_id'],
                      'X-Session-Context':session.get('context_id','baseline-missing-context')})


def test_stale_page_requests_rejected_even_without_notification(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        bind(c)
        original=c.post('/api/v1/crm/customers',json=payload()).json()
        assert c.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)}).status_code==200
        for method,path,body in [
            ('get','/crm/members',None),('get','/crm/customers',None),
            ('get','/crm/customers/'+original['id'],None),
            ('post','/crm/customers',payload('STALE-CREATE')),
            ('put','/crm/customers/'+original['id'],update_body(original,name='wrong tenant')),
        ]:
            r=c.request(method,'/api/v1'+path,**({'json':body} if body else {}))
            assert r.status_code==409,r.text
            assert r.json()['code']=='CONTEXT_CHANGED'
        bind(c)
        assert c.get('/api/v1/crm/customers').json()['total']==0
        c.post('/api/v1/session/tenant',json={'tenant_id':str(i.a)})
        bind(c)
        assert c.get('/api/v1/crm/customers').json()['total']==1
        assert c.get('/api/v1/crm/customers/'+original['id']).json()['version']==1


def test_detail_is_one_committed_aggregate_during_replacement(engine,database,identities):
    import threading,time
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event,text
    from silicon.identity.access import tenant_transaction
    from silicon.crm import service
    from silicon.crm.models import CustomerUpdate
    i=identities
    with client(engine,database,i.user,i.a) as c:
        seed=payload();seed['responsibilities']=[{'role':'sales','user_id':str(i.user)}]
        original=c.post('/api/v1/crm/customers',json=seed).json()
    replacement=payload(name='new customer')
    replacement['contacts'][0]['name']='new contact'
    replacement['projects'][0]['name']='new project'
    replacement['sites'][0]['name']='new site'
    body=CustomerUpdate.model_validate({**replacement,'expected_version':1})
    paused=threading.Event();release=threading.Event();writer_started=threading.Event();pids={}
    def after(db,cursor,statement,params,context,many):
        if threading.current_thread().name.startswith('aggregate-reader') and statement.startswith('SELECT * FROM crm_contacts'):
            paused.set();assert release.wait(5),'reader release timeout'
    event.listen(engine,'after_cursor_execute',after)
    def read():
        with tenant_transaction(engine,i.user,i.a,'crm.read','snapshot-read') as (db,access):
            return service.detail(db,access,original['id'])
    def write():
        with tenant_transaction(engine,i.user,i.a,'crm.write','snapshot-write') as (db,access):
            pids['writer']=db.scalar(text('SELECT pg_backend_pid()'));writer_started.set()
            return service.save(db,access,body,'replace','snapshot-write',original['id'])
    blocked=False
    try:
        with ThreadPoolExecutor(1,thread_name_prefix='aggregate-reader') as reads, ThreadPoolExecutor(1) as writes:
            reading=reads.submit(read)
            try:
                assert paused.wait(2)
                writing=writes.submit(write);assert writer_started.wait(2)
                deadline=time.monotonic()+1
                while time.monotonic()<deadline and not writing.done():
                    with engine.connect() as db:blocked=bool(db.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'),{'pid':pids['writer']}))
                    if blocked:break
                    time.sleep(.01)
            finally:release.set()
            old=reading.result(timeout=3);new=writing.result(timeout=3)
        contacts={str(c.id) for c in old.contacts}
        assert all(str(person.contact_id) in contacts for project in old.projects for person in project.people),'mixed aggregate: project points outside returned contacts'
        assert old.version==1 and old.name==original['name']
        assert old.contact_count==2 and old.project_count==2
        assert len(old.responsibilities)==1 and old.responsibilities[0].user_id==i.user
        assert len(old.role_history)==4 and all(r.valid_until is None for r in old.role_history)
        assert {p.name for p in old.projects}=={'科研平台','教学平台'}
        assert {s.name for s in old.sites}=={'科研楼'}
        assert new.version==2 and new.name=='new customer'
        assert blocked,'normal writer must wait for the parent shared lock until read transaction commits'
    finally:
        release.set();event.remove(engine,'after_cursor_execute',after)


def test_missing_context_and_aba_are_rejected(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        old=dict(c.headers)
        for header in ('X-Expected-Tenant','X-Session-Context'):
            value=c.headers.pop(header)
            r=c.get('/api/v1/crm/customers')
            assert r.status_code==428 and r.json()['code']=='CONTEXT_REQUIRED'
            c.headers[header]=value
        for tenant in (i.b,i.a):assert c.post('/api/v1/session/tenant',json={'tenant_id':str(tenant)}).status_code==200
        r=c.post('/api/v1/crm/customers',json=payload('ABA'),headers=old)
        assert r.status_code==409 and r.json()['code']=='CONTEXT_CHANGED'
        bind(c);assert c.get('/api/v1/crm/customers').json()['total']==0


import pytest


@pytest.mark.parametrize('first',['save','switch'])
def test_switch_and_save_follow_session_lock_order(engine,database,identities,first):
    import threading,time
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event,text
    from sqlalchemy.engine import Engine
    i=identities;held=threading.Event();release=threading.Event();waiting=threading.Event();pids={}
    def before(db,cursor,statement,params,context,many):
        chosen=(first=='save' and statement.lstrip().startswith('INSERT INTO crm_customers') and params.get('number')=='SERIAL') or (first=='switch' and statement.startswith('UPDATE sessions SET tenant_id'))
        if chosen:
            held.set();assert release.wait(5)
        elif held.is_set() and statement.startswith('SELECT s.*,u.display_name'):
            pids['waiter']=db.scalar(text('SELECT pg_backend_pid()'));waiting.set()
    event.listen(Engine,'before_cursor_execute',before)
    try:
        with client(engine,database,i.user,i.a) as c,ThreadPoolExecutor(2) as pool:
            def save():return c.post('/api/v1/crm/customers',json=payload('SERIAL'))
            def switch():return c.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)})
            actions={'save':save,'switch':switch}
            leader=pool.submit(actions[first])
            try:
                assert held.wait(2)
                follower=pool.submit(actions['switch' if first=='save' else 'save']);assert waiting.wait(2)
                deadline=time.monotonic()+1;blocked=False
                while time.monotonic()<deadline:
                    with engine.connect() as db:blocked=bool(db.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'),{'pid':pids['waiter']}))
                    if blocked:break
                    time.sleep(.01)
                assert blocked and not follower.done()
            finally:release.set()
            one=leader.result(timeout=3);two=follower.result(timeout=3)
            assert one.status_code==(201 if first=='save' else 200)
            assert two.status_code==(200 if first=='save' else 409),two.text
            bind(c);assert c.get('/api/v1/crm/customers').json()['total']==0
            c.post('/api/v1/session/tenant',json={'tenant_id':str(i.a)});bind(c)
            assert c.get('/api/v1/crm/customers').json()['total']==(1 if first=='save' else 0)
    finally:
        release.set();event.remove(Engine,'before_cursor_execute',before)


def test_stale_edit_cannot_touch_a_visible_record_in_other_enterprise(engine,database,identities):
    i=identities
    with client(engine,database,i.user,i.b) as b:
        target=b.post('/api/v1/crm/customers',json=payload('B-CUSTOMER','B original')).json()
    with client(engine,database,i.user,i.a) as old:
        old.post('/api/v1/session/tenant',json={'tenant_id':str(i.b)})
        response=old.put('/api/v1/crm/customers/'+target['id'],json=update_body(target,name='A draft'))
        assert response.status_code==409 and response.json()['code']=='CONTEXT_CHANGED'
        bind(old)
        actual=old.get('/api/v1/crm/customers/'+target['id']).json()
        assert actual['name']=='B original' and actual['version']==1
