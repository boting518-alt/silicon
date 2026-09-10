"""Real PostgreSQL/API contracts; session fixture substitutes login only."""
from uuid import uuid4
from test_identity import identities
from test_crm import client
from test_publication import prepare,submit,approve,issue,convert
from test_catalog import ok

P='/api/v1/contracts'
def request(c,path,body,key=None):return c.post(P+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})
def source(engine,database,i):
    with client(engine,database,i.user,i.a) as one:
        d,_,_=prepare(one,i);candidate=submit(one,d)
    with client(engine,database,i.other,i.a) as two:
        ok(approve(two,candidate),200);v=ok(issue(two,candidate));return ok(convert(two,v)),v

def test_existing_source_contract_can_open_workspace(engine,database,identities):
    i=identities;draft,version=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        response=c.get(P+'/'+draft['id'])
        assert response.status_code==200,response.text
        data=response.json();assert data['id']==draft['id']
        assert data['source']['content']==version['content']
        assert data['state']=='draft' and data['version']==0
        assert data['checks'] and not data['ready']

from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from silicon.main import create_app
from silicon.settings import Settings
from test_identity import session_insert
from silicon.identity.routes import SESSION,CSRF

@pytest.fixture(autouse=True)
def file_root(database,tmp_path):database.files=str(tmp_path/'private-files')
@contextmanager
def client(engine,database,user,tenant):
    token,csrf=session_insert(engine,user,tenant)
    app=create_app(Settings(database.url,'test',file_root=database.files))
    from sqlalchemy.exc import SQLAlchemyError
    async def database_error(request,exc):raise exc
    app.add_exception_handler(SQLAlchemyError,database_error)
    with TestClient(app,base_url='https://localhost:5173') as c:
        c.cookies.set(SESSION,token);c.cookies.set(CSRF,csrf);c.headers.update({'Origin':'https://localhost:5173','X-CSRF-Token':csrf})
        context=c.get('/api/v1/session').json();c.headers.update({'X-Expected-Tenant':str(tenant),'X-Session-Context':context['context_id']});yield c

def fields(i,number='CON-001'):
    return {'number':number,'name':'虚构算力合同','buyer':{'name':'虚构甲方','address':'虚构甲方路1号','representative':'虚构代表甲'},
     'seller':{'name':'虚构乙方','address':'虚构乙方路2号','representative':'虚构代表乙'},'project_lead':{'name':'虚构项目负责人','contact':'test@example.invalid'},
     'key_contacts':[{'name':'虚构关键人','contact':'contact@example.invalid'}],'sales':{'user_id':str(i.user)},'support':{'user_id':str(i.other)},
     'signing_date':'2026-01-01','delivery_note':'签约后协商，不代表已交付',
     'payments':[{'id':str(uuid4()),'name':'预付款','amount':'100.00','trigger':'signing','offset_days':7},{'id':str(uuid4()),'name':'验收款','amount':'200.00','trigger':'acceptance','offset_days':30}]}
from pathlib import Path
PDF=(Path(__file__).resolve().parents[3]/'docs/tasks/TASK-007/evidence/fictional-proof.pdf').read_bytes()

def upload(c,id,v,data=PDF,name='fictional-proof.pdf',key=None):
    return c.post(P+'/'+id+'/uploads',params={'name':name,'category':'proof','expected_version':v},content=data,headers={'Idempotency-Key':key or str(uuid4()),'Content-Type':'application/octet-stream'})
def ready(c,id,i):
    w=ok(request(c,'/'+id+'/save',{'expected_version':0,'fields':fields(i)}),200)
    f=ok(upload(c,id,w['version']));w=ok(request(c,'/'+id+'/files/'+f['id']+'/attach',{'expected_version':w['version']}),200)
    assert w['ready'],w['checks'];return w,f

