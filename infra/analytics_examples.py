"""TASK-013 fictional, isolated browser analytics facts via production commands.
Never imported by the production application. No external financial operation.
"""
from sqlalchemy import text
from silicon.shared.db import make_engine
from service_review_examples import seed as service_seed
from test_contracts import client
from test_finance import get,new_plan,new_cash,alloc,ok
from test_service_disposition import return_one,hold
from test_service import get as service_get

def seed(engine,database,actor,tenant,file_root,issuer):
    service_seed(engine,database,actor,tenant,file_root,issuer)
    with client(engine,database,actor,tenant) as c:
        source=next(x for x in get(c,'sources') if x['direction']=='receivable')
        p=new_plan(c,source,'100','虚构首期',due_date='2026-09-01')
        new_plan(c,source,'50','虚构质保金',due_date=None,retention=True,release_condition='虚构验收一年后')
        cash=new_cash(c,source,'80',purpose='advance',occurred_at='2026-09-01T00:00:00Z')
        ok(alloc(c,cash,(p,'40')))
        w=service_get(c,'/works')[0];r=w['rmas'][0]
        locations=ok(c.get('/api/v1/inventory/locations'));loc=locations[0]
        r,rr=return_one(c,r,loc);hold(c,r,rr)
    owner=make_engine(database.migration_url)
    try:
        with owner.begin() as db:
            # Fixture-only entry and existing non-finance read permissions. No
            # production default role is broadened by the analytics migration.
            db.execute(text("INSERT INTO role_permissions(role,permission) SELECT 'viewer',permission FROM role_permissions WHERE role='admin' AND permission IN('analytics.read','contract.read','delivery.read','inventory.read','catalog.read') ON CONFLICT DO NOTHING"))
    finally:owner.dispose()
    print(f'ANALYTICS_FIXTURE_READY: fictional signed{source["amount"]}, receivable110 (50 unreleased), receipt80, allocated40, RMA one outside / one held; no external actions',flush=True)
