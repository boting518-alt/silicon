from concurrent.futures import ThreadPoolExecutor
import os
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from silicon.main import create_app
from silicon.settings import Settings
from silicon.shared.db import make_engine
from silicon.shared.jobs import enqueue_smoke, claim, heartbeat, complete, fail, run_once
from conftest import ROOT, run


def test_empty_migration_and_runtime_role(database, engine):
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == '0001_platform'
        role = db.execute(text("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user")).one()
        assert tuple(role) == (False, False, False, False)
        assert db.scalar(text("SELECT tableowner FROM pg_tables WHERE tablename='jobs'")) == 'silicon_migrator'
        assert db.scalar(text("SELECT count(*) FROM outbox_events")) == 0
    with pytest.raises(ProgrammingError):
        with engine.begin() as db:
            db.execute(text("CREATE TABLE must_not_create(id integer)"))


def test_health_and_ready(database):
    with TestClient(create_app(Settings(database.url, 'test'))) as client:
        assert client.get('/api/v1/health').json() == {'status':'ok'}
        ready = client.get('/api/v1/ready')
        assert ready.status_code == 200 and ready.json() == {'status':'ready'}
        assert ready.headers['x-request-id']


def test_ready_requires_migration(database):
    owner = make_engine(database.migration_url)
    try:
        with owner.begin() as db:
            db.execute(text("UPDATE alembic_version SET version_num='0000_baseline'"))
        with TestClient(create_app(Settings(database.url, 'test'))) as client:
            assert client.get('/api/v1/ready').status_code == 503
            assert client.get('/api/v1/health').status_code == 200
    finally:
        with owner.begin() as db:
            db.execute(text("UPDATE alembic_version SET version_num='0001_platform'"))
        owner.dispose()


def test_enqueue_deduplication_and_worker_restart(database, engine):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: enqueue_smoke(engine,key), range(4)))
    assert len(set(ids)) == 1
    first = run(sys.executable, 'apps/worker/main.py', '--once', cwd=ROOT, env=database.env)
    second = run(sys.executable, 'apps/worker/main.py', '--once', cwd=ROOT, env=database.env)
    assert first.returncode == second.returncode == 0
    with engine.connect() as db:
        row=db.execute(text('SELECT status, attempts, result, completed_at FROM jobs')).one()
        assert row.status == 'completed' and row.attempts == 1
        assert row.result == {'message':'smoke completed'} and row.completed_at


def test_concurrent_claim_single_winner(engine):
    enqueue_smoke(engine, str(uuid4()))
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: claim(engine),range(4)))
    assert sum(j is not None for j in jobs) == 1


def test_locked_job_does_not_block_another_claim(engine):
    first=enqueue_smoke(engine,'first'); second=enqueue_smoke(engine,'second')
    with engine.begin() as db:
        db.execute(text('SELECT id FROM jobs WHERE id=:id FOR UPDATE'),{'id':first})
        job=claim(engine)
        assert job['id']==second


def test_expired_lease_fences_stale_worker(engine):
    enqueue_smoke(engine,'lease')
    old=claim(engine)
    assert heartbeat(engine,old)
    with engine.begin() as db:
        db.execute(text("UPDATE jobs SET lease_until=now()-interval '1 second'"))
    new=claim(engine)
    assert new['id']==old['id'] and new['lease_token']!=old['lease_token']
    assert not heartbeat(engine,old) and not complete(engine,old) and not fail(engine,old)
    assert complete(engine,new)
    assert not complete(engine,new)


def test_crash_exhaustion_and_failure_retry(engine):
    enqueue_smoke(engine,'crash')
    claim(engine)
    with engine.begin() as db:
        db.execute(text("UPDATE jobs SET attempts=max_attempts, lease_until=now()-interval '1 second'"))
    assert claim(engine) is None
    with engine.connect() as db:
        assert db.scalar(text("SELECT status FROM jobs WHERE dedupe_key='crash'"))=='failed'
    enqueue_smoke(engine,'unsupported')
    with engine.begin() as db:
        db.execute(text("UPDATE jobs SET kind='unknown', max_attempts=2 WHERE dedupe_key='unsupported'"))
    assert run_once(engine)
    assert claim(engine) is None  # retry delay is enforced
    with engine.begin() as db:
        db.execute(text("UPDATE jobs SET available_at=now() WHERE dedupe_key='unsupported'"))
    assert run_once(engine)
    with engine.connect() as db:
        row=db.execute(text("SELECT status,attempts,error_code FROM jobs WHERE dedupe_key='unsupported'")).one()
        assert tuple(row)==('failed',2,'UNSUPPORTED_JOB_KIND')


def test_http_database_stop_recovery_and_long_running_worker(database, engine):
    # Real HTTP + real independent process, not TestClient or a mock database outage.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    api=subprocess.Popen([sys.executable,'-m','uvicorn','silicon.main:create_app','--factory','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=database.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    worker=None
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=8,trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get('/api/v1/ready').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.1)
            else:pytest.fail('API did not become ready')
            database.stop()
            try:
                assert client.get('/api/v1/health').status_code==200
                response=client.get('/api/v1/ready')
                assert response.status_code==503
                body=response.json()
                assert set(body)=={'code','message','request_id'}
                assert body['code']=='DATABASE_NOT_READY'
                assert body['request_id']==response.headers['x-request-id']
                for secret in ['silicon_app','postgresql','SELECT','Traceback']:
                    assert secret not in response.text
                failed=subprocess.run([sys.executable,'apps/worker/main.py','--once'],cwd=ROOT,env=database.env,capture_output=True,text=True)
                assert failed.returncode==1
                assert 'worker_database_unavailable' in failed.stderr
                assert 'postgresql' not in failed.stderr
            finally:
                database.start()
            assert client.get('/api/v1/ready').status_code==200
            enqueue_smoke(engine,'daemon')
            worker=subprocess.Popen([sys.executable,'apps/worker/main.py'],cwd=ROOT,env=database.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(100):
                with engine.connect() as db:
                    if db.scalar(text("SELECT status FROM jobs WHERE dedupe_key='daemon'"))=='completed':break
                time.sleep(.1)
            else:pytest.fail('worker did not persist completion')
            worker.terminate();worker.wait(timeout=8)
            assert worker.returncode==0
            run(sys.executable,'apps/worker/main.py','--once',cwd=ROOT,env=database.env)
            database.stop();database.start()
            with engine.connect() as db:
                assert db.scalar(text("SELECT attempts FROM jobs WHERE dedupe_key='daemon'"))==1
                assert db.scalar(text("SELECT status FROM jobs WHERE dedupe_key='daemon'"))=='completed'
    finally:
        if worker and worker.poll() is None:worker.terminate();worker.wait(timeout=8)
        api.terminate();api.wait(timeout=8)


def test_production_mode_disabled():
    with pytest.raises(ValueError, match='production identity'):
        Settings('postgresql+psycopg://unused@localhost/unused','production')
