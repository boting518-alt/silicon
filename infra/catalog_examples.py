"""Optional isolated browser fixture only. Never invoked by API/Worker startup.

Uses production authorization/service functions and a deterministic UUID stream
before HTTP startup, so repeated visual runs have the same entity ordering.
All hardware and prices below are fictional, not supplier specifications.
"""
from uuid import UUID
from unittest.mock import patch
from silicon.identity.access import tenant_transaction
from silicon.catalog import service as s
from silicon.catalog.models import SkuInput,BomInput,RuleInput,PriceInput


def seed(engine,actor,tenant):
    counter=4000
    def next_id():
        nonlocal counter
        counter+=1
        return UUID(int=counter)
    with patch.object(s,'uuid4',next_id),tenant_transaction(engine,actor,tenant,'catalog.write','catalog-visual-fixture') as (db,access):
        s.guard(db,access,True)
        def sku(number,name,category='host',specs=None):
            return s.save_sku(db,access,SkuInput(number=number,name=name,category=category,manufacturer='虚构制造商',brand='硅屿测试品牌',brand_kind='own',specs=specs or {}))
        host=sku('DEMO-HOST','虚构双路准系统',specs={'socket':'DEMO-S1'})
        bare=sku('DEMO-BARE','虚构无电源准系统');psu=sku('DEMO-PSU','虚构 1200W 电源','psu',{'power_w':1200})
        rule=s.new_rule(db,access,RuleInput(name='虚构双路平台',source='虚构工程样例，非供应商认证',socket='DEMO-S1',memory_generation='DEMO-DDR5',power_budget_w=1000))
        for subject,name,lines in [(host,'虚构准系统 · 已含电源',[dict(sku_id=psu.id,quantity=2,required=True,charge_mode='included')]),(bare,'虚构准系统 · 不含电源',[])]:
            draft=s.save_bom(db,access,BomInput(name=name,kind='package',subject_sku_id=subject.id,rule_id=rule.id,lines=lines))
            s.publish_bom(db,draft.id,draft.version)
        book=s.save_price(db,access,PriceInput(name='虚构 2026 销售价格',scope='retail',currency='CNY',tax_included=True,source='虚构演示定价单，不是供应商报价',valid_from='2026-01-01T00:00:00Z',valid_to='2027-01-01T00:00:00Z',lines=[dict(sku_id=host.id,amount='10000.50')]))
        s.publish_price(db,book.id,book.version)
