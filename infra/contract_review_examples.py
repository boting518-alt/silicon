"""Explicit disposable TASK-007 browser preconditions. Never a product auth path.

Use real API commands with existing repository session fixtures to prepare only
an unsigned, populated contract. Browser signing/uploads still use real OIDC.
"""
from types import SimpleNamespace
from test_contracts import client,request,fields
from test_publication import submit,approve,issue,convert
from test_catalog import ok
from publication_examples import APPROVER

def seed(engine,database,actor,tenant,file_root):
    database.files=str(file_root)
    with client(engine,database,actor,tenant) as c:
        drafts=c.get('/api/v1/quotes').json()
        summary=next(x for x in drafts if x['name']=='虚构 TASK-006 发布验收')
        draft=c.get('/api/v1/quotes/'+summary['id']).json()
        candidate=submit(c,draft)
    with client(engine,database,APPROVER,tenant) as c:
        ok(approve(c,candidate),200);version=ok(issue(c,candidate));contract=ok(convert(c,version))
        value=fields(SimpleNamespace(user=actor,other=APPROVER),number='DEMO-CON-007')
        value['name']='虚构附件修复验收'
        value['payments']=value['payments'][:1];value['payments'][0]['amount']=version['content']['calculation']['total']
        ok(request(c,'/'+contract['id']+'/save',{'expected_version':0,'fields':value}),200)