def test_contract_signing_freezes_order_and_file_with_replay(engine,database,identities):
    i=identities;draft,version=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,f=ready(c,draft['id'],i);body={'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True};key=str(uuid4())
        signed=ok(request(c,'/'+draft['id']+'/sign',body,key))
        assert ok(request(c,'/'+draft['id']+'/sign',body,key))['id']==signed['id']
        assert ok(request(c,'/'+draft['id']+'/sign',body))['id']==signed['id']
        order=c.get(P+'/orders/'+signed['order_id']).json()
        assert order['state']=='pending_fulfillment' and order['amount']=='300.00'
        assert order['content']==signed['content'] and order['quote_version_id']==version['id']
        assert signed['content']['commercial']==version['content']
        assert signed['content']['payments'][0]['resolved_due_date']=='2026-01-08'
        assert signed['content']['payments'][1]['resolved_due_date'] is None
        assert c.get(P+'/files/'+f['id']+'/download').content==PDF
        assert request(c,'/'+draft['id']+'/save',{'expected_version':w['version'],'fields':fields(i)}).json()['code']=='CONTRACT_ALREADY_SIGNED'
        assert request(c,'/'+draft['id']+'/files/'+f['id']+'/delete',{'expected_version':w['version']}).json()['code']=='CONTRACT_ALREADY_SIGNED'
        assert len(c.get(P+'/orders').json())==1

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from silicon.identity.access import tenant_transaction

@pytest.mark.parametrize('bad',['amount','date','missing','source','tamper','contact','responsible'])
def test_signing_hard_gates(engine,database,identities,bad):
    i=identities;draft,v=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,f=ready(c,draft['id'],i)
        if bad in ('amount','date','missing','responsible'):
            value=w['fields']
            if bad=='amount':value['payments'][0]['amount']='99.99'
            if bad=='date':value['signing_date']='2099-01-01'
            if bad=='missing':value['seller']['address']=''
            if bad=='responsible':value['sales']['user_id']=str(uuid4())
            r=request(c,'/'+draft['id']+'/save',{'expected_version':w['version'],'fields':value})
            if bad=='responsible':assert r.status_code==422;return
            w=ok(r,200);assert not w['ready']
        if bad=='source':
            from test_publication import call
            ok(call(c,'/versions/'+v['id']+'/withdraw',{'expected_version':1,'reason':'虚构撤回'}),200)
        if bad=='contact':
            with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:a"),{'t':i.a,'a':i.user})
            detail=c.get(P+'/'+draft['id']).json();assert detail['fields']['project_lead']['contact']==''
            assert detail['source']['content']['customer']['contacts'][0]['email']==''
        body={'expected_version':w['version'],'content_hash':'0'*64 if bad=='tamper' else w['content_hash'],'confirmed':True}
        assert request(c,'/'+draft['id']+'/sign',body).status_code in (403,409,422)
        assert c.get(P+'/orders').json()==[]

@pytest.mark.parametrize('kind',['path','html','large','mismatch','active'])
def test_file_validation_and_isolation(engine,database,identities,kind):
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':fields(i)}),200)
        name='../escape.pdf' if kind=='path' else 'bad.png' if kind=='mismatch' else 'bad.pdf'
        data=b'x'*(10*1024*1024+1) if kind=='large' else b'<html>active</html>' if kind=='html' else PDF.replace(b'trailer',b'/JavaScript trailer') if kind=='active' else PDF
        r=upload(c,draft['id'],w['version'],data,name);assert r.status_code in (413,422),r.text
        assert c.get(P+'/'+draft['id']).json()['files']==[]
        good=ok(upload(c,draft['id'],w['version']));assert c.get(P+'/files/'+good['id']+'/download').status_code==404
        w=ok(request(c,'/'+draft['id']+'/files/'+good['id']+'/attach',{'expected_version':w['version']}),200)
        assert c.get(P+'/files/'+good['id']+'/download').headers['x-content-type-options']=='nosniff'
    with client(engine,database,i.other,i.b) as b:
        assert b.get(P+'/files/'+good['id']+'/download').status_code==404
        assert b.get(P+'/'+draft['id']).status_code==404

@pytest.mark.parametrize('race',['sign','edit','delete','withdraw'])
def test_signing_competition_is_atomic(engine,database,identities,race):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from test_publication import call
    i=identities;draft,v=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:w,f=ready(c,draft['id'],i)
    gate=Barrier(2);body={'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}
    def job(index):
        with client(engine,database,i.user,i.a) as c:
            gate.wait(timeout=5)
            if index==0 or race=='sign':return request(c,'/'+draft['id']+'/sign',body)
            if race=='edit':return request(c,'/'+draft['id']+'/save',{'expected_version':w['version'],'fields':{**w['fields'],'name':'另一个版本'}})
            if race=='delete':return request(c,'/'+draft['id']+'/files/'+f['id']+'/delete',{'expected_version':w['version']})
            return call(c,'/versions/'+v['id']+'/withdraw',{'expected_version':1,'reason':'虚构撤回竞争'})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(job,[0,1]))
    with client(engine,database,i.user,i.a) as c:
        orders=c.get(P+'/orders').json();assert len(orders)<=1
        if race=='sign':assert all(r.status_code==201 for r in results) and len(orders)==1
        elif race in ('edit','delete'):assert sorted(r.status_code for r in results) in ([200,409],[201,409])
        if orders:
            assert orders[0]['content']['fields']['name']==w['fields']['name']
            assert orders[0]['content']['attachments'][0]['id']==f['id']
            sid=orders[0]['contract_version_id']
            for table in ['signed_contracts','sales_orders','signed_files']:
                with pytest.raises(DBAPIError):
                    with tenant_transaction(engine,i.user,i.a,'contract.sign','immutable') as (db,_):db.execute(text('UPDATE '+table+' SET tenant_id=tenant_id'))
            assert c.get(P+'/signed/'+sid).json()['content']['commercial']==v['content']


def test_signed_supplement_is_separate_from_frozen_file_set(engine,database,identities):
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,f=ready(c,draft['id'],i);signed=ok(request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}))
        extra=ok(upload(c,draft['id'],w['version'],name='fictional-supplement.pdf'))
        after=ok(request(c,'/'+draft['id']+'/files/'+extra['id']+'/attach',{'expected_version':w['version']}),200)
        assert next(x for x in after['files'] if x['id']==extra['id'])['supplemental']
        assert c.get(P+'/signed/'+signed['id']).json()['content']==signed['content']
        assert c.get(P+'/files/'+extra['id']+'/download').status_code==200

