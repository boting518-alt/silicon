"""TASK-010 disposable browser preconditions via prior-task APIs.
Seeds one signed order, three completed devices and fictional original costs.
No tests, shipments, acceptances or returns are seeded.
"""
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import text
from silicon.shared.db import make_engine
from test_delivery import setup

def seed(engine,database,actor,tenant,file_root,issuer):
    database.files=str(file_root);owner=make_engine(database.migration_url);other=UUID('22222222-2222-4222-8222-222222222222')
    try:
        with owner.begin() as db:db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:u,:i,:s,'虚构前置审批人') ON CONFLICT DO NOTHING"),{'u':other,'i':issuer,'s':str(other)})
        setup(engine,database,SimpleNamespace(user=actor,other=other,a=tenant,owner=owner),3)
    finally:owner.dispose()
