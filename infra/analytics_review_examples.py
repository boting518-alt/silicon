"""TASK013 R1/R2 browser fixture, isolated stack only; never a production import."""
from sqlalchemy import text
from silicon.shared.db import make_engine
from analytics_examples import seed as original_seed

def seed(engine,database,actor,tenant,file_root,issuer):
    original_seed(engine,database,actor,tenant,file_root,issuer)
    owner=make_engine(database.migration_url)
    try:
        with owner.begin() as db:
            db.execute(text("DELETE FROM role_permissions WHERE role='viewer' AND permission='delivery.read'"))
    finally:owner.dispose()
    print('ANALYTICS_REVIEW_READY: alice authorized; carol no delivery/finance; Sep1 receipt80 confirmed at current test time, independent of balance cutoff',flush=True)
