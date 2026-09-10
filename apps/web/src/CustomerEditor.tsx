import { useEffect, useRef, useState } from 'react';
import type { Customer, CustomerInput, Member } from './api';
import { crmRequests, ApiError, errorMessage, StaleResponse, isContextError } from './api';
import type { ContextTicket } from './api';

const uuid=()=>crypto.randomUUID();
const blank:CustomerInput={number:'',name:'',province:'',city:'',industry:'',level:'普通客户',stage:'跟进中',notes:'',contacts:[],projects:[],sites:[],responsibilities:[]};
function inputOf(c:Customer):CustomerInput {
  return {number:c.number,name:c.name,province:c.province,city:c.city,industry:c.industry,level:c.level as CustomerInput['level'],
    stage:c.stage as CustomerInput['stage'],notes:c.notes,contacts:c.contacts,projects:c.projects,sites:c.sites,responsibilities:c.responsibilities};
}
export function CustomerEditor({customer,members,onSaved,onReload,onCancel,onAuthExpired,context,disabled}:{context:ContextTicket;disabled:boolean;customer:Customer|null;members:Member[];onSaved:(c:Customer)=>void;onReload:()=>void;onCancel:()=>void;onAuthExpired:(e:unknown)=>void}) {
  const [draft,setDraft]=useState<CustomerInput>(()=>customer?inputOf(customer):{...blank});
  const [message,setMessage]=useState(''); const [conflict,setConflict]=useState(false); const [busy,setBusy]=useState(false);
  const errorRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(message){errorRef.current?.focus();errorRef.current?.scrollIntoView({block:'center'});}},[message]);
  const attempt=useRef({body:'',key:uuid()});
  function change<K extends keyof CustomerInput>(field:K,value:CustomerInput[K]) { setDraft(d=>({...d,[field]:value})); }
  const contacts=draft.contacts ?? [], projects=draft.projects ?? [], sites=draft.sites ?? [];
  async function save(event:React.FormEvent) {
    event.preventDefault(); if(busy||disabled)return; setBusy(true);setMessage('');setConflict(false);
    const body=JSON.stringify({...draft,...(customer?{expected_version:customer.version}:{})});
    if(attempt.current.body!==body)attempt.current={body,key:uuid()};
    try { onSaved(await crmRequests.request<Customer>(context,'/crm/customers'+(customer?'/'+customer.id:''),{method:customer?'PUT':'POST',body,headers:{'Idempotency-Key':attempt.current.key}})); }
    catch(error){if(error instanceof StaleResponse)return;if(isContextError(error)||(error instanceof ApiError&&error.status===401)){onAuthExpired(error);return;}setMessage(errorMessage(error));setConflict(error instanceof ApiError && error.code==='VERSION_CONFLICT');}
    finally{setBusy(false);}
  }
  return <form onSubmit={save} aria-label="客户编辑表单">
    <p className="form-intro">客户独立建档。客户侧联系人与内部负责人分别记录，保存后可刷新查询。</p>
    <fieldset disabled={busy||disabled}><div className="edit-grid">
      <label>客户编号<input required maxLength={40} value={draft.number} onChange={e=>change('number',e.target.value)}/></label>
      <label>客户名称<input required maxLength={160} value={draft.name} onChange={e=>change('name',e.target.value)}/></label>
      <label>省份<input maxLength={160} value={draft.province} onChange={e=>change('province',e.target.value)}/></label>
      <label>城市<input maxLength={160} value={draft.city} onChange={e=>change('city',e.target.value)}/></label>
      <label>行业<input maxLength={160} value={draft.industry} onChange={e=>change('industry',e.target.value)}/></label>
      <label>客户关系<select value={draft.level} onChange={e=>change('level',e.target.value as CustomerInput['level'])}>{['普通客户','重点客户','战略客户'].map(x=><option key={x}>{x}</option>)}</select></label>
      <label>跟进阶段<select value={draft.stage} onChange={e=>change('stage',e.target.value as CustomerInput['stage'])}>{['跟进中','稳定合作','交付推进','续保跟进'].map(x=><option key={x}>{x}</option>)}</select></label>
    </div>
    <section className="modal-section"><h3>客户侧联系人</h3>{contacts.map((contact,index)=><div className="nested-card" key={contact.id}>
      <div className="edit-grid">{(['name','title','phone','email'] as const).map((key)=><label key={key}>{`联系人 ${index+1} ${ {name:'姓名',title:'职务',phone:'电话',email:'邮箱'}[key]}`}<input required={key==='name'} type={key==='email'?'email':'text'} maxLength={key==='phone'?40:key==='email'?254:160} value={contact[key] ?? ''} onChange={e=>change('contacts',contacts.map(c=>c.id===contact.id?{...c,[key]:e.target.value}:c))}/></label>)}</div>
      <button type="button" onClick={()=>{change('contacts',contacts.filter(c=>c.id!==contact.id));change('projects',projects.map(p=>({...p,people:p.people?.filter(person=>person.contact_id!==contact.id)})));}}>移除联系人 {index+1}</button>
    </div>)}<button type="button" onClick={()=>change('contacts',[...contacts,{id:uuid(),name:'',title:'',phone:'',email:''}])}>添加联系人</button></section>
    <section className="modal-section"><h3>关联项目</h3>{projects.map((project,index)=><div className="nested-card" key={project.id}>
      <label>项目 {index+1} 名称<input required maxLength={160} value={project.name} onChange={e=>change('projects',projects.map(p=>p.id===project.id?{...p,name:e.target.value}:p))}/></label>
      <p>选择本客户的联系人，可一人承担多个角色。</p><div className="people-choices">{contacts.filter(c=>c.name).map(c=><div key={c.id}><strong>{c.name}</strong>{(['project_lead','key_person'] as const).map(role=><label className="checkbox" key={role}><input type="checkbox" checked={project.people?.some(p=>p.contact_id===c.id&&p.role===role) ?? false} onChange={e=>change('projects',projects.map(p=>p.id!==project.id?p:{...p,people:e.target.checked?[...(p.people??[]),{contact_id:c.id,role}]:(p.people??[]).filter(person=>person.contact_id!==c.id||person.role!==role)}))}/>{role==='project_lead'?'项目负责人':'关键人'}</label>)}</div>)}</div>
      <label>项目 {index+1} 说明<textarea maxLength={2000} value={project.notes} onChange={e=>change('projects',projects.map(p=>p.id===project.id?{...p,notes:e.target.value}:p))}/></label>
      <button type="button" onClick={()=>change('projects',projects.filter(p=>p.id!==project.id))}>移除项目 {index+1}</button>
    </div>)}<button type="button" onClick={()=>change('projects',[...projects,{id:uuid(),name:'',notes:'',people:[]}])}>添加项目</button></section>
    <section className="modal-section"><h3>内部责任分工</h3><div className="edit-grid">{(['sales','service'] as const).map(role=><label key={role}>{role==='sales'?'内部销售负责人':'内部售后负责人'}<select value={draft.responsibilities?.find(r=>r.role===role)?.user_id ?? ''} onChange={e=>change('responsibilities',[...(draft.responsibilities??[]).filter(r=>r.role!==role),...(e.target.value?[{role,user_id:e.target.value}]:[])])}><option value="">暂未分配</option>{members.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>)}</div></section>
    <section className="modal-section"><h3>装机地点</h3>{sites.map((site,index)=><div className="nested-card edit-grid" key={site.id}><label>地点 {index+1} 名称<input required maxLength={160} value={site.name} onChange={e=>change('sites',sites.map(s=>s.id===site.id?{...s,name:e.target.value}:s))}/></label><label>地点 {index+1} 地址<input required maxLength={300} value={site.address} onChange={e=>change('sites',sites.map(s=>s.id===site.id?{...s,address:e.target.value}:s))}/></label><button type="button" onClick={()=>change('sites',sites.filter(s=>s.id!==site.id))}>移除地点 {index+1}</button></div>)}<button type="button" onClick={()=>change('sites',[...sites,{id:uuid(),name:'',address:''}])}>添加装机地点</button></section>
    <label className="note-label">客户备注<textarea maxLength={2000} value={draft.notes} onChange={e=>change('notes',e.target.value)}/></label>
    </fieldset>
    {message&&<div className="error" role="alert" ref={errorRef} tabIndex={-1}>{message}{conflict&&<button type="button" onClick={onReload}>重新载入最新版本</button>}</div>}
    <div className="modal-actions"><button className="primary" type="submit" disabled={busy||disabled}>{busy?'正在保存…':'保存客户'}</button><button type="button" disabled={busy||disabled} onClick={onCancel}>取消</button></div>
  </form>;
}
