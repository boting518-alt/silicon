// Actual React DOM + actual lifecycle component; only HTTP boundary is simulated.
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {PublicationDesk} from '../src/Publication';
import {crmRequests} from '../src/api';
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const container=document.querySelector('#fixture'),out=document.querySelector('#results');
const assert=(v,m)=>{if(!v)throw Error(m);};
const content={development:true,customer:{name:'虚构客户',project:{name:'项目'},contacts:[],sites:[],responsibilities:[],responsibility_names:{}},config:{name:'组件候选',quantity:1},policy:{version:1,responsibility:'虚构测试'},valid_until:'2098-01-01T00:00:00Z',host:{name:'主机',brand:'硅屿',brand_kind:'own'},calculation:{total:'100.00',tax_included:true,technical_lines:[],priced_lines:[],checks:[],discount_amount:'0.00'}};
const initial={id:'candidate',draft_id:'draft',draft_version:1,submitter_id:'alice',content_hash:'frozen-hash',state:'approved',content};
async function flush(){await act(async()=>{await new Promise(r=>setTimeout(r,0));});}
async function click(text){await act(async()=>{const b=[...container.querySelectorAll('button')].find(x=>x.textContent===text);assert(b&&!b.disabled,'enabled '+text);b.click();});await flush();}
async function setup(){
 let candidate=structuredClone(initial),versions=[],requests=[],lose=true,delay=null,invalid=false;
 const old=globalThis.fetch;
 globalThis.fetch=async(url,init={})=>{
  const path=String(url).replace('/api/v1/publication','');let data;
  if(path==='/candidates'){if(delay)return delay;data=[candidate];}
  else if(path==='/versions')data=versions;
  else if(path==='/contracts')data=[];
  else if(path==='/candidates/candidate/issue'){
   requests.push(new Headers(init.headers).get('Idempotency-Key'));
   if(invalid)return new Response(JSON.stringify({code:'APPROVAL_INVALIDATED'}),{status:409});
   if(!versions.length)versions.push({id:'version',candidate_id:'candidate',decision_id:'decision',number:'Q-000001',revision:1,version:1,state:'issued',content,content_hash:'frozen-hash',issuer_id:'bob',issued_at:'2026-09-10T00:00:00Z',valid_until:content.valid_until});
   if(lose){lose=false;return new Response(JSON.stringify({code:'TEST_LOSS'}),{status:503});}
   candidate.state='published';data=versions[0];
  }else throw Error('Unexpected '+path);
  return new Response(JSON.stringify(data),{status:200});
 };
 crmRequests.bind({tenant_id:'A',context_id:'A-1'});const root=createRoot(container);
 await act(async()=>root.render(<PublicationDesk context={crmRequests.capture()} canApprove canWrite disabled={false} onContextError={()=>{}}/>));await flush();
 return {requests,versions,invalidate(){invalid=true;},setState(v){candidate.state=v;},defer(p){delay=p;},async close(){await act(async()=>root.unmount());crmRequests.bind(null);globalThis.fetch=old;}};
}
const tests=[
 ['refresh marks old approval invalid and removes publish action',async h=>{
  await click('组件候选 · v1 · 已批准');assert(container.textContent.includes('人工确认发布'),'approved controls visible');h.setState('invalidated');await click('刷新状态');assert(container.textContent.includes('审批失效'),'invalidity shown');assert(!container.textContent.includes('发布批准版本'),'stale publication button removed');
 }],
 ['lost publish response retries same command and renders one immutable version',async h=>{
  await click('组件候选 · v1 · 已批准');await act(async()=>container.querySelector('input[type=checkbox]').click());await click('发布批准版本');assert(container.querySelector('[role=alert]'),'failure shown');assert(h.versions.length===1,'real-intent simulated commit once');await click('发布批准版本');assert(h.requests.length===2&&h.requests[0]===h.requests[1],'same command retry');assert(h.versions.length===1&&container.textContent.includes('Q-000001'),'one version rendered');assert(!container.querySelector('[role=alert]'),'error recovered');
 }],
 ['server rejects stale approval and page removes stale publish controls',async h=>{
  await click('组件候选 · v1 · 已批准');await act(async()=>container.querySelector('input[type=checkbox]').click());h.invalidate();await click('发布批准版本');await flush();assert(container.textContent.includes('审批失效'),'server invalidation shown');assert(!container.textContent.includes('发布批准版本'),'stale action removed immediately');
 }],
 ['late successful A refresh cannot overwrite after context switch',async h=>{
  let release;const gate=new Promise(r=>release=r);h.defer(gate);await click('刷新状态');crmRequests.bind({tenant_id:'B',context_id:'B-1'});await act(async()=>release(new Response(JSON.stringify([{...initial,content:{...content,config:{...content.config,name:'LATE_A_SUCCESS'}}}]),{status:200})));await flush();assert(!container.textContent.includes('LATE_A_SUCCESS'),'successful old response fenced');
 }]
];
const results=[];for(const [name,test] of tests){const h=await setup();try{await test(h);results.push({name,status:'passed'});}catch(e){results.push({name,status:'failed',error:e.message});}finally{await h.close();}out.textContent=JSON.stringify(results,null,2);}out.dataset.status=results.every(x=>x.status==='passed')?'passed':'failed';
