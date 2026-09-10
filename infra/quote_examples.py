"""Explicit fictional quote fixtures, invoked only by the isolated browser harness."""
from uuid import UUID
from sqlalchemy import text
from silicon.identity.access import tenant_transaction
from silicon.catalog import service as c
from silicon.catalog.models import SkuInput,PriceInput
from silicon.quotes.service import guard,code_hash


def seed(engine,migration_engine,actor,tenant):
    with tenant_transaction(engine,actor,tenant,'catalog.write','quote-fixture') as (db,a):
        c.guard(db,a,True)
        for number,name,category,specs,value in [
            ('DEMO-CPU','虚构计算 CPU','cpu',{'socket':'DEMO-S1'},'9800.01'),
            ('DEMO-RAM','虚构 ECC 内存','memory',{'memory_generation':'DEMO-DDR5','capacity_gb':64},'1880.00'),
            ('DEMO-SSD','虚构系统盘','system_disk',{'capacity_gb':960},'980.00'),
            ('DEMO-GPU','虚构计算 GPU','gpu',{'capacity_gb':48},'28000.00'),
        ]:
            sku=c.save_sku(db,a,SkuInput(number=number,name=name,category=category,manufacturer='虚构制造商',brand='硅屿测试品牌',brand_kind='own',specs=specs))
            book=c.save_price(db,a,PriceInput(name='虚构 '+number+' 价格',scope='retail',tax_included=True,valid_from='2026-01-01T00:00:00Z',valid_to='2027-01-01T00:00:00Z',source='虚构开发种子，非供应商价格',lines=[{'sku_id':sku.id,'amount':value}]))
            c.publish_price(db,book.id,book.version)
        for number,value in [('DEMO-BARE','9000.00'),('DEMO-PSU','1800.00')]:
            id=db.scalar(text('SELECT id FROM catalog_skus WHERE number=:n'),{'n':number})
            book=c.save_price(db,a,PriceInput(name='虚构 '+number+' 价格',scope='retail',tax_included=True,valid_from='2026-01-01T00:00:00Z',valid_to='2027-01-01T00:00:00Z',source='虚构开发种子，非供应商价格',lines=[{'sku_id':id,'amount':value}]))
            c.publish_price(db,book.id,book.version)
    with tenant_transaction(migration_engine,actor,tenant,'quote.discount','discount-fixture') as (db,a):
        guard(db,a,True)
        db.execute(text('''INSERT INTO quote_discounts VALUES (:t,:id,:hash,'虚构开发优惠 5%',1,true,
            '2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','retail',true,500,0,5000)'''),
            {'t':tenant,'id':UUID('55555555-5555-4555-8555-555555555555'),'hash':code_hash(tenant,'DEMO5')})