@pytest.mark.parametrize('bad',['fraction','negative','currency','event_date','offset','duplicate'])
def test_payment_input_rejected(engine,database,identities,bad):
    i=identities;draft,_=source(engine,database,i);value=fields(i)
    if bad=='fraction':value['payments'][0]['amount']='1.001'
    if bad=='negative':value['payments'][0]['amount']='-1.00'
    if bad=='currency':value['payments'][0]['currency']='USD'
    if bad=='event_date':value['payments'][1]['due_date']='2026-12-01'
    if bad=='offset':value['payments'][0]['offset_days']=-1
    if bad=='duplicate':value['payments'][1]['id']=value['payments'][0]['id']
    with client(engine,database,i.user,i.a) as c:assert request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':value}).status_code==422

def test_independent_contract_keys_and_replay_current_access(engine,database,identities):
    from test_quotes import command
    i=identities;draft,v=source(engine,database,i)
    with client(engine,database,i.user,i.a) as one:
        d=ok(command(one,'',v['content']['config']));can=submit(one,d)
    with client(engine,database,i.other,i.a) as two:
        ok(approve(two,can),200);other=ok(convert(two,ok(issue(two,can))))
    with client(engine,database,i.user,i.a) as c:
        key='identical-key'
        for index,item in enumerate([draft,other]):
            body={'expected_version':0,'fields':fields(i,'CON-'+str(index))}
            first=ok(request(c,'/'+item['id']+'/save',body,key),200)
            assert ok(request(c,'/'+item['id']+'/save',body,key),200)['id']==first['id']
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        assert request(c,'/'+other['id']+'/save',body,key).status_code==403
        c.headers['X-Session-Context']=str(uuid4());assert c.get(P+'/'+other['id']).status_code==409

