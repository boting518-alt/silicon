from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from typing import Annotated,Literal
from uuid import UUID
from pydantic import Field,BeforeValidator,AwareDatetime
from silicon.catalog.models import Input,Name
from silicon.assembly.models import View

def exact(v):
    if isinstance(v,(float,bool)):raise ValueError('Use a decimal string, not floating point')
    try:n=Decimal(v)
    except (InvalidOperation,TypeError):raise ValueError("Invalid decimal amount")
    if not n.is_finite() or abs(n)>=Decimal('1e16') or n.as_tuple().exponent < -2:raise ValueError('Finite amounts with at most two decimal places required')
    return n
Money=Annotated[Decimal,BeforeValidator(exact),Field(gt=0,max_digits=18,decimal_places=2)]
SignedMoney=Annotated[Decimal,BeforeValidator(exact),Field(max_digits=18,decimal_places=2)]
Direction=Literal['receivable','payable']
class Version(Input):
    expected_version:int=Field(ge=1)
    confirmed:Literal[True]
    reason:str=Field(min_length=1,max_length=500)
class PlanInput(Input):
    direction:Direction
    source_id:UUID
    order_id:UUID|None=None
    node:Name
    amount:Money
    currency:Literal['CNY']='CNY'
    due_date:date|None=None
    retention:bool=False
    release_condition:str=Field(default='',max_length=500)
    notes:str=Field(default='',max_length=1000)
class ImportInput(Input):
    source_id:UUID
class CashInput(Input):
    direction:Direction
    party_id:UUID
    amount:Money
    currency:Literal['CNY']='CNY'
    purpose:Literal['unallocated','advance']='unallocated'
    occurred_at:AwareDatetime
    method:Name
    account:Name
    external_ref:str=Field(default='',max_length=160)
    notes:str=Field(min_length=1,max_length=1000)
class AllocationLine(Input):
    plan_id:UUID
    expected_version:int=Field(ge=1)
    amount:Money
class AllocateInput(Version):
    lines:list[AllocationLine]=Field(min_length=1,max_length=100)
class AdjustmentInput(Version):
    amount:SignedMoney
    basis_ref:Name
    return_id:UUID|None=None
class AdjustmentCorrectionInput(Version):
    adjustment_id:UUID
    basis_ref:Name
class ReleaseInput(Version):
    due_date:date
class RefundInput(Input):
    cash_id:UUID
    amount:Money
    occurred_at:AwareDatetime
    account:Name
    external_ref:str=Field(default='',max_length=160)
    reason:Name
class RefundConfirm(Version):
    cash_version:int=Field(ge=1)
class SourceAdjustment(Input):
    direction:Direction
    source_id:UUID
    amount:SignedMoney
    basis_ref:Name
    reason:Name
    confirmed:Literal[True]
    expected_version:int=Field(ge=1)
class InvoiceLineInput(Input):
    source_id:UUID
    amount:Money
class InvoiceInput(Input):
    direction:Direction
    party_id:UUID
    number:Name
    kind:Name
    issued_on:date
    buyer:Name
    seller:Name
    currency:Literal['CNY']='CNY'
    amount:Money
    net_amount:Annotated[Decimal,BeforeValidator(exact),Field(ge=0,max_digits=18,decimal_places=2)]|None=None
    tax_amount:Annotated[Decimal,BeforeValidator(exact),Field(ge=0,max_digits=18,decimal_places=2)]|None=None
    original_id:UUID|None=None
    lines:list[InvoiceLineInput]=Field(min_length=1,max_length=100)
    notes:str=Field(default='',max_length=1000)
    archive_ref:str=Field(default='',max_length=160)
class NodeView(View):
    id:str
    name:str
    amount:str
    resolved_due_date:date|None=None
    trigger:str
class SourceView(View):
    kind:str="contract"
    id:UUID
    direction:Direction
    party_id:UUID
    party_name:str
    number:str
    amount:str
    base_amount:str
    version:int
    order_ids:list[UUID]
    nodes:list[NodeView]
    tax_basis:str
class EventView(View):
    id:UUID
    amount:str|None=None
    reason:str=''
    basis_ref:str=''
    created_at:datetime
    actor_id:UUID
    return_id:UUID|None=None
    due_date:date|None=None
class AllocationView(View):
    id:UUID
    cash_id:UUID
    plan_id:UUID
    amount:str
    created_at:datetime
    actor_id:UUID
    reversed:bool
class AdjustmentCorrectionView(EventView):
    adjustment_id:UUID
class PlanView(View):
    id:UUID
    source_id:UUID
    direction:Direction
    party_id:UUID
    party_name:str
    node:str
    notes:str
    order_id:UUID|None
    purchase_order_id:UUID|None
    state:str
    version:int
    amount:str
    effective:str
    adjustment:str
    allocated:str
    remaining:str
    due_date:date|None
    retention:bool
    release_condition:str
    released:bool
    overdue:bool
    adjustments:list[EventView]
    corrections:list[AdjustmentCorrectionView]=Field(default_factory=list)
    releases:list[EventView]
    allocations:list[AllocationView]
class CashView(View):
    id:UUID
    actor_id:UUID
    created_at:datetime
    direction:Direction
    party_id:UUID
    party_name:str
    state:str
    version:int
    amount:str
    allocated:str
    refunded:str
    available:str
    purpose:str
    occurred_at:datetime
    method:str
    account:str
    external_ref:str
    notes:str
    reversed:bool
    allocations:list[AllocationView]
class RefundView(View):
    id:UUID
    cash_id:UUID
    state:str
    version:int
    amount:str
    occurred_at:datetime
    reason:str
    account:str
    external_ref:str
    reversed:bool
class InvoiceLineView(View):
    id:UUID
    source_id:UUID
    amount:str
class InvoiceView(View):
    id:UUID
    direction:Direction
    party_id:UUID
    state:str
    version:int
    number:str
    kind:str
    issued_on:date
    buyer:str
    seller:str
    amount:str
    net_amount:str|None
    tax_amount:str|None
    tax_state:str
    original_id:UUID|None
    notes:str
    archive_ref:str
    reversed:bool
    lines:list[InvoiceLineView]
class SummaryView(View):
    receivable:str
    payable:str
    overdue_receivable:str
    overdue_payable:str
    received:str
    paid:str
    customer_refunds:str
    supplier_refunds:str
    net_cash_flow:str
    advance_received:str
    advance_paid:str
    unallocated_received:str
    unallocated_paid:str
    as_of:datetime
    currency:Literal['CNY']='CNY'
    basis:str='经营资金登记；非收入或利润'
class FinanceContext(View):
    permissions:list[str]
class PartyView(View):
    id:UUID
    name:str
    direction:Direction
class FinanceReconciliation(View):
    matches:bool
    differences:list[str]
    summary:SummaryView
class SourceSummary(View):
    source:SourceView
    plans:list[PlanView]
    invoiced:str
