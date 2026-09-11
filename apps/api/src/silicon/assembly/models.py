from datetime import date
from uuid import UUID
from pydantic import Field
from silicon.catalog.models import Input
class WorkInput(Input):
    order_id:UUID
    product_sku_id:UUID
    manager_id:UUID
    planned_on:date
    notes:str=Field(default='',max_length=2000)

from pydantic import AwareDatetime,model_validator
from typing import Literal
class Version(Input):
    expected_version:int=Field(ge=1)
    confirmed:Literal[True]
    reason:str=Field(default='确认',min_length=1,max_length=1000)
class Reserve(Version):
    requirement_id:UUID
    quantity:int=Field(ge=1,le=1000000,strict=True)
    expires_at:AwareDatetime|None=None
    duration_hours:int|None=Field(default=None,ge=1,le=8760,strict=True)
    @model_validator(mode='after')
    def expiry_choice(self):
        if (self.expires_at is None)==(self.duration_hours is None):raise ValueError('choose expiry or duration')
        return self

class IssueLine(Input):
    reservation_id:UUID
    quantity:int=Field(ge=1,le=1000000,strict=True)
class Issue(Version):
    lines:list[IssueLine]=Field(min_length=1,max_length=100)
class Complete(Version):
    correction_of:UUID|None=None
    serial:str=Field(min_length=1,max_length=120)
    location_id:UUID
class Reverse(Version):
    movement_id:UUID

from datetime import datetime
from pydantic import ConfigDict
from silicon.catalog.models import Sku,TechnicalLine
class View(Input):
    model_config=ConfigDict(extra='ignore')
class RequirementView(View):
    id:UUID
    sku_id:UUID
    quantity:int
    position:str
    reserved:int
    issued:int
    missing:int
class ReservationView(View):
    id:UUID
    requirement_id:UUID
    layer_id:UUID
    location_id:UUID
    quantity:int
    consumed:int
    released:int
    expires_at:datetime
class IssueView(View):
    id:UUID
    movement_id:UUID
class DeviceRef(View):
    id:UUID
    number:str
    movement_id:UUID
class CompletionView(View):
    id:UUID
    device_id:UUID
    layer_id:UUID
    movement_id:UUID
    completed_at:datetime
    correction_of:UUID|None=None
    reversed_by:UUID|None=None
class EventView(View):
    id:UUID
    action:str
    reason:str
    actor_id:UUID
    created_at:datetime
class WorkView(View):
    id:UUID
    order_id:UUID
    product_sku_id:UUID
    manager_id:UUID
    planned_on:date
    notes:str
    state:str
    version:int
    wip_location_id:UUID
    requirements:list[RequirementView]
    reservations:list[ReservationView]
    included:list[TechnicalLine]
    checks:list[str]
    issues:list[IssueView]
    devices:list[DeviceRef]
    completions:list[CompletionView]=Field(default_factory=list)
    history:list[EventView]
    wip_cost:str|None=None
class SalesSourceView(View):
    id:UUID
    number:str
    quantity:int
    host:Sku
class InstallationView(View):
    completion_id:UUID
    id:UUID
    layer_id:UUID
    unit_id:UUID|None=None
    sku_id:UUID
    sku_number:str
    quantity:int
    position:str
    serial:str|None=None
    batch:str|None=None
    installed_at:datetime
    removed_at:datetime|None=None
    correction_id:UUID|None=None
    source_movement:UUID
    source_line:UUID|None=None
class DeviceInventoryView(View):
    location_id:UUID
    state:str
    quantity:int
class DeviceView(View):
    id:UUID
    number:str
    work_id:UUID
    inventory_unit_id:UUID
    layer_id:UUID
    movement_id:UUID
    product:Sku
    serial:str
    completed_at:datetime
    order_id:UUID
    order_number:str
    contract_id:UUID
    contract_number:str
    quote_version_id:UUID
    customer_id:UUID
    customer_name:str
    project_id:UUID
    reversed:bool
    inventory:list[DeviceInventoryView]
    completion_id:UUID
    completions:list[CompletionView]
    installations:list[InstallationView]
    cost:str|None=None
    cost_scope:str
    delivery_state:str

class WorkEdit(Input):
    expected_version:int=Field(ge=1)
    product_sku_id:UUID
    manager_id:UUID
    planned_on:date
    notes:str=Field(default='',max_length=2000)
class ReconciliationView(View):
    work_id:UUID
    issued_quantity:int
    wip_quantity:int
    completed_quantity:int
    issued_cost:str|None=None
    wip_cost:str|None=None
    finished_cost:str|None=None
    matches:bool
    differences:list[str]