def test_failed_upload_and_orphan_cleanup_never_delete_live_files(engine,database,identities):
    import os,time,sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'infra'))
    from clean_contract_files import clean
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,f=ready(c,draft['id'],i)
        # Physical write succeeds, business transaction rejects stale version.
        assert upload(c,draft['id'],0).status_code==409
        root=Path(database.files)/str(i.a);paths=list(root.iterdir());assert len(paths)==2
        for p in paths:os.utime(p,(time.time()-90000,time.time()-90000))
        settings=Settings(database.url,'test',file_root=database.files)
        assert clean(settings,i.user,i.a)==1
        assert len(list(root.iterdir()))==2
        assert clean(settings,i.user,i.a,True)==1
        assert c.get(P+'/files/'+f['id']+'/download').content==PDF
        w=ok(request(c,'/'+draft['id']+'/files/'+f['id']+'/delete',{'expected_version':w['version']}),200)
        assert c.get(P+'/files/'+f['id']+'/download').status_code==404
        assert clean(settings,i.user,i.a,True)==1
        assert list(root.iterdir())==[]

def test_expired_source_and_snapshot_permissions(engine,database,identities,monkeypatch):
    from datetime import datetime,timezone
    from silicon.publication import service as pub
    i=identities;draft,v=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,f=ready(c,draft['id'],i)
        monkeypatch.setattr(pub,'now',lambda:datetime(2099,1,1,tzinfo=timezone.utc))
        assert request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}).status_code==422
        assert c.get(P+'/orders').json()==[]

def test_upgrade_from_task006_preserves_source_data(engine,database,identities):
    import subprocess,sys
    from pathlib import Path
    i=identities;draft,v=source(engine,database,i);root=Path(__file__).resolve().parents[3]
    # Remove only the still-empty new module, producing the exact 0007 schema.
    for command in [('downgrade','0007_publication'),('upgrade','head')]:
        result=subprocess.run([sys.executable,'infra/migrate.py',*command],cwd=root,env=database.env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
    with client(engine,database,i.user,i.a) as c:
        assert c.get('/api/v1/publication/contracts/'+draft['id']).json()['content']==draft['content']
        assert c.get('/api/v1/publication/versions/'+v['id']).json()['content']==v['content']
        assert c.get(P+'/'+draft['id']).json()['version']==0


def test_later_master_data_and_quote_withdrawal_preserve_signed_order(engine,database,identities):
    from test_catalog import send,update_body
    from test_crm import update_body as crm_update
    from test_publication import call
    i=identities
    with client(engine,database,i.user,i.a) as one:d,parts,customer=prepare(one,i);candidate=submit(one,d)
    with client(engine,database,i.other,i.a) as c:
        ok(approve(c,candidate),200);version=ok(issue(c,candidate));draft=ok(convert(c,version));w,f=ready(c,draft['id'],i)
        signed=ok(request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}))
        order=c.get(P+'/orders/'+signed['order_id']).json()
        ok(send(c,'/skus/'+parts[0]['id'],update_body(parts[0],'skus',name='虚构后续型号',enabled=False),'put'),200)
        ok(c.put('/api/v1/crm/customers/'+customer['id'],json=crm_update(customer,name='虚构后续客户名称'),headers={'Idempotency-Key':str(uuid4())}),200)
        ok(call(c,'/versions/'+version['id']+'/withdraw',{'expected_version':version['version'],'reason':'虚构后续撤回'}),200)
        assert c.get(P+'/signed/'+signed['id']).json()==signed
        assert c.get(P+'/orders/'+order['id']).json()==order
        reopened=c.get(P+'/'+draft['id']).json()
        assert reopened['fields']==w['fields'] and reopened['source']['source_state']=='withdrawn'
        assert reopened['source']['content']==version['content']


