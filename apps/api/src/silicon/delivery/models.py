from uuid import UUID
from typing import Literal
from pydantic import Field,AwareDatetime
from silicon.catalog.models import Input,Name
from silicon.assembly.models import Version
class TestItem(Input):
    name:Name
    result:Literal['pass','fail']
class TestInput(Input):
    expected_version:int=Field(ge=1)
    completion_id:UUID
    items:list[TestItem]=Field(min_length=1,max_length=100)
    performed_at:AwareDatetime
    notes:str=Field(default='',max_length=2000)
    report_ref:str=Field(default='',max_length=160)
class ShipmentInput(Input):
    order_id:UUID
    device_ids:list[UUID]=Field(min_length=1,max_length=100)
    recipient:Name
    address:str=Field(min_length=1,max_length=500)
    contact:Name
class AcceptInput(Version):
    line_ids:list[UUID]=Field(min_length=1,max_length=100)
    performed_at:AwareDatetime
    confirmation:Name
    notes:str=Field(default='',max_length=2000)
    evidence_ref:str=Field(default='',max_length=160)
class CorrectInput(Version):
    acceptance_id:UUID
    performed_at:AwareDatetime
    confirmation:Name
class ReturnInput(Version):
    line_ids:list[UUID]=Field(min_length=1,max_length=100)
    location_id:UUID
    performed_at:AwareDatetime

from datetime import datetime
from silicon.assembly.models import View,DeviceView
class DeliveryTestView(View):
    id:UUID
    completion_id:UUID
    layer_version:int
    result:Literal['pass','fail']
    items:list[TestItem]
    performed_at:datetime
    created_at:datetime
    actor_id:UUID
    notes:str
    report_ref:str
class AcceptanceView(View):
    id:UUID
    line_id:UUID
    accepted:bool
    corrects:UUID|None
    performed_at:datetime
    created_at:datetime
    actor_id:UUID
    confirmation:str
    notes:str
    evidence_ref:str
class ReturnView(View):
    id:UUID
    line_id:UUID
    location_id:UUID
    movement_id:UUID
    performed_at:datetime
    created_at:datetime
    actor_id:UUID
    reason:str
class DeliveryLineView(View):
    id:UUID
    shipment_id:UUID
    order_id:UUID
    device_id:UUID
    completion_id:UUID
    layer_id:UUID
    location_id:UUID|None
    test_id:UUID|None
    movement_id:UUID|None
    serial:str=''
    number:str=''
    cost:str|None=None
    acceptances:list[AcceptanceView]=[]
    returns:list[ReturnView]=[]
    accepted:bool=False
    reversed:bool=False
class DeliveryDeviceView(DeviceView):
    version:int
    tests:list[DeliveryTestView]
    deliveries:list[DeliveryLineView]
    eligibility:Literal['pending','pass','fail','shipped','invalid']
class DeliveryProgress(View):
    order_id:UUID
    number:str
    customer_name:str
    quantity:int
    shipped:int
    accepted:int
    returned:int
    net_delivered:int
    net_accepted:int
    remaining:int
    cost:str|None=None
class DeliveryReversal(View):
    id:UUID
    movement_id:UUID
    actor_id:UUID
    reason:str
    created_at:datetime
class ShipmentView(View):
    id:UUID
    order_id:UUID
    recipient:str
    address:str
    contact:str
    state:Literal['draft','confirmed','cancelled']
    version:int
    created_at:datetime
    lines:list[DeliveryLineView]
    reversals:list[DeliveryReversal]
    progress:DeliveryProgress
class DeliveryReconciliation(View):
    matches:bool
    differences:list[str]
    orders:list[DeliveryProgress]
