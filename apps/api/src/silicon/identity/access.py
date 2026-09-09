"""Authorization boundary shared by HTTP, tenant services and workers.

Callers supply a server-authenticated actor; tenant IDs alone grant no authority.
Only transaction-local context is installed. Database roles remain a trusted server boundary.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4
from sqlalchemy import text


class Denied(Exception):
    def __init__(self, status=403, code='FORBIDDEN'):
        self.status, self.code = status, code
        super().__init__(code)


@dataclass(frozen=True)
class Access:
    actor_id: UUID
    tenant_id: UUID
    permissions: frozenset[str]
    data_scope: str

    def require(self, permission):
        if permission not in self.permissions:
            raise Denied()

    def fields(self, values: dict, protected: dict[str, str]):
        """Explicit allowlist required at the serializer; remove protected fields before output."""
        return {k: v for k, v in values.items() if k not in protected or protected[k] in self.permissions}

    def require_fields(self, values: dict, protected: dict[str, str]):
        """Reject forbidden writes instead of silently discarding attempted changes."""
        for name in values:
            if name in protected:
                self.require(protected[name])

    def owns(self, owner_id):
        return self.data_scope == 'all' or owner_id == self.actor_id


def authorize(db, actor_id, tenant_id):
    row = db.execute(text('SELECT * FROM lock_membership(:actor,:tenant)'),
                     {'actor': actor_id, 'tenant': tenant_id}).mappings().first()
    if row is None:
        raise Denied()
    permissions = db.scalars(text('SELECT permission FROM role_permissions WHERE role=:role'), {'role': row['role']})
    return Access(actor_id, tenant_id, frozenset(permissions), row['data_scope'])


def audit(db, actor_id, tenant_id, action, object_id, outcome, request_id):
    # No arbitrary body/metadata field: tokens, SQL and payloads cannot be passed accidentally.
    db.execute(text('''INSERT INTO audit_events(id,actor_id,tenant_id,action,object_id,outcome,request_id)
        VALUES (:id,:actor,:tenant,:action,:object,:outcome,:request)'''),
        dict(id=uuid4(), actor=actor_id, tenant=tenant_id, action=action,
             object=str(object_id), outcome=outcome, request=request_id))


@contextmanager
def tenant_transaction(engine, actor_id, tenant_id, permission, request_id, action='resource.access'):
    try:
        with engine.begin() as db:
            access = authorize(db, actor_id, tenant_id)
            access.require(permission)
            db.execute(text("SELECT set_config('silicon.tenant_id',:tenant,true), set_config('silicon.user_id',:actor,true)"),
                       {'tenant': str(tenant_id), 'actor': str(actor_id)})
            yield db, access
            audit(db, actor_id, tenant_id, action, tenant_id, 'allowed', request_id)
    except Denied:
        # A rollback must not erase the denial record.
        with engine.begin() as db:
            audit(db, actor_id, tenant_id, action, tenant_id, 'denied', request_id)
        raise