def test_old_pending_can_be_deleted_after_signing_without_changing_frozen_evidence(engine,database,identities):
    import os,time,sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'infra'))
    from clean_contract_files import clean
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,a=ready(c,draft['id'],i)
        b=ok(upload(c,draft['id'],w['version'],name='unused.pdf'))
        signed=ok(request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}))
        order=c.get(P+'/orders/'+signed['order_id']).json();key=str(uuid4());body={'expected_version':w['version']}
        deleted=ok(request(c,'/'+draft['id']+'/files/'+b['id']+'/delete',body,key),200)
        assert deleted['version']==w['version'] and [x['id'] for x in deleted['files']]==[a['id']]
        assert ok(request(c,'/'+draft['id']+'/files/'+b['id']+'/delete',body,key),200)==deleted
        root=Path(database.files)/str(i.a)
        for p in root.iterdir():os.utime(p,(time.time()-90000,)*2)
        assert clean(Settings(database.url,'test',file_root=database.files),i.user,i.a,True)==1
        assert len(list(root.iterdir()))==1
        assert c.get(P+'/files/'+a['id']+'/download').content==PDF
        assert c.get(P+'/files/'+b['id']+'/download').status_code==404
        assert c.get(P+'/signed/'+signed['id']).json()==signed
        assert c.get(P+'/orders/'+order['id']).json()==order


@pytest.mark.parametrize('kind',['pdf','jpg','png'])
def test_invalid_marked_documents_rejected_before_attachment_creation(engine,database,identities,kind):
    import struct,zlib
    from pathlib import Path
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    malformed={'pdf':b'%PDF-1.4\nthis is plain text, no PDF objects or pages\n%%EOF',
               'jpg':b'\xff\xd8\xff'+b'not a JPEG image, plain text'+b'\xff\xd9',
               'png':b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,2,0,0,0))+chunk(b'IEND',b'')}
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':fields(i)}),200)
        r=upload(c,draft['id'],w['version'],malformed[kind],'invalid-proof.'+kind)
        assert r.status_code==422,r.text
        assert r.json()['code']=='FILE_TYPE_REJECTED'
        assert c.get(P+'/'+draft['id']).json()['files']==[]
        assert not list(Path(database.files).rglob('*'))


@pytest.mark.parametrize('kind',['pdf','jpg','png'])
def test_decodable_formats_roundtrip_and_truncation_is_rejected(engine,database,identities,kind):
    import io
    from PIL import Image
    if kind=='pdf':data=PDF
    else:
        stream=io.BytesIO();Image.new('RGB',(8,8),(30,90,60)).save(stream,format='JPEG' if kind=='jpg' else 'PNG');data=stream.getvalue()
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':fields(i)}),200)
        f=ok(upload(c,draft['id'],w['version'],data,'valid.'+kind))
        w=ok(request(c,'/'+draft['id']+'/files/'+f['id']+'/attach',{'expected_version':w['version']}),200)
        assert c.get(P+'/files/'+f['id']+'/download').content==data
        truncated=data[:40]+(b'\n%%EOF' if kind=='pdf' else b'\xff\xd9' if kind=='jpg' else data[-12:])
        assert upload(c,draft['id'],w['version'],truncated,'truncated.'+kind).status_code==422
        assert len(c.get(P+'/'+draft['id']).json()['files'])==1


