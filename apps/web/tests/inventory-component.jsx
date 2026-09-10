import React,{act} from 'react';import {createRoot} from 'react-dom/client';import {Inventory} from '../src/Inventory';import {crmRequests} from '../src/api';
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const container=document.querySelector('#fixture'),out=document.querySelector('#results');const results=[];
function assert(v,m){if(!v)throw Error(m)}
const flush=()=>act(()=>new Promise(r=>setTimeout(r,15)));
async function click(label){await act(async()=>{const b=[...container.querySelectorAll('button')].find(x=>x.textContent===label);assert(b,'button '+label);b.click();});await flush();}
async function test(name,run){try{await run();results.push({name,status:'passed'});}catch(e){results.push({name,status:'failed',message:String(e)});}out.textContent=JSON.stringify(results,null,2);}
async function setup(){const old=globalThis.fetch;let pending,keys=[],fail=false;
 globalThis.fetch=async(url,init={})=>{const path=String(url).replace('/api/v1','');let data=[];
 if(path==='/inventory/context')data={permissions:['inventory.read','purchase.read','purchase.write','inventory.configure'],tracking:[]};
 else if(path==='/inventory/stock')data={items:[],available_quantity:0,unit:'piece',reservation_state:'not_implemented',as_of:'2026-09-11T00:00:00Z'};
 else if(path==='/inventory/summary')data={pending_quantity:0,quarantine_quantity:0,remaining_quantity:0};
 else if(path==='/inventory/suppliers'&&init.method==='POST'){keys.push(new Headers(init.headers).get('Idempotency-Key'));if(fail){fail=false;return new Response(JSON.stringify({code:'TEST_LOST_RESPONSE'}),{status:503});}data={id:'supplier'};}
 else if(path==='/inventory/suppliers'&&pending){const p=pending;pending=null;await p;data=[{id:'old',name:'OLD_A_SUPPLIER'}];}
 return new Response(JSON.stringify(data),{status:200});};
 crmRequests.bind({tenant_id:'A',context_id:'A1'});const root=createRoot(container);await act(async()=>root.render(<Inventory context={crmRequests.capture()} members={[]} onContextError={()=>{}}/>));for(let i=0;i<5;i++)await flush();
 return {keys,fail(){fail=true},delay(p){pending=p},root,async close(){await act(async()=>root.unmount());globalThis.fetch=old;crmRequests.bind(null)}};
}
await test('lost supplier response retries same intent; no false success',async()=>{const h=await setup();try{await click('基础资料');h.fail();await click('新增供应商');assert(container.querySelector('[role=alert]'),'error shown');assert(!container.textContent.includes('供应商已保存。'),'no false success');await click('新增供应商');assert(h.keys.length===2&&h.keys[0]===h.keys[1],'retry same command');assert(container.textContent.includes('供应商已保存。'),'success after retry');}finally{await h.close()}});
await test('late successful old enterprise refresh cannot repopulate new page',async()=>{const h=await setup();let release;try{h.delay(new Promise(r=>release=r));await click('刷新');crmRequests.bind({tenant_id:'B',context_id:'B1'});await act(async()=>h.root.render(<Inventory key="B" context={crmRequests.capture()} members={[]} onContextError={()=>{}}/>));release();for(let i=0;i<8;i++)await flush();await click('基础资料');assert(!container.textContent.includes('OLD_A_SUPPLIER'),'old success dropped');}finally{release?.();await h.close()}});
