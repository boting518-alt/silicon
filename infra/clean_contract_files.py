"""Tenant-scoped shared-file orphan cleanup; dry-run by default.

Requires a current authorized admin, isolated root and DATABASE_URL. Does not
remove live contract, procurement or import references. Missing schemas fail closed.
"""
import argparse,fcntl,os,time
from pathlib import Path
from uuid import UUID
from sqlalchemy import text
from silicon.settings import Settings
from silicon.shared.db import make_engine
from silicon.identity.access import tenant_transaction,audit
from silicon.publication.service import prelock
from silicon.quotes.service import guard
from silicon.contracts.storage import Store
from silicon.inventory.service import guard as inventory_guard

def clean(settings,actor,tenant,apply=False,minimum_age=86400):
    if minimum_age<86400:raise ValueError('Minimum grace period is one day')
    store=Store(str(Path(settings.file_root)/str(tenant)) if settings.file_root else '',settings.file_max_bytes)
    root=store.path(UUID(int=0)).parent
    engine=make_engine(settings.database_url);count=0
    try:
        with tenant_transaction(engine,actor,tenant,'contract.sign','file-cleanup') as (db,a):
            prelock(db,a);guard(db,a,True)
            # Global order: identities -> catalog(shared) -> quotes -> inventory.
            # Inventory never takes quote locks. Acquire all domain guards BEFORE
            # reading references so committed uploads cannot be missed.
            inventory_guard(db,a,True)
            references={str(id) for id in db.scalars(text('''
                SELECT storage_id FROM contract_files f
                WHERE state<>'deleted' OR EXISTS(
                    SELECT 1 FROM signed_files s WHERE s.tenant_id=f.tenant_id AND s.file_id=f.id)
                UNION SELECT storage_id FROM inv_attachments
                UNION SELECT storage_id FROM inv_imports
            '''))}
            # Missing tables / query errors propagate before any unlink. No fallback.
            if not root.exists():return 0
            for path in root.iterdir():
                if path.is_symlink() or not path.is_file():continue
                try:UUID(path.name)
                except ValueError:continue
                if path.name in references or time.time()-path.stat().st_mtime<minimum_age:continue
                with path.open('rb') as f:
                    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:continue
                    count+=1
                    if apply:path.unlink()
            audit(db,a.actor_id,a.tenant_id,'contract.orphan_cleanup',str(count),'allowed','file-cleanup')
    finally:engine.dispose()
    return count
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--actor',type=UUID,required=True);parser.add_argument('--tenant',type=UUID,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print('Eligible files:',clean(Settings.from_env(),args.actor,args.tenant,args.apply))
