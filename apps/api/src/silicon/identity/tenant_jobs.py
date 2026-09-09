"""Bounded tenant authorization check, no payload or business handler.

Scheduler envelopes are global control-plane metadata. Tenant context is persisted only
by an authorized service, then revalidated at execution (including revocation).
"""
from uuid import uuid4
from sqlalchemy import text
from silicon.identity.access import Denied, audit, authorize, tenant_transaction


def enqueue(engine, actor_id, tenant_id, dedupe_key, request_id):
    if not dedupe_key or len(dedupe_key)>128:
        raise ValueError('dedupe key must contain 1–128 characters')
    with tenant_transaction(engine,actor_id,tenant_id,'job.run',request_id,'job.enqueue') as (db, access):
        key = f'tenant:{tenant_id}:{actor_id}:identity.check:{dedupe_key}'
        result = db.scalar(text('''INSERT INTO jobs(id,kind,dedupe_key,tenant_id,actor_id,request_id)
            VALUES (:id,'identity.check',:key,:tenant,:actor,:request)
            ON CONFLICT(dedupe_key) DO NOTHING RETURNING id'''),
            dict(id=uuid4(),key=key,tenant=access.tenant_id,actor=access.actor_id,request=request_id))
        return result or db.scalar(text('SELECT id FROM jobs WHERE dedupe_key=:key'),{'key':key})


class _LeaseExpired(Exception):
    pass


def execute(engine, job):
    try:
        return _execute(engine, job)
    except _LeaseExpired:
        return False


def _execute(engine, job):
    with engine.begin() as db:
        current = db.execute(text('''SELECT * FROM jobs WHERE id=:id AND lease_token=:lease_token
            AND status='running' AND lease_until>clock_timestamp() FOR UPDATE'''),job).mappings().first()
        if current is None:
            return False
        allowed = False
        try:
            if current['kind'] != 'identity.check' or current['tenant_id'] is None or current['actor_id'] is None:
                raise Denied()
            access = authorize(db,current['actor_id'],current['tenant_id'])
            access.require('job.run')
            db.execute(text("SELECT set_config('silicon.tenant_id',:tenant,true),set_config('silicon.user_id',:actor,true)"),
                       {'tenant':str(access.tenant_id),'actor':str(access.actor_id)})
            allowed = True
        except Denied:
            pass
        audit(db,current['actor_id'],current['tenant_id'],'job.execute',current['id'],
              'allowed' if allowed else 'denied',current['request_id'] or str(current['id']))
        # Audit and completion are atomic and fenced by the locked, current lease token.
        changed = db.execute(text('''UPDATE jobs SET status=:status,error_code=:error,
            result=CASE WHEN :allowed THEN '{"message":"authorization checked"}'::jsonb ELSE NULL END,
            completed_at=now(),lease_token=NULL,lease_until=NULL WHERE id=:id
            AND lease_token=:token AND lease_until>clock_timestamp()'''),
            dict(id=job['id'],token=job['lease_token'],allowed=allowed,status='completed' if allowed else 'failed',
                 error=None if allowed else 'TENANT_AUTHORIZATION_DENIED')).rowcount
        if changed != 1:
            raise _LeaseExpired()  # Roll back the audit together with the stale completion.
        return allowed
