// Real React DOM and unmodified QuoteStudio events. Only HTTP is simulated.
// Open /tests/quote-component.html on the development server; never a product route.
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {QuoteStudio} from '../src/QuoteStudio';
import {crmRequests} from '../src/api';
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const output=document.querySelector('#results'),container=document.querySelector('#fixture');
const assert=(condition,message)=>{if(!condition)throw Error(message);};
const copy=value=>JSON.parse(JSON.stringify(value));
const customer={id:'customer-a',name:'虚构组件客户',projects:[{id:'project-a',name:'虚构项目'}]};
const host={id:'host-a',name:'虚构主机',category:'host',enabled:true};
const bom={id:'bom-a',name:'虚构 BOM',revision:1,state:'published',subject_sku_id:host.id,snapshot:{subject:host,technical_lines:[]}};
const calc={total:'12.00',subtotal:'12.00',discount_amount:'0.00',amount_complete:true,priced_lines:[],technical_lines:[],checks:[],calculated_at:'2026-09-10T00:00:00Z'};
function field(name){const label=[...container.querySelectorAll('label')].find(x=>x.firstChild?.textContent.trim()===name);assert(label,'field '+name);return label.querySelector('input,select');}
function button(name){const b=[...container.querySelectorAll('button')].find(x=>x.textContent===name);assert(b,'button '+name);assert(!b.disabled,'button enabled '+name);return b;}
async function flush(){await act(async()=>{await new Promise(r=>setTimeout(r,0));});}
async function waitFor(check){const deadline=performance.now()+2000;while(!check()){assert(performance.now()<deadline,'component did not settle');await flush();}}
async function click(name){await act(async()=>{button(name).click();});await flush();}
async function change(name,value){await act(async()=>{const node=field(name);const setter=Object.getOwnPropertyDescriptor(node.tagName==='INPUT'?HTMLInputElement.prototype:HTMLSelectElement.prototype,'value').set;setter.call(node,value);node.dispatchEvent(new Event(node.tagName==='INPUT'?'input':'change',{bubbles:true}));});await flush();}
async function fillSame(){await change('草稿名称','完全相同的虚构草稿');await change('客户',customer.id);await waitFor(()=>field('项目').options.length===2);await change('项目','project-a');await change('准系统 / BOM 版本',bom.id);}
async function setup(){
 const rows=new Map(),commands=new Map(),creates=[];let lose=false,trial=null;
 const oldFetch=globalThis.fetch;
 globalThis.fetch=async(url,init={})=>{
  const path=String(url).replace('/api/v1','');const method=init.method??'GET';const body=init.body?JSON.parse(init.body):null;
  let value;
  if(path==='/catalog/skus')value=[host];else if(path==='/catalog/boms')value=[bom];
  else if(path.startsWith('/crm/customers?'))value={items:[customer]};else if(path==='/crm/customers/'+customer.id)value=customer;
  else if(path==='/quotes/evaluate'){if(trial)return trial();value=calc;}
  else if(path==='/quotes'&&method==='GET')value=[...rows.values()].map(x=>({id:x.id,name:x.config.name,version:x.version}));
  else if(path.startsWith('/quotes')&&method!=='GET'){
   const key=new Headers(init.headers).get('Idempotency-Key');const scope=method+path+key;
   if(method==='POST')creates.push(key);
   if(commands.has(scope))value=commands.get(scope);
   else {const id=method==='POST'?'draft-'+(rows.size+1):path.split('/').at(-1);const old=rows.get(id);
    if(old)assert(body.expected_version===old.version,'expected_version accompanies edit');
    const {expected_version,...config}=body;value={id,version:(old?.version??0)+1,config,saved_calculation:calc,current_calculation:calc,needs_reprice:false};rows.set(id,copy(value));commands.set(scope,copy(value));}
   if(lose&&method==='POST'){lose=false;throw new TypeError('test response lost after commit');}
  }else if(path.startsWith('/quotes/'))value=rows.get(path.split('/').at(-1));else throw Error('unexpected test request '+path);
  return new Response(JSON.stringify(copy(value)),{status:200});
 };
 crmRequests.bind({tenant_id:'A',context_id:'A-1'});const root=createRoot(container);
 await act(async()=>root.render(<QuoteStudio context={crmRequests.capture()} canWrite canDiscount disabled={false} onContextError={e=>{throw e;}}/>));await flush();
 return {rows,creates,loseNext(){lose=true;},setTrial(fn){trial=fn;},async close(){await act(async()=>root.unmount());crmRequests.bind(null);globalThis.fetch=oldFetch;}};
}
const tests=[
 ['R2 explicit new creates a second identical draft and edits only that draft',async h=>{
  await fillSame();await click('保存草稿');await waitFor(()=>h.rows.size===1);const first=field('已保存草稿').value;
  await click('新建草稿');await fillSame();await click('保存草稿');
  assert(h.rows.size===2,'explicit new must create two rows for identical content');const second=field('已保存草稿').value;
  assert(second!==first,'new draft id differs');assert(field('已保存草稿').options.length===3,'list contains both drafts');
  await change('草稿名称','仅修改第二份');await click('保存草稿');assert(h.rows.get(first).config.name==='完全相同的虚构草稿','first draft unchanged');assert(h.rows.get(second).version===2,'second edited');
  await change('已保存草稿',first);await waitFor(()=>field('草稿名称').value==='完全相同的虚构草稿');await click('新建草稿');await fillSame();await click('保存草稿');assert(h.rows.size===3,'open then new starts independent command');
 }],
 ['R2 lost create response retries one command, then explicit new starts another',async h=>{
  await fillSame();h.loseNext();await click('保存草稿');assert(container.querySelector('[role=alert]'),'loss shown');assert(h.rows.size===1,'server committed before loss');
  await click('保存草稿');assert(h.rows.size===1,'retry does not duplicate');assert(h.creates[0]===h.creates[1],'same attempt keeps key');assert(field('已保存草稿').value==='draft-1','replay opens committed draft');
  await click('新建草稿');await fillSame();await click('保存草稿');assert(h.rows.size===2,'explicit new after retry is independent');
 }],
 ['C1 success then in-flight failure then success preserves edits and historical amount',async h=>{
  await fillSame();await click('保存草稿');await change('草稿名称','未保存的编辑');await click('重新计价');assert(container.querySelector('.total strong').textContent==='12.00 CNY','first trial succeeds');
  let release;const gate=new Promise(r=>release=r);h.setTrial(async()=>{await gate;return new Response(JSON.stringify({code:'TEST_UNAVAILABLE'}),{status:503});});
  try{await click('重新计价');assert(container.textContent.includes('正在重新计价'),'in-flight status');assert(!container.querySelector('.total strong').textContent.includes('12.00'),'prior trial hidden while in flight');}
  finally{await act(async()=>release());await flush();}
  assert(container.querySelector('[role=alert]'),'failure visible');assert(container.textContent.includes('待重新计价'),'failure requires retry');assert(!container.textContent.includes('已完成后端试算'),'old success notice gone');
  assert(container.textContent.includes('历史保存结果'),'history explicitly labelled');assert(field('草稿名称').value==='未保存的编辑','unsaved edit survives');
  h.setTrial(null);await click('重新计价');assert(container.querySelector('.total strong').textContent==='12.00 CNY','retry succeeds');assert(!container.querySelector('[role=alert]'),'error cleared');
 }]
];
const results=[];
for(const [name,test] of tests){const h=await setup();try{await test(h);results.push({name,status:'passed'});}catch(e){results.push({name,status:'failed',error:e.message});}finally{await h.close();}output.textContent=JSON.stringify(results,null,2);}
output.dataset.status=results.every(x=>x.status==='passed')?'passed':'failed';
