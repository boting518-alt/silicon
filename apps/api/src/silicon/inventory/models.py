from pydantic import BaseModel,ConfigDict,Field
class Model(BaseModel):
    model_config=ConfigDict(extra='forbid')
class SupplierInput(Model):
    name:str=Field(min_length=1,max_length=160)
    address:str=Field(default='',max_length=500)
    contact:str=Field(default='',max_length=160)
    phone:str=Field(default='',max_length=160)
    enabled:bool=True
    expected_version:int=0
from typing import Literal
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID
from pydantic import field_validator
class InventoryVersion(Model):
    expected_version:int=Field(ge=0)
    confirmed:bool=False
    reason:str=Field(default='',max_length=500)
class Tracking(Model):
    mode:Literal['sn','batch']
    unit:Literal['piece']='piece'
    expected_version:int=0
class ContractLine(Model):
    sku_id:UUID
    quantity:int=Field(gt=0,le=1000000,strict=True)
    unit_price:Decimal=Field(ge=0,max_digits=18,decimal_places=2)
    tax_basis:Literal['included','excluded','unconfirmed']='unconfirmed'
    due_date:date
class PurchaseContract(Model):
    expected_version:int=0
    number:str=Field(min_length=1,max_length=60)
    supplier_id:UUID
    buyer:str=Field(min_length=1,max_length=500)
    manager_id:UUID
    signing_date:date
    currency:Literal['CNY']='CNY'
    notes:str=Field(default='',max_length=1000)
    lines:list[ContractLine]=Field(min_length=1,max_length=100)
class OrderLine(Model):
    contract_line_id:UUID
    quantity:int=Field(gt=0,le=1000000,strict=True)
    sales_order_id:UUID|None=None
    project_id:UUID|None=None
class PurchaseOrder(Model):
    number:str=Field(min_length=1,max_length=60)
    contract_id:UUID
    supplier_confirmation:str=Field(default='',max_length=100)
    lines:list[OrderLine]=Field(min_length=1,max_length=100)
class Cancel(Model):
    expected_version:int
    line_id:UUID
    quantity:int=Field(gt=0,strict=True)
    reason:str=Field(min_length=1,max_length=500)
    confirmed:bool
class Location(Model):
    warehouse:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=100)
class ReceiptLine(Model):
    order_line_id:UUID
    quantity:int=Field(gt=0,le=10000,strict=True)
    serials:list[str]=Field(default_factory=list,max_length=10000)
    batch:str=Field(default='',max_length=100)
    cost_status:Literal['unknown','provisional','confirmed']='unknown'
    unit_cost:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=2)
    deductible_tax:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=2)
    cost_basis:str=Field(default='',max_length=500)
class Receipt(Model):
    order_id:UUID
    received_on:date
    location_id:UUID
    lines:list[ReceiptLine]=Field(min_length=1,max_length=100)
class Transfer(Model):
    layer_id:UUID
    source_location_id:UUID
    source_state:Literal['pending','qualified','quarantine']
    target_location_id:UUID
    target_state:Literal['pending','qualified','quarantine']
    quantity:int=Field(gt=0,le=1000000,strict=True)
    expected_version:int
    confirmed:bool
    reason:str=Field(min_length=1,max_length=500)
class OpeningConfig(Model):
    cutoff:date
    open:bool
    reason:str=Field(min_length=1,max_length=500)
    expected_version:int
class CSVInput(Model):
    csv:str=Field(min_length=1,max_length=1000000)
class Amendment(Model):
    line_id:UUID
    extra_quantity:int=Field(gt=0,le=1000000,strict=True)
    reason:str=Field(min_length=1,max_length=500)
    expected_version:int
    confirmed:bool
# Response contracts keep money as exact strings; unset protected fields are omitted.
from typing import Any
class SupplierView(SupplierInput):
    id:UUID
    version:int
class LocationView(Location):
    id:UUID
class ContractLineView(Model):
    id:UUID
    sku_id:UUID
    quantity:int
    unit_price:str|None=None
    tax_basis:str
    due_date:date
class ContractView(Model):
    id:UUID
    number:str
    supplier_id:UUID
    buyer:str
    manager_id:UUID
    signing_date:date
    currency:str
    notes:str
    state:str
    version:int
    lines:list[ContractLineView]
    snapshot:dict[str,Any]|None=None
    amendments:list[dict[str,Any]]=Field(default_factory=list)
class OrderLineView(Model):
    id:UUID
    contract_line_id:UUID
    sku_id:UUID
    quantity:int
    received:int
    cancelled:int
    unit_price:str|None=None
    tax_basis:str
    due_date:date
    sales_order_id:UUID|None=None
    project_id:UUID|None=None
class OrderView(Model):
    id:UUID
    number:str
    contract_id:UUID
    supplier_confirmation:str
    state:str
    version:int
    lines:list[OrderLineView]
class ReceiptLineView(Model):
    id:UUID
    order_line_id:UUID
    quantity:int
    serials:list[str]
    batch:str
    cost_status:str|None=None
    unit_cost:str|None=None
    deductible_tax:str|None=None
    cost_basis:str|None=None
class ReceiptView(Model):
    id:UUID
    order_id:UUID
    location_id:UUID
    received_on:date
    state:str
    version:int
    lines:list[ReceiptLineView]
    movement_id:UUID|None=None
class StockItem(Model):
    reserved_quantity:int|None=None
    stage:str="material"
    layer_id:UUID
    sku_id:UUID
    location_id:UUID
    state:str
    balance:int
    ownership:str
    version:int
    unit_id:UUID|None=None
    serial_raw:str|None=None
    batch:str|None=None
    warehouse:str
    location_name:str
    number:str
    name:str
    source_movement:UUID
    created_at:datetime
    unit_cost:str|None=None
    deductible_tax:str|None=None
    cost_status:str|None=None
    cost_basis:str|None=None
    tax_basis:str
    currency:str
class StockView(Model):
    items:list[StockItem]
    available_quantity:int
    unit:str
    reservation_state:str
    as_of:datetime
    known_cost:str|None=None
    total_cost:str|None=None
    unknown_quantity:int|None=None
    cost_complete:bool|None=None
class EntryView(Model):
    layer_id:UUID
    location_id:UUID
    state:str
    quantity:int
class MovementView(Model):
    id:UUID
    kind:str
    reason:str
    actor_id:UUID
    request_id:str
    effective_on:date
    created_at:datetime
    receipt_id:UUID|None=None
    reverse_of:UUID|None=None
    entries:list[EntryView]
# Database-only keys never become public fields.
for _type in [SupplierView,LocationView,ContractLineView,ContractView,OrderLineView,OrderView,ReceiptLineView,ReceiptView,StockItem,StockView,EntryView,MovementView]:
    _type.model_config=ConfigDict(extra='ignore');_type.model_rebuild(force=True)
