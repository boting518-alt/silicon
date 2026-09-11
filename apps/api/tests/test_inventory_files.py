"""Real PG + filesystem regressions; ASGI receive is the upload transport seam."""
import asyncio,hashlib,os,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from test_identity import identities
from test_contracts import client,file_root,PDF,source,ready,upload,request as contract_post
from test_inventory import P,post,ok,setup_purchase,warehouse,receipt_body
from silicon.settings import Settings
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'infra'))
from clean_contract_files import clean

@pytest.fixture(autouse=True)
def second_admin(identities):
    i=identities
    with i.owner.begin() as db:
        db.execute(text("INSERT INTO memberships VALUES (:t,:u,'admin',true) ON CONFLICT DO NOTHING"),{'t':i.a,'u':i.other})

def age(root):
    for p in root.iterdir():
        if p.is_file():os.utime(p,(time.time()-90000,)*2)
def attach(c,kind,id,version=1,data=PDF,key=None):
    return c.post(P+'/attachments/'+kind+'/'+id,params={'name':'proof.pdf','expected_version':version},content=data,headers={'Idempotency-Key':key or str(uuid4())})
def purchase_draft(c,i,active):
    return ok(post(c,'/contracts',{'number':'FILE-'+str(uuid4())[:8],'supplier_id':active['supplier_id'],'buyer':'虚构买方','manager_id':str(i.user),'signing_date':'2026-01-01','lines':[{'sku_id':active['lines'][0]['sku_id'],'quantity':1,'unit_price':'100.00','due_date':'2026-12-01'}]}))
def csv_preview(c,sku,loc,external):
    csv='external_id,sku,location_id,state,ownership,quantity,serial,batch,unit_cost,cost_status,currency,opening_date,basis\n'+f'{external},{sku["number"]},{loc["id"]},qualified,own,1,{external},,,unknown,CNY,2026-01-01,虚构依据\n'
    return ok(post(c,'/opening/preview',{'csv':csv})),csv.encode()

def test_cleanup_preserves_every_shared_reference_and_frozen_download(engine,database,identities):
    i=identities;sales,_=source(engine,database,i);settings=Settings(database.url,'test',file_root=database.files)
    with client(engine,database,i.user,i.a) as c:
        w,linked=ready(c,sales['id'],i);pending=ok(upload(c,sales['id'],w['version']),201)
        deleted=ok(upload(c,sales['id'],w['version']),201)
        ok(contract_post(c,'/'+sales['id']+'/files/'+deleted['id']+'/delete',{'expected_version':w['version']}))
        sku,active,order=setup_purchase(c,i,1);loc=warehouse(c);purchase=purchase_draft(c,i,active)
        pa=ok(attach(c,'contract',purchase['id']));frozen=ok(post(c,'/contracts/'+purchase['id']+'/activate',{'expected_version':1,'confirmed':True}))
        receipt=ok(post(c,'/receipts',receipt_body(order,loc,['RECEIPT'])));ra=ok(attach(c,'receipt',receipt['id']))
        ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':True,'reason':'测试','expected_version':0}))
        preview,raw1=csv_preview(c,sku,loc,'PREVIEW');posted,raw2=csv_preview(c,sku,loc,'POSTED')
        ok(post(c,'/opening/'+posted['id']+'/commit',{'expected_version':1,'confirmed':True}))
        root=Path(database.files)/str(i.a);orphan=root/str(uuid4());orphan.write_bytes(b'fictional orphan');age(root)
        other=Path(database.files)/str(i.b);other.mkdir();foreign=other/str(uuid4());foreign.write_bytes(b'other tenant');age(other)
        originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        assert clean(settings,i.user,i.a)==2
        assert {p.name for p in root.iterdir()}==set(originals)
        assert clean(settings,i.user,i.a,True)==2
        assert foreign.exists() and not orphan.exists()
        assert c.get('/api/v1/contracts/files/'+linked['id']+'/download').content==PDF
        for f in [pa,ra]:assert c.get(P+'/attachments/'+f['id']+'/download').content==PDF
        for imp,raw in [(preview,raw1),(posted,raw2)]:assert c.get(P+'/opening/'+imp['id']+'/file').content==raw
        assert ok(c.get(P+'/contracts/'+purchase['id']))['snapshot']==frozen['snapshot']
        assert pending['id'] in {x['id'] for x in c.get('/api/v1/contracts/'+sales['id']).json()['files']}
        for p in root.iterdir():assert hashlib.sha256(p.read_bytes()).hexdigest()==originals[p.name]
        ok(post(c,'/opening/'+preview['id']+'/commit',{'expected_version':1,'confirmed':True}))
        assert clean(settings,i.user,i.a,True)==0

