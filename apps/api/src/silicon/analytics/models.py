from datetime import date as Date,datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .time import today
class AnalyticsFilter(BaseModel):
    model_config=ConfigDict(extra='forbid')
    start:Date
    end:Date
    as_of:Date
    customer_id:UUID|None=None
    region:str|None=Field(default=None,max_length=20)
    overdue_days:int=Field(default=90,ge=1,le=3650)
    old_stock_days:int=Field(default=180,ge=1,le=3650)
    due_days:int=Field(default=7,ge=0,le=90)
    top_n:int=Field(default=5,ge=1,le=20)
    @model_validator(mode='after')
    def dates(self):
        from datetime import timedelta
        if not self.start<self.end or (self.end-self.start).days>366:raise ValueError('期间必须为1至366天的半开区间')
        if self.as_of>today() or self.end>today()+timedelta(days=1):raise ValueError('截止日及期间不可晚于今天')
        return self
class AnalyticsTarget(BaseModel):
    kind:Literal['customer','contract','order','shipment','finance','inventory','service']
    id:str
class Contribution(BaseModel):
    id:str
    label:str
    date:Date|None=None
    value:str
    customer_id:str|None=None
    region:str='unknown'
    group:str=''
    note:str=''
    target:AnalyticsTarget|None=None
class AnalyticsGroup(BaseModel):
    key:str
    label:str
    value:str
    count:int
class Metric(BaseModel):
    id:str
    name:str
    value:str|None
    unit:str
    status:Literal['complete','partial','unavailable','unauthorized','not_applicable']
    reason:str=''
    basis:str
    start:Date
    end:Date
    as_of:Date
    drillable:bool
    groups:list[AnalyticsGroup]=Field(default_factory=list)
class RegionView(BaseModel):
    code:str
    name:str
    short:str
    row:int
    column:int
class CustomerOption(BaseModel):
    id:str
    name:str
class AnalyticsReport(BaseModel):
    customers:list[CustomerOption]
    snapshot:str
    calculated_at:datetime
    basis_version:str='analytics-v1'
    filters:AnalyticsFilter
    metrics:list[Metric]
    regions:list[RegionView]
    scope_note:str
class AnalyticsDetails(BaseModel):
    snapshot:str
    filters:AnalyticsFilter
    metric:Metric
    total:int
    page:int
    page_size:int
    items:list[Contribution]
