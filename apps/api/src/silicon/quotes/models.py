from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from pydantic import Field,model_validator
from silicon.catalog.models import Input,Name,Code,Positive,Check,TechnicalLine,CurrentPrice

class Selection(Input):
    sku_id: UUID
    quantity: Annotated[int,Field(ge=1,le=10000,strict=True)]

class QuoteInput(Input):
    name: Name
    customer_id: UUID
    project_id: UUID
    bom_id: UUID
    quantity: Annotated[int,Field(ge=1,le=10000,strict=True)]=1
    scope: Code='retail'
    tax_included: bool=True
    additions: Annotated[list[Selection],Field(max_length=100)]=Field(default_factory=list)
    excluded_sku_ids: Annotated[list[UUID],Field(max_length=100)]=Field(default_factory=list)
    discount_id: UUID|None=None
    @model_validator(mode='after')
    def unique(self):
        if len({x.sku_id for x in self.additions})!=len(self.additions) or len(set(self.excluded_sku_ids))!=len(self.excluded_sku_ids):raise ValueError('duplicate selection')
        return self

class QuoteUpdate(QuoteInput):
    expected_version: Positive

class DiscountCode(Input):
    code: Annotated[str,Field(min_length=1,max_length=80)]

class DiscountRef(Input):
    id: UUID
    name: str
    version: int

class PricedLine(Input):
    sku_id: UUID
    name: str
    quantity: int
    unit_price: str|None
    line_amount: str|None
    source: CurrentPrice

class Calculation(Input):
    calculated_at: datetime
    config_hash: str
    fingerprint: str
    priced_lines: list[PricedLine]
    technical_lines: list[TechnicalLine]
    checks: list[Check]
    subtotal: str|None
    discount_amount: str|None
    total: str|None
    amount_complete: bool
    sale_ready: bool=False
    currency: str='CNY'
    tax_included: bool
    discount: DiscountRef|None=None
    discount_basis_points: int|None=None
    policy: str='development-v1; no tax conversion; no reservation/redemption'

class QuoteSummary(Input):
    id: UUID
    name: str
    customer_id: UUID
    version: int

class QuoteDetail(Input):
    published_version_id: UUID|None=None
    id: UUID
    version: int
    config: QuoteInput
    saved_calculation: Calculation
    current_calculation: Calculation
    needs_reprice: bool