async def stream_request(c,url,chunks,key=None,before_chunk=None):
    """Drive real app via ASGI messages; no buffering client transport or mocked auth."""
    req=c.build_request('POST',url,headers={'Idempotency-Key':key or str(uuid4()),'Content-Type':'application/octet-stream'})
    scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':'POST','scheme':'https',
           'path':req.url.path,'raw_path':req.url.path.encode(),'query_string':req.url.query,
           'headers':[(k.lower(),v) for k,v in req.headers.raw if k.lower()!=b'content-length'],
           'client':('127.0.0.1',12345),'server':('localhost',5173),'root_path':''}
    consumed=0;messages=[]
    async def receive():
        nonlocal consumed
        if consumed==len(chunks):await asyncio.Event().wait()
        if before_chunk:await before_chunk(consumed)
        chunk=chunks[consumed];consumed+=1
        return {'type':'http.request','body':chunk,'more_body':consumed<len(chunks)}
    async def send(message):messages.append(message)
    await asyncio.wait_for(c.app(scope,receive,send),timeout=15)
    status=next(x['status'] for x in messages if x['type']=='http.response.start')
    import json
    body=json.loads(b''.join(x.get('body',b'') for x in messages if x['type']=='http.response.body'))
    return status,body,consumed

@pytest.mark.parametrize('unauthorized',[True,False])
def test_upload_rejects_before_consuming_unbounded_stream(engine,database,identities,unauthorized):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,active,_=setup_purchase(c,i);draft=purchase_draft(c,i,active)
        url=P+'/attachments/contract/'+draft['id']+'?name=proof.pdf&expected_version=1'
        if unauthorized:c.cookies.clear()
        status,body,consumed=asyncio.run(stream_request(c,url,[b'x'*(6*1024*1024),b'y'*(6*1024*1024),b'never consume']))
        assert status==(401 if unauthorized else 413),body
        assert consumed==(0 if unauthorized else 2)
    assert not list(Path(database.files).rglob('*'))
    with client(engine,database,i.user,i.a) as c:assert ok(c.get(P+'/attachments'))==[]

@pytest.mark.parametrize('change',['revoke','freeze'])
def test_upload_rechecks_after_unlocked_stream_and_retries_safely(engine,database,identities,change):
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,active,_=setup_purchase(c,i);draft=purchase_draft(c,i,active)
        url=P+'/attachments/contract/'+draft['id']+'?name=proof.pdf&expected_version=1'
        async def alter(index):
            if index!=1:return
            def run():
                if change=='revoke':
                    with i.owner.begin() as db:
                        db.execute(text("SET LOCAL lock_timeout='2s'"))
                        db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
                else:
                    with client(engine,database,i.other,i.a) as other:
                        ok(post(other,'/contracts/'+draft['id']+'/activate',{'expected_version':1,'confirmed':True}))
            await asyncio.wait_for(asyncio.to_thread(run),timeout=5)
        status,body,consumed=asyncio.run(stream_request(c,url,[PDF[:100],PDF[100:]],before_chunk=alter))
        assert status==(403 if change=='revoke' else 409),body
        assert consumed==2
    with client(engine,database,i.other,i.a) as c:assert ok(c.get(P+'/attachments'))==[] and ok(c.get(P+'/stock'))['items']==[]
    # Failed upload leaves at most an aged orphan, never visible business metadata.
    root=Path(database.files)/str(i.a);age(root)
    assert clean(Settings(database.url,'test',file_root=database.files),i.other,i.a,True)==1


