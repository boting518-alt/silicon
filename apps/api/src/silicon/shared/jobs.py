"""Global scheduler envelopes. Tenant jobs enter through identity.tenant_jobs only."""
from uuid import uuid4
from sqlalchemy import text


def enqueue_smoke(engine, dedupe_key: str):
    if not dedupe_key or len(dedupe_key) > 128:
        raise ValueError("dedupe key must contain 1–128 characters")
    with engine.begin() as db:
        job_id = db.scalar(text("""
            INSERT INTO jobs (id, kind, dedupe_key) VALUES (:id, 'smoke', :key)
            ON CONFLICT (dedupe_key) DO NOTHING RETURNING id
        """), {"id": uuid4(), "key": dedupe_key})
        if job_id is None:
            job_id = db.scalar(text("SELECT id FROM jobs WHERE dedupe_key = :key"), {"key": dedupe_key})
        return job_id


def claim(engine, lease_seconds=30):
    if lease_seconds <= 0:
        raise ValueError("lease must be positive")
    with engine.begin() as db:
        # Lock a bounded cleanup batch without waiting behind another worker.
        # The materialized selection keeps those locks through the update/claim transaction.
        db.execute(text("""
            WITH exhausted AS MATERIALIZED (
                SELECT id FROM jobs
                WHERE status='running' AND lease_until < now() AND attempts >= max_attempts
                ORDER BY lease_until, id FOR UPDATE SKIP LOCKED LIMIT 100
            )
            UPDATE jobs SET status='failed', error_code='LEASE_EXHAUSTED',
                lease_token=NULL, lease_until=NULL
            FROM exhausted WHERE jobs.id=exhausted.id
        """))
        row = db.execute(text("""
            SELECT id FROM jobs
            WHERE attempts < max_attempts AND
                ((status='queued' AND available_at <= now()) OR
                 (status='running' AND lease_until < now()))
            ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
        """)).first()
        if row is None:
            return None
        return dict(db.execute(text("""
            UPDATE jobs SET status='running', attempts=attempts+1,
                lease_token=:token, lease_until=now()+make_interval(secs => :seconds), error_code=NULL
            WHERE id=:id RETURNING id, kind, lease_token, attempts, tenant_id, actor_id
        """), {"id": row.id, "token": uuid4(), "seconds": lease_seconds}).mappings().one())


def heartbeat(engine, job, lease_seconds=30):
    with engine.begin() as db:
        return db.execute(text("""
            UPDATE jobs SET lease_until=now()+make_interval(secs => :seconds)
            WHERE id=:id AND lease_token=:lease_token AND status='running' AND lease_until > now()
        """), {**job, "seconds": lease_seconds}).rowcount == 1


def complete(engine, job):
    with engine.begin() as db:
        return db.execute(text("""
            UPDATE jobs SET status='completed', result='{"message":"smoke completed"}'::jsonb,
                completed_at=now(), lease_token=NULL, lease_until=NULL
            WHERE id=:id AND lease_token=:lease_token AND status='running' AND lease_until > now()
        """), job).rowcount == 1


def fail(engine, job):
    with engine.begin() as db:
        return db.execute(text("""
            UPDATE jobs SET status=CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                available_at=now()+make_interval(secs => LEAST(60, power(2, attempts)::int)),
                error_code='UNSUPPORTED_JOB_KIND', lease_token=NULL, lease_until=NULL
            WHERE id=:id AND lease_token=:lease_token AND status='running' AND lease_until > now()
        """), job).rowcount == 1


def run_once(engine):
    job = claim(engine)
    if job is None:
        return False
    # Only a bounded, deterministic handler; no external requests or arbitrary payloads.
    if job['kind'] == 'identity.check' or job['tenant_id'] is not None or job['actor_id'] is not None:
        from silicon.identity.tenant_jobs import execute
        execute(engine, job)
    elif job['kind'] != 'smoke':
        fail(engine, job)
    elif heartbeat(engine, job):
        complete(engine, job)
    return True
