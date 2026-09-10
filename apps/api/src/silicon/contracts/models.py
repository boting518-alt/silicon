from datetime import date,datetime
from decimal import Decimal
from typing import Annotated,Literal
from uuid import UUID
from pydantic import Field,model_validator
from silicon.catalog.models import Input,Short
from silicon.publication.models import Contract
Text=Annotated[str,Field(max_length=1000)]
class Person(Input):
    name:Short=''
    contact:Short=''
class Party(Input):
    name:Short=''
    address:Text=''
    identifier:Short=''
    representative:Short=''
class Assignment(Input):
    user_id:UUID|None=None
    name:Short=''
class Payment(Input):
    id:UUID
    name:Short
    amount:Annotated[Decimal,Field(gt=0,max_digits=18,decimal_places=2)]
    currency:Literal['CNY']='CNY'
    trigger:Literal['date','signing','delivery','acceptance']
    due_date:date|None=None
    offset_days:Annotated[int,Field(ge=0,le=3650)]=0
    note:Text=''
    @model_validator(mode='after')
    def dates(self):
        if (self.trigger=='date')!=(self.due_date is not None):raise ValueError('Only fixed-date plans have a known due date')
        if self.trigger=='date' and self.offset_days:raise ValueError('Fixed date does not use offset')
        return self
class Fields(Input):
    number:Annotated[str,Field(max_length=40,pattern=r'^[A-Za-z0-9_-]*$')]=''
    name:Short=''
    buyer:Party=Field(default_factory=Party)
    seller:Party=Field(default_factory=Party)
    project_lead:Person=Field(default_factory=Person)
    key_contacts:Annotated[list[Person],Field(max_length=20)]=Field(default_factory=list)
    sales:Assignment=Field(default_factory=Assignment)
    support:Assignment=Field(default_factory=Assignment)
    signing_date:date|None=None
    delivery_date:date|None=None
    delivery_note:Text=''
    notes:Text=''
    payments:Annotated[list[Payment],Field(max_length=30)]=Field(default_factory=list)
class Save(Input):
    expected_version:Annotated[int,Field(ge=0)]
    fields:Fields
class Version(Input):
    expected_version:Annotated[int,Field(ge=0)]
class Sign(Version):
    content_hash:Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
    confirmed:Literal[True]
class File(Input):
    supplemental:bool=False
    id:UUID
    name:str
    category:str
    media_type:str
    size:int
    sha256:str
    state:str
    uploaded_by:UUID
    created_at:datetime
class Workspace(Input):
    id:UUID
    version:int
    state:Literal['draft','signed']
    fields:Fields
    source:Contract
    files:list[File]
    checks:list[str]
    ready:bool
    content_hash:str
    signed_id:UUID|None=None
    order_id:UUID|None=None
    history:list[dict]=Field(default_factory=list)
class Signed(Input):
    id:UUID
    contract_id:UUID
    number:str
    version:int
    content_hash:str
    content:dict
    registered_by:UUID
    registered_at:datetime
    order_id:UUID
class Order(Input):
    id:UUID
    number:str
    contract_version_id:UUID
    quote_version_id:UUID
    amount:Decimal
    currency:Literal['CNY']
    state:Literal['pending_fulfillment']
    content:dict
