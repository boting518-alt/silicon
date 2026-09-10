import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {Contracts} from '../src/Contracts';
import {crmRequests} from '../src/api';
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const container=document.querySelector('#fixture'),out=document.querySelector('#results');
const assert=(v,m)=>{if(!v)throw Error(m);};
const base={id:'contract',version:1,state:'draft',fields:{number:'CON-001',name:'虚构合同',buyer:{name:'甲',address:'甲地址',identifier:'',representative:'甲代表'},seller:{name:'乙',address:'乙地址',identifier:'',representative:'乙代表'},project_lead:{name:'负责人',contact:'fictional@example.invalid'},key_contacts:[{name:'关键人',contact:''}],sales:{user_id:'a',name:'甲'},support:{user_id:'a',name:'甲'},signing_date:'2026-01-01',delivery_date:null,delivery_note:'虚构约定',notes:'',payments:[{id:'p',name:'付款',amount:'300.00',currency:'CNY',trigger:'signing',offset_days:0,note:''}]},source:{source_number:'Q-000001',source_hash:'source-hash',source_state:'issued',content:{config:{name:'源草稿'},development:true,calculation:{total:'300.00',tax_included:true,technical_lines:[],priced_lines:[]}}},files:[],checks:[],ready:true,content_hash:'frozen-confirmation',history:[]};
async function flush(){await act(async()=>{await new Promise(r=>setTimeout(r,0));});}
async function click(text){await act(async()=>{const b=[...container.querySelectorAll('button')].find(x=>x.textContent===text);assert(b&&!b.disabled,'enabled '+text);b.click();});await flush();}
async function input(label,value){const el=[...container.querySelectorAll('label')].find(x=>x.firstChild?.textContent===label)?.querySelector('input');assert(el,'input '+label);await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));});await flush();}
async function setup(){
 let work=structuredClone(base),mode='',deferred=null;const calls=[];const old=globalThis.fetch;
 globalThis.fetch=async(url,init={})=>{let path=String(url).replace('/api/v1/contracts',''),data;
  if(path==='')data=[work];else if(path==='/orders')data=[];else if(path==='/contract'){if(deferred)return deferred;data=work;}
  else if(path==='/contract/save'){
   calls.push({path,key:new Headers(init.headers).get('Idempotency-Key')});if(mode==='conflict')return new Response(JSON.stringify({code:'VERSION_CONFLICT'}),{status:409});
   work={...work,fields:JSON.parse(init.body).fields,version:work.version+1};work.ready=work.fields.payments[0].amount==='300.00';work.checks=work.ready?[]:['PAYMENTS_UNBALANCED'];data=work;
  }else if(path.startsWith('/contract/uploads'))return new Response(JSON.stringify({code:'FILE_TYPE_REJECTED'}),{status:422});
  else if(path==='/contract/sign'){
   calls.push({path,key:new Headers(init.headers).get('Idempotency-Key')});work={...work,state:'signed',order_id:'order'};
   if(mode==='lost'){mode='';return new Response(JSON.stringify({code:'TEST_LOSS'}),{status:503});}data={id:'signed'};
  }else if(path==='/contract/files/pending/delete'){calls.push({path});work={...work,files:work.files.filter(x=>x.id!=='pending')};data=work;}else throw Error('Unexpected '+path);
  return new Response(JSON.stringify(data),{status:200});
 };
 crmRequests.bind({tenant_id:'A',context_id:'A1'});const root=createRoot(container);
 await act(async()=>root.render(<Contracts context={crmRequests.capture()} members={[{id:'a',name:'甲'}]} canWrite canSign onContextError={()=>{}}/>));await flush();
 const list=[...container.querySelectorAll('nav button')].find(b=>b.textContent.includes('CON-001'));await act(async()=>list.click());await flush();
 return {calls,setWork(v){work=v;},setMode(v){mode=v;},defer(v){deferred=v;},async close(){await act(async()=>root.unmount());crmRequests.bind(null);globalThis.fetch=old;}};
}
const tests=[
 ['old pending after signing can be deleted without enabling frozen file edits',async h=>{h.setWork({...structuredClone(base),state:'signed',files:[{id:'frozen',name:'A.pdf',size:621,state:'linked',category:'proof',sha256:'frozen-hash',supplemental:false},{id:'pending',name:'B.pdf',size:621,state:'pending',category:'proof',sha256:'pending-hash',supplemental:false}]});await click('重新载入合同');const button=t=>[...container.querySelectorAll('button')].find(x=>x.textContent===t);assert(button('删除 A.pdf').disabled,'frozen file protected');assert(button('关联 B.pdf').disabled,'cannot silently add old pending');assert(!button('删除 B.pdf').disabled,'pending can be removed');assert(container.textContent.includes('未进入签约冻结集'),'explanation');await click('删除 B.pdf');assert(!container.textContent.includes('B.pdf')&&container.textContent.includes('A.pdf'),'only pending removed');assert(container.textContent.includes('冻结内容 · v1'),'signed version retained');}],
 ['edit and unbalanced plan block confirmation',async h=>{await input('节点金额 1','299.99');assert(container.textContent.includes('未保存修改'),'dirty state');await click('保存合同资料');assert(container.textContent.includes('付款节点合计必须等于合同金额'),'unbalanced error');assert(container.querySelector('input[type=checkbox]').disabled,'cannot confirm');}],
 ['version conflict preserves edits',async h=>{h.setMode('conflict');await input('合同名称','未保存的新名称');await click('保存合同资料');assert(container.textContent.includes('版本已变化'),'conflict visible');assert([...container.querySelectorAll('input')].some(x=>x.value==='未保存的新名称'),'draft retained');}],
 ['upload failure does not claim success or signing',async h=>{const el=container.querySelector('input[type=file]');await act(async()=>{Object.defineProperty(el,'files',{configurable:true,value:[new File(['bad'],'fake.pdf',{type:'application/pdf'})]});el.dispatchEvent(new Event('change',{bubbles:true}));});await click('上传附件');for(let n=0;n<10&&!container.querySelector('[role=alert]');n++)await flush();assert(container.textContent.includes('文件内容与允许'),'actual upload failure');assert(!container.textContent.includes('上传已就绪'),'no success');}],
 ['lost signing response retries same command then readonly',async h=>{h.setMode('lost');await act(async()=>container.querySelector('input[type=checkbox]').click());await click('登记签约并生成订单');assert(container.querySelector('[role=alert]'),'error shown');await click('登记签约并生成订单');assert(h.calls.length===2&&h.calls[0].key===h.calls[1].key,'retry key stable');assert(container.textContent.includes('已签合同 · 冻结内容'),'signed readonly');assert(![...container.querySelectorAll('button')].some(x=>x.textContent==='登记签约并生成订单'),'no repeat business action');}],
 ['late successful response cannot cross enterprise',async h=>{let release;h.defer(new Promise(r=>release=r));await click('重新载入合同');crmRequests.bind({tenant_id:'B',context_id:'B1'});await act(async()=>release(new Response(JSON.stringify({...base,fields:{...base.fields,name:'LATE_A_SUCCESS'}}),{status:200})));await flush();assert(!container.textContent.includes('LATE_A_SUCCESS'),'old successful result fenced');}]
];
const results=[];for(const [name,test] of tests){const h=await setup();try{await test(h);results.push({name,status:'passed'});}catch(e){results.push({name,status:'failed',error:e.message});}finally{await h.close();}out.textContent=JSON.stringify(results,null,2);}out.dataset.status=results.every(x=>x.status==='passed')?'passed':'failed';
