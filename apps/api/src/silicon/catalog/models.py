"""Small typed hardware vocabulary; snapshots preserve these same public fields."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, AwareDatetime, model_validator

Name=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=160)]
Code=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=40)]
Short=Annotated[str,StringConstraints(strip_whitespace=True,max_length=160)]
Positive=Annotated[int,Field(gt=0,le=1000000,strict=True)]
Category=Literal['host','cpu','gpu','memory','psu','system_disk','data_disk','nic','ib']

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Specs(Input):
    socket: Short=''
    memory_generation: Short=''
    capacity_gb: Positive|None=None
    power_w: Positive|None=None
    slot_width: Annotated[int,Field(ge=1,le=8,strict=True)]|None=None
    interface: Short=''
    speed_gbps: Positive|None=None
    cpu_sockets: Annotated[int,Field(ge=1,le=8,strict=True)]|None=None

class SkuInput(Input):
    number: Code
    name: Name
    category: Category
    manufacturer: Name
    brand: Name
    brand_kind: Literal['own','third_party']
    enabled: bool=True
    specs: Specs=Field(default_factory=Specs)

class SkuUpdate(SkuInput):
    expected_version: Positive

class Sku(SkuInput):
    id: UUID
    version: int

class Check(Input):
    code: str
    status: Literal['BLOCK','WARN','UNKNOWN','PASS']
    message: str

class RuleInput(Input):
    name: Name
    source: Name
    socket: Short=''
    memory_generation: Short=''
    power_budget_w: Positive|None=None

class Rule(RuleInput):
    id: UUID
    family_id: UUID
    revision: int

class BomLine(Input):
    sku_id: UUID
    package_version_id: UUID|None=None
    quantity: Annotated[int,Field(ge=1,le=10000,strict=True)]
    required: bool=True
    charge_mode: Literal['included','separate']

class BomInput(Input):
    name: Name
    kind: Literal['package','bom']
    subject_sku_id: UUID
    rule_id: UUID|None=None
    lines: Annotated[list[BomLine],Field(max_length=100)]=Field(default_factory=list)
    @model_validator(mode='after')
    def unique_lines(self):
        ids=[x.sku_id for x in self.lines]
        if len(set(ids))!=len(ids):raise ValueError('duplicate SKU line')
        if self.kind=='package' and any(x.charge_mode!='included' for x in self.lines):
            raise ValueError('package contents must be included, not extra charges')
        return self

class BomUpdate(BomInput):
    expected_version: Positive

class VersionCommand(Input):
    expected_version: Positive

class TechnicalLine(Input):
    sku: Sku
    quantity: int
    required: bool
    charge_mode: Literal['included','separate']

class BomSnapshot(Input):
    subject: Sku
    technical_lines: list[TechnicalLine]
    rule: Rule|None
    checks: list[Check]

class Bom(BomInput):
    id: UUID
    family_id: UUID
    revision: int
    version: int
    state: Literal['draft','published']
    snapshot: BomSnapshot

Money=Annotated[Decimal,Field(ge=0,max_digits=18,decimal_places=2)]
class PriceLine(Input):
    sku_id: UUID
    amount: Money

class PriceInput(Input):
    name: Name
    scope: Code
    currency: Literal['CNY']='CNY'
    tax_included: bool
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    source: Name
    lines: Annotated[list[PriceLine],Field(min_length=1,max_length=100)]
    @model_validator(mode='after')
    def interval(self):
        if self.valid_to<=self.valid_from:raise ValueError('empty or reversed price interval')
        if len({x.sku_id for x in self.lines})!=len(self.lines):raise ValueError('duplicate price SKU')
        return self

class PriceUpdate(PriceInput):
    expected_version: Positive

class PriceBook(PriceInput):
    id: UUID
    family_id: UUID
    revision: int
    version: int
    state: Literal['draft','published']

class CurrentPrice(Input):
    status: Literal['KNOWN','UNKNOWN','EXPIRED','NOT_YET_VALID']
    amount: str|None=None
    currency: Literal['CNY']='CNY'
    tax_included: bool
    scope: str
    as_of: datetime
    book_id: UUID|None=None
    revision: int|None=None
    source: str|None=None
    valid_from: datetime|None=None
    valid_to: datetime|None=None

class RuleRevision(RuleInput):
    expected_version: Positive
