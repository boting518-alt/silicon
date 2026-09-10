"""Isolated browser acceptance stack; no resident DB and no authentication shortcut.

Uses repository-owned disposable PG fixture. Ctrl-C/SIGTERM cleans only this stack.
"""
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from uuid import UUID,uuid4
import httpx
from sqlalchemy import text

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api/tests'))
from conftest import database as database_fixture
from keycloak_realm import realm,SUBJECT
from silicon.shared.db import make_engine
from silicon.identity.access import tenant_transaction
from silicon.crm.models import CustomerInput
from silicon.crm.service import save

for port in (5173,8000,8443):
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
stop=threading.Event()
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
processes=[]
origin='https://localhost:5173'
issuer='https://127.0.0.1:8443/realms/silicon-dev'
cert=ROOT/'.tools/tls/localhost.crt';key=ROOT/'.tools/tls/localhost.key'
tls=ssl.create_default_context(cafile=str(cert))
assert key.is_file(), "Generate the local test key before starting the stack"
font=ROOT/'.tools/visual/PingFang.ttc'
assert hashlib.sha256(font.read_bytes()).hexdigest()=='6bccdb1a967b2ae7e856927eb559591b2ce05656b0d4ad2764b9c9429f12c0b7', 'Supply the documented visual baseline font; do not silently substitute'
pg=database_fixture.__wrapped__()
database=next(pg)
with tempfile.TemporaryDirectory(prefix='silicon-browser-',dir='/tmp') as directory:
    temp=Path(directory)
    try:
        home=temp/'keycloak'
        shutil.copytree(os.environ['SILICON_TEST_KEYCLOAK_HOME'],home,ignore=shutil.ignore_patterns('._*','data','log'))
        imports=home/'data/import';imports.mkdir(parents=True)
        realm_data=realm(origin)
        if os.getenv('SILICON_BROWSER_PUBLICATION')=='1':
            realm_data['users'].append({'id':'22222222-2222-4222-8222-222222222222','username':'bob','enabled':True,'firstName':'虚构','lastName':'审批人乙','email':'bob@example.invalid','emailVerified':True,'credentials':[{'type':'password','value':'Fictional-bob-17!','temporary':False}]})
        if os.getenv('SILICON_BROWSER_CONTRACTS')=='1':
            realm_data['users'].append({'id':'33333333-3333-4333-8333-333333333333','username':'carol','enabled':True,'firstName':'虚构','lastName':'只读用户','email':'carol@example.invalid','emailVerified':True,'credentials':[{'type':'password','value':'Fictional-carol-17!','temporary':False}]})
        (imports/'realm.json').write_text(json.dumps(realm_data))
        env={**database.env,'OIDC_ISSUER':issuer,'OIDC_CLIENT_ID':'silicon-web','OIDC_CLIENT_SECRET':'fictional-dev-client-secret',
             'OIDC_CA_BUNDLE':str(cert),'PUBLIC_ORIGIN':origin,'SILICON_VISUAL_FONT':str(ROOT/'.tools/visual/PingFang.ttc')}
        if os.getenv('SILICON_BROWSER_CONTRACTS')=='1':env['SILICON_FILE_ROOT']=str(temp/'contract-files')
        owner=make_engine(database.migration_url)
        actor=UUID('11111111-1111-4111-8111-111111111111')
        a=UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');b=UUID('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
        with owner.begin() as db:
            db.execute(text('INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:id,:issuer,:subject,\'虚构用户甲\')'),dict(id=actor,issuer=issuer,subject=SUBJECT))
            db.execute(text("INSERT INTO tenants VALUES (:a,'虚构企业 A'),(:b,'虚构企业 B')"),dict(a=a,b=b))
            db.execute(text("INSERT INTO memberships VALUES (:a,:u,'admin',true),(:b,:u,:role,true)"),dict(a=a,b=b,u=actor,role='viewer' if os.getenv('SILICON_BROWSER_CATALOG')=='1' else 'admin'))
        if os.getenv('SILICON_BROWSER_CONTRACTS')=='1':
            with owner.begin() as db:
                viewer=UUID('33333333-3333-4333-8333-333333333333')
                db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:id,:issuer,:subject,'虚构只读用户')"),dict(id=viewer,issuer=issuer,subject=str(viewer)))
                db.execute(text("INSERT INTO memberships VALUES (:t,:u,:role,true)"),dict(t=a,u=viewer,role='member' if os.getenv('SILICON_BROWSER_INVENTORY')=='1' else 'viewer'))
        owner.dispose()
        engine=make_engine(database.url)
        samples=[('澄川大学 · 人工智能学院','浙江','杭州','高校','战略客户'),('栖原智能科技有限公司','江苏','苏州','企业','重点客户'),('远岑材料研究院','安徽','合肥','科研院所','重点客户'),('京澜智能研究中心','北京','北京','科研院所','战略客户'),('锦序工业科技有限公司','四川','成都','企业','重点客户'),('南序机器人有限公司','广东','深圳','企业','重点客户'),('浦澄数据技术有限公司','上海','上海','企业','重点客户')]
        for n,(name,province,city,industry,level) in enumerate(samples,1):
            contact1=UUID(int=100+n*10);contact2=UUID(int=101+n*10);project=UUID(int=200+n*10)
            body=CustomerInput(number=f'CUS-{n:03}',name=name,province=province,city=city,industry=industry,level=level,stage='稳定合作',
                contacts=[{'id':contact1,'name':'周明远' if n==1 else f'虚构联系人 {n}'},{'id':contact2,'name':'许知微' if n==1 else f'虚构关键人 {n}'}],
                projects=[{'id':project,'name':'科研平台' if n==1 else f'虚构项目 {n}','people':[{'contact_id':contact1,'role':'project_lead'},{'contact_id':contact2,'role':'key_person'}]}],
                responsibilities=[{'role':'sales','user_id':actor}])
            with tenant_transaction(engine,actor,a,'crm.write','browser-fixture') as (db,access):save(db,access,body,f'seed-{n}','browser-fixture')
        with tenant_transaction(engine,actor,a,'crm.write','visual-clock') as (db,_):
            db.execute(text("UPDATE crm_customers SET created_at=timestamptz '2026-09-08 04:00:00+00'-make_interval(secs=>substring(number from 5)::int), updated_at=timestamptz '2026-09-08 04:00:00+00'"))
        if os.getenv('SILICON_BROWSER_CATALOG_SEED')=='1':
            from catalog_examples import seed
            seed(engine,actor,a)
        if os.getenv('SILICON_BROWSER_QUOTES')=='1':
            from quote_examples import seed as quote_seed
            migration=make_engine(database.migration_url)
            quote_seed(engine,migration,actor,a)
            migration.dispose()
        if os.getenv('SILICON_BROWSER_PUBLICATION')=='1':
            from publication_examples import seed as publication_seed
            migration=make_engine(database.migration_url)
            publication_seed(engine,migration,actor,a,issuer)
            migration.dispose()
        review=os.getenv('SILICON_BROWSER_QUOTE_REVIEW')=='1'
        if review:
            from quote_review_fixture import seed as review_seed,CONTROL,EVENTS
            assert not CONTROL.exists() and not EVENTS.exists(), 'Review control files already exist; inspect before starting'
            review_seed(engine,actor,a)
        if os.getenv('SILICON_BROWSER_CONTRACT_REPAIR')=='1':
            assert os.getenv('SILICON_BROWSER_CONTRACTS')=='1' and os.getenv('SILICON_BROWSER_PUBLICATION')=='1'
            from contract_review_examples import seed as contract_seed
            contract_seed(engine,database,actor,a,temp/'contract-files')
        engine.dispose()
        commands=[([str(home/'bin/kc.sh'),'start-dev','--http-host=127.0.0.1','--http-enabled=false','--https-port=8443',f'--https-certificate-file={cert}',f'--https-certificate-key-file={key}','--import-realm','--cache=local'],issuer+'/.well-known/openid-configuration'),
                  ([sys.executable,'-m','uvicorn','infra.quote_review_fixture:create_app' if review else 'silicon.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-access-log'],'http://127.0.0.1:8000/api/v1/ready'),
                  (['npm','run','dev'],origin)]
        for index,(command,url) in enumerate(commands):
            log=(temp/f'process-{index}.log').open('w')
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            processes.append((process,log))
            deadline=time.monotonic()+90
            with httpx.Client(verify=tls,trust_env=False,timeout=2) as client:
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise RuntimeError(f'Process {index} exited: '+(temp/f'process-{index}.log').read_text())
                    try:
                        if client.get(url).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.2)
                else:raise TimeoutError(f'Process {index} startup timeout')
        print('BROWSER_STACK_READY: https://localhost:5173; real IdP; isolated PG; fictional seeded A; empty B',flush=True)
        # Local maintenance handle only, never read by production code or committed.
        (ROOT/'.tools/browser-runtime.json').write_text(json.dumps({'database_url':database.url,'migration_url':database.migration_url,'actor':str(actor),'tenant_a':str(a),'tenant_b':str(b)}))
        stop.wait()
    finally:
        for process,log in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
            log.close()
        pg.close()
        (ROOT/'.tools/browser-runtime.json').unlink(missing_ok=True)
        print('BROWSER_STACK_CLEANED',flush=True)