def test_upload_limit_boundary_replay_after_freeze_and_scope(engine,database,identities):
    from silicon.main import create_app
    i=identities
    with client(engine,database,i.user,i.a) as c:
        _,active,_=setup_purchase(c,i);draft=purchase_draft(c,i,active)
        url=P+'/attachments/contract/'+draft['id']+'?name=proof.pdf&expected_version=1';key=str(uuid4())
        # Real route configured to its legal minimum; valid PDF padded to exact limit.
        c.app=create_app(Settings(database.url,'test',file_root=database.files,file_max_bytes=1024))
        data=PDF+b' '*(1024-len(PDF))
        status,first,n=asyncio.run(stream_request(c,url,[data[:512],data[512:]],key));assert status==200 and n==2,first
        with client(engine,database,i.other,i.a) as other:ok(post(other,'/contracts/'+draft['id']+'/activate',{'expected_version':1,'confirmed':True}))
        status,replayed,_=asyncio.run(stream_request(c,url,[data],key));assert status==200 and replayed==first
        status,conflict,_=asyncio.run(stream_request(c,url,[PDF],key));assert status==409 and conflict['code']=='IDEMPOTENCY_CONFLICT'
        assert c.get(P+'/attachments/'+first['id']+'/download').content==data
        assert len(ok(c.get(P+'/attachments')))==1
        c.headers['X-Expected-Tenant']=str(i.b)
        status,_,n=asyncio.run(stream_request(c,url,[data]));assert status==409 and n==0
    with client(engine,database,i.other,i.b) as c:
        status,_,n=asyncio.run(stream_request(c,url,[data]));assert status==404 and n==0


def test_cleanup_conservative_when_reference_query_fails_and_inflight_file(engine,database,identities):
    from silicon.contracts.storage import Store
    from sqlalchemy.exc import DBAPIError
    from silicon.identity.access import Denied
    i=identities;settings=Settings(database.url,'test',file_root=database.files)
    store=Store(str(Path(database.files)/str(i.a)),1024);metadata=store.put('proof.pdf',PDF);root=store.root;age(root)
    try:assert clean(settings,i.user,i.a,True)==0 # actual flock protects unpublished write
    finally:store.release()
    with i.owner.begin() as db:db.execute(text('ALTER TABLE inv_imports RENAME TO inv_imports_unavailable'))
    try:
        with pytest.raises(DBAPIError):clean(settings,i.user,i.a,True)
        assert store.path(metadata['storage_id']).exists()
    finally:
        with i.owner.begin() as db:db.execute(text('ALTER TABLE inv_imports_unavailable RENAME TO inv_imports'))
    with pytest.raises(Denied):clean(settings,i.user,i.b,True)
    assert store.path(metadata['storage_id']).exists()
    assert clean(settings,i.user,i.a,True)==1


def test_cleanup_waits_for_inventory_commit_and_preserves_new_reference(engine,database,identities,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from silicon.inventory import service
    i=identities;written=Event();release=Event();original=service.audit
    with client(engine,database,i.user,i.a) as c:
        _,_,order=setup_purchase(c,i);loc=warehouse(c);receipt=ok(post(c,'/receipts',receipt_body(order,loc,['INFLIGHT'])))
    def gated(*args,**kwargs):
        original(*args,**kwargs)
        if str(args[3]).startswith('attachment.'):
            age(Path(database.files)/str(i.a));written.set();assert release.wait(10)
    # SQL audit remains real; synchronization pauses the actual upload before commit.
    monkeypatch.setattr(service,'audit',gated)
    def uploader():
        with client(engine,database,i.user,i.a) as c:return ok(attach(c,'receipt',receipt['id']))
    settings=Settings(database.url,'test',file_root=database.files)
    with ThreadPoolExecutor(2) as pool:
        upload_future=pool.submit(uploader)
        try:
            assert written.wait(8)
            clean_future=pool.submit(clean,settings,i.other,i.a,True)
            deadline=time.monotonic()+5;waiting=False
            while time.monotonic()<deadline:
                with engine.connect() as db:
                    waiting=bool(db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE usename=current_user AND wait_event='advisory' AND pid<>pg_backend_pid()")))
                if waiting:break
                time.sleep(.01)
            assert waiting and not clean_future.done(),'cleaner must wait for uncommitted inventory reference'
        finally:release.set()
        f=upload_future.result(timeout=10);assert clean_future.result(timeout=10)==0
    with client(engine,database,i.user,i.a) as c:assert c.get(P+'/attachments/'+f['id']+'/download').content==PDF
