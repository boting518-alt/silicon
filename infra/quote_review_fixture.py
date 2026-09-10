"""Isolated TASK-005 review browser fixtures; never imported by product startup.

Explicit factory is test-only. Local files inject transport failures *after* the
real route completes, including committing a create whose success is not delivered.
No HTTP control endpoint, credential logging, auth bypass or database mock.
"""
import asyncio
import json
import os
from pathlib import Path
import time
from sqlalchemy import text
from silicon.main import create_app as product_app
from silicon.identity.access import tenant_transaction
from silicon.catalog import service as c
from silicon.catalog.models import SkuInput,PriceInput,BomInput
ROOT=Path(__file__).resolve().parents[1]
CONTROL=ROOT/'.tools/quote-review-control.json'
EVENTS=ROOT/'.tools/quote-review-events.jsonl'


def seed(engine,actor,tenant):
    with tenant_transaction(engine,actor,tenant,'catalog.write','review-fixture') as (db,a):
        c.guard(db,a,True)
        skus={r['number']:r['id'] for r in db.execute(text('SELECT id,number FROM catalog_skus')).mappings()}
        for number,name,category,specs in [('REVIEW-CPU','虚构可选不匹配 CPU','cpu',{'socket':'OTHER'}),('REVIEW-RAM','虚构可选不匹配内存','memory',{'memory_generation':'OTHER'})]:
            sku=c.save_sku(db,a,SkuInput(number=number,name=name,category=category,manufacturer='虚构制造商',brand='硅屿测试品牌',brand_kind='own',specs=specs));skus[number]=sku.id
            book=c.save_price(db,a,PriceInput(name='虚构审查价格',scope='retail',tax_included=True,valid_from='2026-01-01T00:00:00Z',valid_to='2027-01-01T00:00:00Z',source='虚构回归夹具',lines=[{'sku_id':sku.id,'amount':'2000.00'}]));c.publish_price(db,book.id,book.version)
        rule=db.scalar(text('SELECT id FROM catalog_rules ORDER BY id LIMIT 1'))
        lines=[dict(sku_id=skus[number],quantity=quantity,required=required,charge_mode=mode) for number,quantity,required,mode in [
            ('DEMO-CPU',1,True,'separate'),('REVIEW-CPU',1,False,'separate'),('DEMO-RAM',1,True,'separate'),('REVIEW-RAM',1,False,'separate'),('DEMO-PSU',2,False,'included'),('DEMO-SSD',1,True,'separate')]]
        bom=c.save_bom(db,a,BomInput(name='虚构回归 · 混合可选件',kind='bom',subject_sku_id=skus['DEMO-HOST'],rule_id=rule,lines=lines));c.publish_bom(db,bom.id,bom.version)


def create_app():
    if os.environ.get('SILICON_ENV')!='test' or os.environ.get('SILICON_BROWSER_QUOTE_REVIEW')!='1':
        raise RuntimeError('Review transport requires explicit isolated test startup')
    return ReviewTransport(product_app())


class ReviewTransport:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        path=scope.get('path');is_create=path=='/api/v1/quotes' and scope.get('method')=='POST'
        is_trial=path=='/api/v1/quotes/evaluate'
        control=json.loads(CONTROL.read_text()) if CONTROL.exists() else {}
        mode=control.get('mode')
        armed=(is_create and mode=='create-loss') or (is_trial and mode=='trial-failure')
        if not armed:return await self.app(scope,receive,send)
        CONTROL.write_text('{}') # consume once, before the request; no repeated drop on retry
        messages=[]
        async def buffer(message):messages.append(message)
        await self.app(scope,receive,buffer)
        status=next(m['status'] for m in messages if m['type']=='http.response.start')
        if status<200 or status>=300:
            for message in messages:await send(message)
            return
        result=json.loads(b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body'))
        event={'event':mode,'upstream_status':status}
        if is_create:event.update(draft_id=result['id'],version=result['version'])
        with EVENTS.open('a') as f:f.write(json.dumps(event)+'\n')
        if is_trial:
            deadline=time.monotonic()+7
            while time.monotonic()<deadline:
                value=json.loads(CONTROL.read_text()) if CONTROL.exists() else {}
                if value.get('mode')=='release':break
                await asyncio.sleep(.05)
        body=b'{"code":"TEST_DELIVERY_FAILURE"}'
        await send({'type':'http.response.start','status':503,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
        await send({'type':'http.response.body','body':body})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--arm',choices=['create-loss','trial-failure','release'],required=True);args=parser.parse_args()
    if not (ROOT/'.tools/browser-runtime.json').is_file():raise SystemExit('Start the isolated review browser stack first')
    temp=CONTROL.with_suffix('.tmp');temp.write_text(json.dumps({'mode':args.arm}));temp.replace(CONTROL)
    print('Armed local test transport: '+args.arm)
