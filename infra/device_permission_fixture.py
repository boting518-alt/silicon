"""TASK-010 R1 browser-only permission fixture; requires live disposable browser stack.

Never accepts a database URL. Changes only fictional admin delivery.read in the
repository's active browser fixture; not an application or production endpoint.
"""
import argparse,json
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import make_url
from silicon.shared.db import make_engine

p=argparse.ArgumentParser();p.add_argument('action',choices=['revoke','restore']);args=p.parse_args()
root=Path(__file__).resolve().parents[1]
runtime=json.loads((root/'.tools/browser-runtime.json').read_text())
files=Path(runtime['file_root']).resolve()
assert files.parent.name.startswith('silicon-browser-') and files.is_dir()
assert files.parent.parent==Path('/tmp').resolve()
url=make_url(runtime['migration_url'])
assert url.host=='127.0.0.1' and url.database=='silicon' and url.username=='silicon_migrator'
markers=[p for p in Path('/tmp').glob('silicon-test-*/data/postmaster.pid') if p.read_text().splitlines()[3]==str(url.port)]
assert len(markers)==1, 'Refuse a database without a matching disposable PG marker'
owner=make_engine(runtime['migration_url'])
try:
    with owner.begin() as db:
        assert db.execute(text("SELECT name FROM tenants WHERE id=:t"),{'t':runtime['tenant_a']}).scalar()=='虚构企业 A'
        if args.action=='revoke':db.execute(text("DELETE FROM role_permissions WHERE role='admin' AND permission='delivery.read'"))
        else:db.execute(text("INSERT INTO role_permissions VALUES ('admin','delivery.read') ON CONFLICT DO NOTHING"))
        print(json.dumps({'fixture':'disposable browser PG','action':args.action,'delivery_read':bool(db.execute(text("SELECT 1 FROM role_permissions WHERE role='admin' AND permission='delivery.read'")).scalar())}))
finally:owner.dispose()
