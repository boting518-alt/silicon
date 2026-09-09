"""Explicit migration-role provisioning for the fictional local Keycloak user.

No HTTP shortcut, password handling or production path. Login still requires Keycloak.
"""
import os
from uuid import UUID,uuid4
from sqlalchemy import text
from silicon.settings import Settings
from silicon.shared.db import make_engine
from keycloak_realm import SUBJECT

settings=Settings.from_env()
if settings.environment!='development' or settings.oidc_issuer!='https://localhost:8443/realms/silicon-dev':
    raise SystemExit('Only the documented loopback development realm is supported')
engine=make_engine(os.environ['MIGRATION_DATABASE_URL'])
with engine.begin() as db:
    db.execute(text('''INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:id,:issuer,:subject,'虚构用户甲')
      ON CONFLICT(issuer,subject) DO NOTHING'''),dict(id=uuid4(),issuer=settings.oidc_issuer,subject=SUBJECT))
    user=db.scalar(text('SELECT id FROM identity_users WHERE issuer=:issuer AND subject=:subject'),dict(issuer=settings.oidc_issuer,subject=SUBJECT))
    for tenant,name,role in [('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','虚构企业 A','admin'),('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','虚构企业 B','member')]:
        db.execute(text('INSERT INTO tenants VALUES (:id,:name) ON CONFLICT(id) DO NOTHING'),dict(id=UUID(tenant),name=name))
        db.execute(text('''INSERT INTO memberships(tenant_id,user_id,role) VALUES (:t,:u,:r)
          ON CONFLICT(tenant_id,user_id) DO NOTHING'''),dict(t=UUID(tenant),u=user,r=role))
engine.dispose()
print('Fictional development memberships provisioned; authenticate through Keycloak.')
