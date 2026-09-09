from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=160)]
Short=Annotated[str,StringConstraints(strip_whitespace=True,max_length=160)]
Note=Annotated[str,StringConstraints(strip_whitespace=True,max_length=2000)]


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Contact(Input):
    id: UUID
    name: Name
    title: Short=''
    phone: Annotated[str,StringConstraints(strip_whitespace=True,max_length=40)]=''
    email: Annotated[str,StringConstraints(strip_whitespace=True,max_length=254)]=''

    @model_validator(mode='after')
    def email_format(self):
        import re
        if self.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',self.email):
            raise ValueError('联系人邮箱格式无效')
        return self


class ProjectPerson(Input):
    contact_id: UUID
    role: Literal['project_lead','key_person']


class Project(Input):
    id: UUID
    name: Name
    notes: Note=''
    people: list[ProjectPerson]=Field(default_factory=list,max_length=50)


class Site(Input):
    id: UUID
    name: Name
    address: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=300)]


class Responsibility(Input):
    role: Literal['sales','service']
    user_id: UUID


class CustomerInput(Input):
    number: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=40)]
    name: Name
    province: Short=''
    city: Short=''
    industry: Short=''
    level: Literal['普通客户','重点客户','战略客户']='普通客户'
    stage: Literal['跟进中','稳定合作','交付推进','续保跟进']='跟进中'
    notes: Note=''
    contacts: list[Contact]=Field(default_factory=list,max_length=50)
    projects: list[Project]=Field(default_factory=list,max_length=50)
    sites: list[Site]=Field(default_factory=list,max_length=50)
    responsibilities: list[Responsibility]=Field(default_factory=list,max_length=2)

    @model_validator(mode='after')
    def relationships(self):
        for values in (self.contacts,self.projects,self.sites):
            if len({x.id for x in values})!=len(values):raise ValueError('子项 ID 不可重复')
        if len({x.role for x in self.responsibilities})!=len(self.responsibilities):raise ValueError('内部负责人角色不可重复')
        contacts={x.id for x in self.contacts}
        for project in self.projects:
            if any(p.contact_id not in contacts for p in project.people):raise ValueError('项目角色必须关联本客户联系人')
            if len({(p.contact_id,p.role) for p in project.people})!=len(project.people):raise ValueError('项目角色不可重复')
        return self


class CustomerUpdate(CustomerInput):
    expected_version: int=Field(ge=1)


class CustomerSummary(BaseModel):
    id: UUID
    number: str
    name: str
    province: str
    city: str
    industry: str
    level: str
    stage: str
    contact_count: int
    project_count: int
    owner_id: UUID
    owner_name: str
    version: int
    created_at: datetime
    updated_at: datetime


class RoleHistory(BaseModel):
    id: UUID
    party: str
    project_id: UUID | None
    project_name: str
    role: str
    person_id: UUID
    person_name: str
    valid_from: datetime
    valid_until: datetime | None
    changed_by: UUID


class CustomerDetail(CustomerSummary):
    notes: str
    contacts: list[Contact]
    projects: list[Project]
    sites: list[Site]
    responsibilities: list[Responsibility]
    role_history: list[RoleHistory]


class CustomerPage(BaseModel):
    contact_total: int
    project_total: int
    province_total: int
    items: list[CustomerSummary]
    total: int
    page: int
    page_size: int


class Member(BaseModel):
    id: UUID
    name: str
