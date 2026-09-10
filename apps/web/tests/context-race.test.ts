// Successful HTTP delivery is deliberately gated, not rejected or timed out.
// Transport is a test double; the production request wrapper and response fence run unchanged.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CrmRequests,StaleResponse} from '../src/api.ts';

for(const [surface,method,path] of [
  ['list','GET','/crm/customers'],['detail','GET','/crm/customers/one'],
  ['new form','POST','/crm/customers'],['edit form','PUT','/crm/customers/one'],
]) {
  test(`delayed successful ${surface} response never updates the new enterprise`,async()=>{
    const original=globalThis.fetch;
    let release!:()=>void; const gate=new Promise<void>(resolve=>release=resolve);
    let arrived!:()=>void; const started=new Promise<void>(resolve=>arrived=resolve);
    let delivered=false; const state={value:'B current state'};
    // Only the CSRF cookie is faked for this transport-level test, not a browser login.
    Object.defineProperty(globalThis,'document',{value:{cookie:''},configurable:true});
    globalThis.fetch=async(_url,init)=>{
      assert.equal(new Headers(init?.headers).get('X-Expected-Tenant'),'A');
      assert.equal(new Headers(init?.headers).get('X-Session-Context'),'A-1');
      arrived();await gate;delivered=true;
      // Model a completed response whose callback arrives even after best-effort abort.
      return new Response(JSON.stringify({value:'A old success'}),{status:200});
    };
    try {
      const requests=new CrmRequests();requests.bind({tenant_id:'A',context_id:'A-1'});
      const pending=requests.request<{value:string}>(requests.capture(),path,{method})
        .then(value=>{state.value=value.value;});
      const rejected=assert.rejects(pending,StaleResponse);
      await started;
      requests.bind({tenant_id:'B',context_id:'B-1'});
      release();await rejected;
      assert.equal(delivered,true);assert.equal(state.value,'B current state');
    }finally{release();globalThis.fetch=original;Reflect.deleteProperty(globalThis,'document');}
  });
}

test('a discarded form ticket cannot issue another request after A/B/A',async()=>{
  const requests=new CrmRequests();requests.bind({tenant_id:'A',context_id:'1'});
  const old=requests.capture();requests.bind(null);requests.bind({tenant_id:'A',context_id:'3'});
  await assert.rejects(requests.request(old,'/crm/customers',{method:'POST'}),StaleResponse);
});
