from datetime import date,datetime
from uuid import UUID
from typing import Literal
from pydantic import Field,AwareDatetime
from silicon.catalog.models import Input,Name
from silicon.assembly.models import View
from silicon.finance.models import Version,Money,SignedMoney
class ServiceWorkInput(Input):
    device_id:UUID
    number:Name
    fault:Name
    reported_at:AwareDatetime
    contact:Name
    mode:Literal['remote','onsite','return']
    priority:Literal['normal','urgent']='normal'
    manager_id:UUID
    planned_on:date
class ServiceDiagnose(Version):
    manager_id:UUID
    diagnosis:Name
    solution:Name
    warranty:Literal['pending','inside','outside','special']='pending'
    warranty_basis:str=Field(default='',max_length=1000)
class ServiceTransition(Version):
    reopen:bool=False
    state:Literal['working','waiting','verify','resolved','closed','cancelled']
    customer_confirmation:str=Field(default='',max_length=1000)
class ServiceReceive(Version):
    location_id:UUID
    performed_at:AwareDatetime
    appearance:Name
    accessories:Name
class ServiceReturnDevice(Version):
    receipt_id:UUID
    performed_at:AwareDatetime
    customer_confirmation:Name
class ServiceManualTestItem(Input):
    name:Name
    result:Literal['pass','fail']
class ServiceTestInput(Version):
    performed_at:AwareDatetime
    items:list[ServiceManualTestItem]=Field(min_length=1,max_length=50)
    report_ref:str=Field(default='',max_length=160)
class ServiceReserve(Version):
    sku_id:UUID
    quantity:int=Field(gt=0,le=1000)
    hours:int=Field(default=24,ge=1,le=168)
class ServiceIssue(Version):
    reservation_id:UUID
    quantity:int=Field(gt=0,le=1000)
class ServiceSpareReturn(Version):
    issue_id:UUID
    quantity:int=Field(gt=0,le=1000)
class ServiceReplace(Version):
    old_installation_id:UUID
    issue_id:UUID
    old_destination:Literal['customer','quarantine','dispose']
    location_id:UUID
    compatibility_basis:Name
    manual_compatibility_confirmed:Literal[True]
class ServiceReverseChange(Version):
    change_id:UUID
class RmaInput(Input):
    work_id:UUID
    expected_version:int=Field(ge=1)
    number:Name
    supplier_id:UUID
    manager_id:UUID
    supplier_number:Name
    fault:Name
    expected_on:date
    authorization_basis:str=Field(default='',max_length=1000)
    old_part_ids:list[UUID]=Field(min_length=1,max_length=100)
class RmaReturn(Version):
    line_id:UUID
    quantity:int=Field(gt=0,le=1000)
    kind:Literal['repair','replacement']
    serial:str=Field(default='',max_length=120)
    batch:str=Field(default='',max_length=120)
    location_id:UUID
    performed_at:AwareDatetime
    result:Name
class ServiceInspect(Version):
    return_id:UUID
    passed:bool
    disposition:Literal['customer','hold','scrap','own_spare']
    ownership_basis:Name
    unit_cost:SignedMoney|None=None
class ServiceCostInput(Version):
    kind:Literal['labor','other']
    person_id:UUID|None=None
    hours:SignedMoney|None=None
    amount:SignedMoney
    basis:Name
    occurred_on:date
class ServiceChargeInput(Version):
    kind:Literal['customer_service','supplier_repair']
    rma_id:UUID|None=None
    amount:Money
    basis_ref:Name
    number:Name
class ServiceWorkView(View):
    id:UUID
    number:str
    device_id:UUID
    line_id:UUID
    manager_id:UUID
    fault:str
    contact:str
    mode:str
    priority:str
    planned_on:date
    state:str
    version:int
    config_version:int
    diagnosis:str
    solution:str
    warranty:str
    warranty_basis:str
    customer_confirmation:str
    reported_at:datetime
    created_at:datetime
    serial:str
    customer_id:UUID
    customer_name:str
    order_id:UUID
    order_number:str
    contract_id:UUID
    custody:str
    receipts:list[dict]
    returns:list[dict]
    tests:list[dict]
    test_valid:bool
    history:list[dict]
    reservations:list[dict]
    issues:list[dict]
    changes:list[dict]
    old_parts:list[dict]
    rmas:list[dict]
    installations:list[dict]
    original_configuration:list[dict]
    material_cost:str|None=None
    labor_cost:str|None=None
    other_cost:str|None=None
    costs:list[dict]|None=None
class RmaView(View):
    id:UUID
    work_id:UUID
    number:str
    supplier_id:UUID
    manager_id:UUID
    supplier_number:str
    fault:str
    expected_on:date
    authorization_basis:str
    state:str
    version:int
    lines:list[dict]
    outside_quantity:int
    pending_quantity:int
    overdue:bool
class ServiceContext(View):
    permissions:list[str]
    people:list[dict]
class ServiceDevice(View):
    id:UUID
    serial:str
    customer_name:str
    customer_id:UUID
    order_number:str
    contract_id:UUID
    line_id:UUID
class ServiceChargeView(View):
    id:UUID
    work_id:UUID
    kind:str
    direction:str
    amount:str
    number:str
    basis_ref:str
    rma_id:UUID|None=None
class ServiceReconciliation(View):
    matches:bool
    differences:list[str]

class ServiceOptions(View):
    locations:list[dict]
    suppliers:list[dict]
    stock:list[dict]

class ServiceDispose(Version):
    old_part_id:UUID|None=None
    return_id:UUID|None=None
    disposition:Literal['customer','scrap']
    basis:Name
