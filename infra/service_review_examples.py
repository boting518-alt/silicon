"""R1 browser-only fictional prerequisites via real APIs.
Seeds a two-piece old installation, replacement and sent RMA; no returns,
inspections or final dispositions. Browser performs the regression itself.
"""
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import text
from silicon.shared.db import make_engine
from test_service_disposition import batch_rma


def seed(engine,database,actor,tenant,file_root,issuer):
    database.files=str(file_root)
    owner=make_engine(database.migration_url)
    other=UUID('22222222-2222-4222-8222-222222222222')
    try:
        with owner.begin() as db:
            db.execute(text("INSERT INTO identity_users(id,issuer,subject,display_name) VALUES (:u,:i,:s,'虚构前置审批人') ON CONFLICT DO NOTHING"),{'u':other,'i':issuer,'s':str(other)})
        w,r,loc=batch_rma(engine,database,SimpleNamespace(user=actor,other=other,a=tenant,owner=owner))
        print('R1_FIXTURE_READY: R1-BATCH / R1-RMA, two pieces at supplier, no return/hold/disposition seeded',flush=True)
    finally:
        owner.dispose()
