"""TASK-011 fictional browser prerequisites, through existing domain APIs.
Creates signed sales/order/device and an active purchase contract/order.
No finance plans, cash, invoices, refunds or allocations are seeded.
"""
from types import SimpleNamespace
from uuid import UUID
from delivery_examples import seed as delivery_seed
from test_contracts import client
from test_inventory import setup_purchase

def seed(engine,database,actor,tenant,file_root,issuer):
    delivery_seed(engine,database,actor,tenant,file_root,issuer)
    i=SimpleNamespace(user=actor,other=UUID('22222222-2222-4222-8222-222222222222'),a=tenant)
    with client(engine,database,actor,tenant) as c:setup_purchase(c,i)
