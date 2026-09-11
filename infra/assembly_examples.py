"""Disposable TASK-009 browser preconditions; no work/reservation/issue is seeded.
Sales contract and original inventory are fictional prior-task API fixtures.
"""
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import text
from silicon.shared.db import make_engine
from test_assembly import prepared
from test_contracts import client
from test_inventory import post,ok

def seed(engine,database,actor,tenant,file_root,issuer):
    database.files=str(file_root);owner=make_engine(database.migration_url);other=UUID('22222222-2222-4222-8222-222222222222')
    try:
        with owner.begin() as db:
            db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:u,:i,:s,'虚构前置审批人') ON CONFLICT DO NOTHING"),{'u':other,'i':issuer,'s':str(other)})
        i=SimpleNamespace(user=actor,other=other,a=tenant,owner=owner)
        prepared(engine,database,i,independent=True)
        with client(engine,database,actor,tenant) as c:ok(post(c,'/opening/configure',{'cutoff':'2026-01-01','open':False,'reason':'关闭虚构前置期初','expected_version':1}))
    finally:owner.dispose()
