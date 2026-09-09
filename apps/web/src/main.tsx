import { StrictMode, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, errorMessage } from './api';
import type { Session, Customer, CustomerPage, Member } from './api';
import { CustomerEditor } from './CustomerEditor';
import '../../../packages/ui/tokens.css';
import './style.css';

const navigation=[['▧','业务驾驶舱'],['◇','报价与利润'],['▤','交付与验收'],['⚙','售后与部件'],['↗','续保与扩容'],['◫','经营总览'],['◉','客户管理'],['▤','合同管理'],['▥','设备查询'],['▣','采购合同'],['▦','库存管理'],['◷','周转分析']];
const roles:Record<string,string>={project_lead:'项目负责人',key_person:'关键人',sales:'内部销售负责人',service:'内部售后负责人'};
function Dialog({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const origin=document.activeElement as HTMLElement; const dialog=ref.current!;dialog.showModal();return()=>{dialog.close();if(origin?.isConnected)origin.focus();};},[]);
  return <dialog ref={ref} aria-labelledby="modal-title" onCancel={onClose}><div className="modal-head"><div><div className="eyebrow">SILICON / WORKSPACE</div><h2 id="modal-title">{title}</h2></div><button aria-label="关闭" onClick={onClose}>✕</button></div><div className="modal-body">{children}</div></dialog>;
}
function CustomerView({customer,members,onEdit,canWrite}:{customer:Customer;members:Member[];onEdit:()=>void;canWrite:boolean}) {
  return <><div className="asset-hero"><span className="eyebrow">{customer.number} / {customer.province} · {customer.city}</span><h3>{customer.name}</h3><p>{customer.industry} · {customer.level} · {customer.stage}</p></div>
    <div className="kv"><div><label>内部责任分工</label>{customer.responsibilities.map(r=><p key={r.role}>{roles[r.role]}：{members.find(m=>m.id===r.user_id)?.name ?? '已停用成员'}</p>)}{!customer.responsibilities.length&&<p>暂未分配</p>}</div><div><label>关联记录</label><strong>{customer.contacts.length} 位联系人 · {customer.projects.length} 个项目</strong><p>合同和设备模块未启用</p></div></div>
    <section className="modal-section"><h3>客户侧联系人</h3>{customer.contacts.map(c=><div className="person" key={c.id}><span className="avatar">{c.name.slice(0,1)}</span><div><strong>{c.name}</strong><small>{c.title || '职务未填写'} · {c.phone || '电话未填写'}</small><small>{c.email}</small></div></div>)}{!customer.contacts.length&&<p>暂无联系人</p>}</section>
    <section className="modal-section"><h3>关联项目</h3>{customer.projects.map(p=><div className="nested-card" key={p.id}><h3>{p.name}</h3><p>{p.notes}</p>{p.people?.map(person=><p key={person.contact_id+person.role}>{roles[person.role]}：{customer.contacts.find(c=>c.id===person.contact_id)?.name}</p>)}</div>)}{!customer.projects.length&&<p>暂无项目</p>}</section>
    <section className="modal-section"><h3>装机地点</h3>{customer.sites.map(site=><p key={site.id}>{site.name} · {site.address}</p>)}{!customer.sites.length&&<p>暂无地点</p>}</section>
    <section className="modal-section"><h3>备注与角色历史</h3><p className="pre-wrap">{customer.notes || '暂无备注'}</p>{customer.role_history.map(r=><p key={r.id}>{r.project_name && `${r.project_name} · `}{roles[r.role]}：{r.person_name} · {r.valid_until?'历史分工':'当前分工'}</p>)}</section>
    <div className="modal-actions"><button className="primary" disabled={!canWrite} onClick={onEdit}>编辑客户</button><span className="muted">版本 {customer.version} · 已持久保存</span></div></>;
}
function App() {
  const [session,setSession]=useState<Session|null>(null),[authLoading,setAuthLoading]=useState(true),[busy,setBusy]=useState(false);
  const [message,setMessage]=useState(''),[notice,setNotice]=useState(''),[data,setData]=useState<CustomerPage|null>(null);
  const [members,setMembers]=useState<Member[]>([]),[loading,setLoading]=useState(false),[keyword,setKeyword]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0);
  const [modal,setModal]=useState<'detail'|'edit'|'create'|null>(null),[selected,setSelected]=useState<Customer|null>(null);
  const epoch=useRef(0);
  const tenant=session?.tenant_id;
  const canWrite=session?.memberships.find(m=>m.id===tenant)?.role!=='viewer';
  function clearCustomerState(){epoch.current++;setData(null);setMembers([]);setSelected(null);setModal(null);setQuery('');setKeyword('');setPage(1);setNotice('');}
  function handleError(e:unknown){setMessage(errorMessage(e));if(e instanceof ApiError&&e.status===401){setSession(null);clearCustomerState();}}
  async function loadSession(){setAuthLoading(true);try{setSession(await api<Session>('/session'));setMessage('');}catch(e){setSession(null);clearCustomerState();setMessage(e instanceof ApiError&&e.status===401?'请先登录企业身份。':errorMessage(e));}finally{setAuthLoading(false);}}
  useEffect(()=>{void loadSession();},[]);
  useEffect(()=>{
    if(!tenant)return;
    const abort=new AbortController();setLoading(true);setMessage('');
    Promise.all([api<CustomerPage>(`/crm/customers?q=${encodeURIComponent(query)}&page=${page}&page_size=10`,{signal:abort.signal}),api<Member[]>('/crm/members',{signal:abort.signal})])
      .then(([result,people])=>{if(!abort.signal.aborted){setData(result);setMembers(people);}})
      .catch(e=>{if(!abort.signal.aborted){setData(null);setMessage(errorMessage(e));if(e instanceof ApiError&&e.status===401){setSession(null);clearCustomerState();}}})
      .finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return()=>abort.abort();
  },[tenant,query,page,refresh]);
  async function switchTenant(id:string){setBusy(true);clearCustomerState();try{await api('/session/tenant',{method:'POST',body:JSON.stringify({tenant_id:id})});await loadSession();setRefresh(n=>n+1);}catch(e){handleError(e);}finally{setBusy(false);}}
  async function logout(){setBusy(true);try{const result=await api<{logout_url:string}>('/auth/logout',{method:'POST'});setSession(null);clearCustomerState();window.location.assign(result.logout_url);}catch(e){handleError(e);}finally{setBusy(false);}}
  async function openCustomer(id:string){const generation=epoch.current;setMessage('');try{const customer=await api<Customer>('/crm/customers/'+id);if(generation===epoch.current){setSelected(customer);setModal('detail');}}catch(e){if(generation===epoch.current){setSelected(null);setModal(null);handleError(e);}}}
  const generation=epoch.current;
  return <><aside className="sidebar"><a className="brand" href="/" aria-label="硅屿首页"><b>▧</b><span>硅屿 <small>SILICON</small></span></a><div className="side-caption">业务工作空间</div><nav aria-label="主导航">{navigation.map(([icon,label])=><button key={label} className={label==='客户管理'?'active':''} aria-current={label==='客户管理'?'page':undefined} disabled={label!=='客户管理'} title={label==='客户管理'?'客户管理':`${label}尚未启用`}><span>{icon}</span>{label}{label!=='客户管理'&&<small>未启用</small>}</button>)}</nav><div className="sidebar-bottom"><span className="avatar">{session?.user.name.slice(0,1) ?? '硅'}</span><div>{session?.user.name ?? '尚未登录'}<small>客户与服务协同</small></div></div></aside>
  <div className="shell"><header><span>业务管理 <i>/</i><b>客户管理</b></span><div className="identity-bar">{session&&<><select aria-label="当前企业" disabled={busy} value={tenant ?? ''} onChange={e=>void switchTenant(e.target.value)}><option value="" disabled>请选择企业</option>{session.memberships.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select><button disabled={busy} onClick={()=>void logout()}>退出登录</button></>}</div></header><main>
    <div className="heading"><div><div className="eyebrow">SALES & CUSTOMER INTELLIGENCE</div><h1>从一次成交，到长期合作<span>。</span></h1><p>独立客户档案，连接联系人、项目与内部责任分工。</p></div><span className="date">工作台 / {new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','.')}</span></div>
    {message&&<div className="error" role="alert">{message}</div>}{notice&&<p className="success" role="status">{notice}</p>}
    {!session?<section className="panel login-panel"><h2>{authLoading?'正在读取身份…':'进入客户工作空间'}</h2><p>使用企业身份登录后，选择企业访问客户档案。</p><a className="primary button-link" href="/api/v1/auth/login">使用企业身份登录</a><button onClick={()=>void loadSession()}>刷新登录状态</button></section>:!tenant?<section className="panel login-panel"><h2>请选择企业</h2><p>{session.memberships.length?'在右上方选择你要进入的企业。':'尚未加入企业，请联系管理员。'}</p></section>:<>
      <section className="metrics" aria-label="客户统计">{[['客户档案',data?.total,'家'],['联系人',data?.contact_total,'位'],['关联项目',data?.project_total,'个'],['覆盖地区',data?.province_total,'个']].map(([label,count,unit])=><div className="metric" key={label}><label>{label}</label><strong>{loading?'…':count??'—'} <em>{unit}</em></strong><small>当前企业 · 当前搜索范围</small></div>)}</section>
      <div className="analysis-filters"><span>客户管理</span><span className="muted">合同、报价、设备与库存模块尚未启用</span></div>
      <section className="panel"><div className="panel-title"><div><h2>客户档案</h2><p>客户独立于合同 · 点击客户查看档案</p></div><button className="primary" disabled={busy||!canWrite} onClick={()=>{setSelected(null);setModal('create');}}>新增客户</button></div>
        <form className="toolbar" role="search" onSubmit={e=>{e.preventDefault();setPage(1);setQuery(keyword);setRefresh(n=>n+1);}}><input aria-label="搜索客户" placeholder="搜索客户名称、编号、城市或联系人" maxLength={160} value={keyword} onChange={e=>setKeyword(e.target.value)}/><button type="submit">搜索</button><button type="button" onClick={()=>{setKeyword('');setQuery('');setPage(1);setRefresh(n=>n+1);}}>重置</button></form>
        <div className="devices-table"><div className="table-wrap" tabIndex={0} role="region" aria-label="客户表格，可横向滚动"><table><thead><tr>{['客户单位 / 行业','所在地区','客户关系','建档人员','联系人 / 项目','跟进阶段','档案'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{!loading&&data?.items.map(c=><tr key={c.id}><td><button className="customer-name" onClick={()=>void openCustomer(c.id)}>{c.name}</button><small>{c.number} · {c.industry||'行业未填写'}</small></td><td>{c.province||'—'} · {c.city||'—'}</td><td><span className="badge">{c.level}</span></td><td>{c.owner_name}</td><td>{c.contact_count} 位 / {c.project_count} 个</td><td><span className="badge">{c.stage}</span></td><td><button className="link" aria-label={`查看 ${c.name} 档案`} onClick={()=>void openCustomer(c.id)}>档案 ↗</button></td></tr>)}</tbody></table></div>
          {loading?<p className="empty" role="status">正在加载客户…</p>:data?.items.length===0?<p className="empty">没有匹配的客户。可调整搜索条件或新增客户。</p>:null}
          <div className="pagination"><span>{data?.total??'—'} 家客户 · 第 {page} 页</span><button disabled={loading||page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button><button disabled={loading||!data||page*10>=data.total} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
        </div></section>
    </>}
    <footer>硅屿 SILICON / BUSINESS STUDIO <span>企业内独立档案 · 操作记录可追溯</span></footer>
  </main></div>
  {modal&&tenant&&<Dialog title={modal==='create'?'新增客户':modal==='edit'?'编辑客户':'客户全景档案'} onClose={()=>setModal(null)}>
    {modal==='detail'&&selected?<CustomerView customer={selected} members={members} canWrite={canWrite} onEdit={()=>setModal('edit')}/>:<CustomerEditor key={selected?.version??'new'} customer={selected} members={members} onAuthExpired={handleError} onCancel={()=>setModal(null)} onReload={()=>{if(selected)void openCustomer(selected.id);}} onSaved={c=>{if(generation!==epoch.current)return;setSelected(c);setModal('detail');setRefresh(n=>n+1);setNotice('客户已保存，可刷新查询。');}}/>}
  </Dialog>}
  </>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