def test_legacy_unfrozen_format_rechecked_on_attach_and_sign(engine,database,identities):
    import hashlib
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,a=ready(c,draft['id'],i);file_id=uuid4();storage=uuid4();data=b'%PDF-1.4\nnot a document\n%%EOF'
        directory=Path(database.files)/str(i.a);(directory/str(storage)).write_bytes(data)
        # Reconstruct an existing pre-fix row, not a mock of the current validator.
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text("INSERT INTO contract_files(tenant_id,id,contract_id,storage_id,name,media_type,size,sha256,category,state,uploaded_by) VALUES (:t,:id,:c,:s,'legacy.pdf','application/pdf',:n,:h,'proof','pending',:u)"),{'t':i.a,'id':file_id,'c':draft['id'],'s':storage,'n':len(data),'h':hashlib.sha256(data).hexdigest(),'u':i.user})
        assert request(c,'/'+draft['id']+'/files/'+str(file_id)+'/attach',{'expected_version':w['version']}).json()['code']=='FILE_TYPE_REJECTED'
        with i.owner.begin() as db:
            db.execute(text("SELECT set_config('silicon.tenant_id',:t,true),set_config('silicon.user_id',:u,true)"),{'t':str(i.a),'u':str(i.user)})
            db.execute(text("UPDATE contract_files SET state='linked' WHERE id=:id"),{'id':file_id})
        w=c.get(P+'/'+draft['id']).json()
        assert request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}).json()['code']=='FILE_TYPE_REJECTED'
        assert c.get(P+'/orders').json()==[]
        assert (directory/str(storage)).read_bytes()==data


def test_pending_deletion_rechecks_current_permissions_and_tenant(engine,database,identities):
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w,a=ready(c,draft['id'],i);b=ok(upload(c,draft['id'],w['version'],name='unused.pdf'))
        signed=ok(request(c,'/'+draft['id']+'/sign',{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True}))
        path='/'+draft['id']+'/files/'+b['id']+'/delete';body={'expected_version':w['version']};key=str(uuid4())
        with client(engine,database,i.other,i.b) as other:assert request(other,path,body).status_code==404
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        assert request(c,path,body,key).status_code==403
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='admin' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        ok(request(c,path,body,key),200)
        with i.owner.begin() as db:db.execute(text("UPDATE memberships SET role='viewer' WHERE tenant_id=:t AND user_id=:u"),{'t':i.a,'u':i.user})
        assert request(c,path,body,key).status_code==403


def test_pending_delete_and_sign_serialize_without_stranding_files(engine,database,identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:w,a=ready(c,draft['id'],i);b=ok(upload(c,draft['id'],w['version'],name='unused.pdf'))
    barrier=Barrier(2)
    def job(sign):
        with client(engine,database,i.user,i.a) as c:
            barrier.wait(timeout=5)
            return request(c,'/'+draft['id']+('/sign' if sign else '/files/'+b['id']+'/delete'),{'expected_version':w['version'],'content_hash':w['content_hash'],'confirmed':True} if sign else {'expected_version':w['version']})
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(job,x) for x in [True,False]];sign,delete=[f.result(timeout=15) for f in futures]
    assert delete.status_code==200,delete.text
    assert sign.status_code in (201,409),sign.text
    with client(engine,database,i.user,i.a) as c:
        current=c.get(P+'/'+draft['id']).json();assert [x['id'] for x in current['files']]==[a['id']]
        if sign.status_code==409:
            assert sign.json()['code']=='VERSION_CONFLICT'
            ok(request(c,'/'+draft['id']+'/sign',{'expected_version':current['version'],'content_hash':current['content_hash'],'confirmed':True}))
        assert len(c.get(P+'/orders').json())==1
        assert c.get(P+'/files/'+a['id']+'/download').content==PDF


@pytest.mark.parametrize('kind',['page_count','page_pixels'])
def test_pdf_processing_limits_reject_without_visible_upload(engine,database,identities,kind):
    import io,pypdfium2 as pdfium
    doc=pdfium.PdfDocument.new()
    for _ in range(51 if kind=='page_count' else 1):doc.new_page(100 if kind=='page_count' else 10000,100 if kind=='page_count' else 10000).close()
    data=io.BytesIO();doc.save(data);doc.close()
    i=identities;draft,_=source(engine,database,i)
    with client(engine,database,i.user,i.a) as c:
        w=ok(request(c,'/'+draft['id']+'/save',{'expected_version':0,'fields':fields(i)}),200)
        r=upload(c,draft['id'],w['version'],data.getvalue(),'large.pdf')
        assert r.status_code==422 and r.json()['code']=='FILE_VALIDATION_LIMIT',r.text
        assert c.get(P+'/'+draft['id']).json()['files']==[]
