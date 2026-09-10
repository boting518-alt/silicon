import {useEffect,useRef,useState} from 'react';
import type {components} from '../../../packages/api-client/schema';
import {crmRequests,StaleResponse,ApiError,isContextError,errorMessage} from './api';
import type {ContextTicket} from './api';
type S=components['schemas'];type Candidate=S['Candidate'];type Published=S['Published'];type Contract=S['Contract'];type Frozen=S['Frozen'];
const names:Record<string,string>={pending:'待审批',approved:'已批准',rejected:'已驳回',invalidated:'审批失效，需重新提交',published:'已发布',issued:'有效',withdrawn:'已撤回',expired:'已过期'};
const errors:Record<string,string>={PUBLICATION_POLICY_REQUIRED:'未配置有效发布政策，不能提交或发布。',PUBLICATION_HARD_BLOCK:'存在缺价、缺件、停用或确定性不兼容，不能人工绕过。',APPROVAL_INVALIDATED:'审批绑定内容已变化，原审批失效，请重新提交审批。',SELF_APPROVAL_FORBIDDEN:'提交人不能审批自己的候选，请分配另一位授权人员。',RISK_CONFIRMATION_REQUIRED:'请逐项填写风险确认说明和依据。',RISK_POLICY_FORBIDS:'本政策不允许人工放行未知风险。',APPROVAL_REQUIRED:'此版本尚未获得有效批准。',APPROVAL_ALREADY_DECIDED:'已有审批终局，请刷新查看。',SOURCE_NOT_ACTIVE:'源报价已撤回或过期，不能新转合同。',PARTICIPANT_ACCESS_CHANGED:'提交人或审批人的当前权限已变化，需重新分配审批。',DISCOUNT_QUOTA_UNSUPPORTED:'不支持有限次数或预算的折扣政策，禁止按无限额发布。',QUOTE_EXPIRED:'报价有效期已结束。',VERSION_CONFLICT:'版本已变化，请刷新后重新确认。',FORBIDDEN:'当前身份无权执行该操作。',PUBLISHED_DRAFT_REQUIRES_REVISION:'已发布草稿不能原位修改，请从发布版本创建修订草稿。'};
function message(e:unknown){return e instanceof ApiError?(errors[e.code]??`${errorMessage(e)} (${e.code})`):errorMessage(e);}
function useCommands(context:ContextTicket,onError:(e:unknown)=>void){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[code,setCode]=useState('');const epoch=useRef(0),keys=useRef(new Map<string,string>());
 useEffect(()=>()=>{epoch.current++;},[context.context_id]);
 async function run<T>(work:()=>Promise<T>,done:(v:T)=>void,text=''){
  const n=epoch.current;setBusy(true);setError('');setCode('');setNotice('');
  try{const v=await work();if(n===epoch.current&&crmRequests.isCurrent(context)){done(v);setNotice(text);}}
  catch(e){if(n!==epoch.current||e instanceof StaleResponse)return;if(isContextError(e)||e instanceof ApiError&&e.status===401)onError(e);else {setError(message(e));setCode(e instanceof ApiError?e.code:'');}}
  finally{if(n===epoch.current)setBusy(false);}
 }
 function post<T>(path:string,body:unknown){const sig=JSON.stringify([path,body]);if(!keys.current.has(sig))keys.current.set(sig,crypto.randomUUID());return crmRequests.request<T>(context,'/publication'+path,{method:'POST',headers:{'Idempotency-Key':keys.current.get(sig)!},body:JSON.stringify(body)});}
 return {busy,error,notice,code,run,post};
}
export function DraftSubmission({context,draft,dirty,disabled,onContextError}:{context:ContextTicket;draft:S['QuoteDetail'];dirty:boolean;disabled:boolean;onContextError:(e:unknown)=>void}){
 const [until,setUntil]=useState(''),[items,setItems]=useState<Candidate[]>([]);const cmd=useCommands(context,onContextError);
 useEffect(()=>{void cmd.run(()=>crmRequests.request<Candidate[]>(context,'/publication/candidates'),v=>setItems(v.filter(x=>x.draft_id===draft.id)));},[draft.id,draft.version]);
 const latest=items.at(-1);
 return <section className="panel publication-panel"><h3>审批与发布</h3><p>{dirty?'未保存修改：不得使用旧审批发布，请先保存再重新提交。':latest?`${names[latest.state]} · 草稿 v${latest.draft_version}`:'已保存草稿，尚未提交审批'}</p>
 <p>所有报价均需另一授权人员审批。UNKNOWN 保留原状态，缺价或确定性 BLOCK 不能放行。</p>
 <label>报价有效期（本地时间）<input type="datetime-local" value={until} disabled={disabled||cmd.busy} onChange={e=>setUntil(e.target.value)}/></label>
 <button className="primary" disabled={dirty||disabled||cmd.busy||!until} onClick={()=>void cmd.run(()=>cmd.post<Candidate>('/drafts/'+draft.id+'/submit',{expected_version:draft.version,valid_until:new Date(until).toISOString()}),v=>setItems([...items,v]),'已冻结候选并提交审批。请由另一授权人员进入报价审批查看。')}>提交审批</button>
 {cmd.error&&<p className="error" role="alert">{cmd.error}</p>}{cmd.notice&&<p role="status">{cmd.notice}</p>}</section>;
}
function Content({value}:{value:Frozen}){
 return <><div className="asset-hero"><span className="eyebrow">{value.development?'演示数据 / 开发政策，不用于真实商务':'正式政策 / 系统内报价'}</span><h3>{value.customer.name} · {value.customer.project.name}</h3><p>{value.config.name} · {value.config.quantity} 台</p></div>
 <div className="kv"><div><label>冻结总额</label><strong>{value.calculation.total} CNY · {value.calculation.tax_included?'含税':'不含税'}</strong><p>有效至 {value.valid_until}</p></div><div><label>发布政策</label><p>v{value.policy.version} · {value.policy.responsibility}</p><p>成本、利润、税额拆分、运费及服务费：未配置</p></div></div>
 <h3>设备与商业内容</h3><p>{value.host.name} · {value.host.brand} · {value.host.brand_kind==='own'?'自有品牌':'第三方品牌'}</p>
 {value.calculation.technical_lines.map((x,n)=><p key={n}>{x.sku.name} ×{x.quantity} · {x.charge_mode==='included'?'含于包件，不重复收费':'另计价'}</p>)}
 {value.calculation.priced_lines.map(x=><div className="line" key={x.sku_id}><span>{x.name} ×{x.quantity}<small>{x.source.source} · 价格表 v{x.source.revision} · {x.source.valid_from} → {x.source.valid_to}</small></span><b>{x.line_amount} CNY</b></div>)}
 <p>优惠 {value.calculation.discount_amount} CNY · {value.calculation.discount?.name??'无折扣'}；无额度占用或核销。</p>
 <h3>原始风险与检查范围</h3>{value.calculation.checks.map((x,n)=><p className={'quote-check check-'+x.status.toLowerCase()} key={n}><b>{x.status}</b> · {x.message}</p>)}
 <h3>合同字段来源</h3><p>客户及项目来自冻结 CRM 内容，地点不冒称甲方注册地址。乙方主体资料待补齐。</p>{value.customer.contacts.map(x=><p key={x.id}>{x.name} · {x.title||'职务未配置'}</p>)}{value.customer.sites.map(x=><p key={x.id}>地点：{x.name} · {x.address}</p>)}<p>内部负责人：{value.customer.responsibilities.length?value.customer.responsibilities.map(x=>`${x.role} / ${value.customer.responsibility_names[x.user_id]??x.user_id}`).join('；'):'待分配，不默认使用登录人'}</p>
 </>;
}
export function PublicationDesk({context,contractsOnly=false,canApprove,canWrite,disabled,onContextError}:{context:ContextTicket;contractsOnly?:boolean;canApprove:boolean;canWrite:boolean;disabled:boolean;onContextError:(e:unknown)=>void}){
 const [candidates,setCandidates]=useState<Candidate[]>([]),[versions,setVersions]=useState<Published[]>([]),[contracts,setContracts]=useState<Contract[]>([]);
 const [selection,setSelection]=useState<{kind:'candidate'|'version'|'contract';id:string}|null>(null),[note,setNote]=useState(''),[confirm,setConfirm]=useState(false),[risks,setRisks]=useState<Record<string,{explanation:string;evidence:string}>>({});
 const cmd=useCommands(context,onContextError);const locked=cmd.busy||disabled;
 const load=()=>Promise.all([crmRequests.request<Candidate[]>(context,'/publication/candidates'),crmRequests.request<Published[]>(context,'/publication/versions'),crmRequests.request<Contract[]>(context,'/publication/contracts')]);
 function apply(data:Awaited<ReturnType<typeof load>>){setCandidates(data[0]);setVersions(data[1]);setContracts(data[2]);}
 function refresh(){void cmd.run(load,apply);}
 useEffect(refresh,[context.context_id]);
 function select(kind:'candidate'|'version'|'contract',id:string){setSelection({kind,id});setNote('');setConfirm(false);setRisks({});}
 useEffect(()=>{if(cmd.code==='APPROVAL_INVALIDATED'&&selection?.kind==='candidate')setCandidates(rows=>rows.map(x=>x.id===selection.id?{...x,state:'invalidated'}:x));},[cmd.code]);
 const candidate=selection?.kind==='candidate'?candidates.find(x=>x.id===selection.id):undefined;
 const version=selection?.kind==='version'?versions.find(x=>x.id===selection.id):undefined;
 const contract=selection?.kind==='contract'?contracts.find(x=>x.id===selection.id):undefined;
 async function action(path:string,body:unknown,doneText:string,next?:'version'|'contract'){
  void cmd.run(async()=>{const result=await cmd.post<{id:string}>(path,body);const data=await load();return {result,data};},({result,data})=>{apply(data);if(next)select(next,result.id);setConfirm(false);},doneText);
 }
 return <section className="panel publication-panel"><div className="panel-title"><div><h2>{contractsOnly?'来源合同草稿':'报价审批与版本历史'}</h2><p>内部发布，不发送外部；合同草稿不代表签约或收入。</p></div><button disabled={locked} onClick={refresh}>刷新状态</button></div>
 {cmd.error&&<p role="alert" className="error">{cmd.error}</p>}{cmd.notice&&<p role="status">{cmd.notice}</p>}
 <div className="publication-layout"><nav aria-label="版本列表">
 {!contractsOnly&&<><h3>审批候选</h3>{candidates.map(x=><button disabled={locked} key={x.id} onClick={()=>select('candidate',x.id)}>{x.content.config.name} · v{x.draft_version} · {names[x.state]}</button>)}<h3>已发布版本</h3>{versions.map(x=><button disabled={locked} key={x.id} onClick={()=>select('version',x.id)}>{x.number} · {names[x.state]}</button>)}</>}
 <h3>合同草稿</h3>{contracts.map(x=><button disabled={locked} key={x.id} onClick={()=>select('contract',x.id)}>{x.content.customer.name} · 来源 {versions.find(v=>v.id===x.quote_version_id)?.number??x.quote_version_id}</button>)}{!contracts.length&&<p>暂无来源合同草稿</p>}</nav>
 <article>{!candidate&&!version&&!contract&&<p className="empty">请选择记录查看冻结详情。</p>}
 {candidate&&<><h2>{names[candidate.state]} · 候选 v{candidate.draft_version}</h2><p className="publication-id">提交人 {candidate.submitter_id}<br/>候选 {candidate.id}<br/>内容 hash {candidate.content_hash}</p><Content value={candidate.content}/>
 {candidate.note&&<p>内部审批说明：{candidate.note}</p>}{candidate.confirmations?.map(x=><p key={x.code}>风险确认 {x.code}：{x.explanation}；依据：{x.evidence}</p>)}
 {candidate.state==='pending'&&canApprove&&<fieldset disabled={locked}><legend>逐项风险确认（保留原 WARN / UNKNOWN）</legend>{candidate.content.calculation.checks.filter(x=>['WARN','UNKNOWN'].includes(x.status)).map(x=><div className="nested-card" key={x.code}><strong>{x.code} · {x.message}</strong><label>说明 {x.code}<input value={risks[x.code]?.explanation??''} onChange={e=>setRisks({...risks,[x.code]:{explanation:e.target.value,evidence:risks[x.code]?.evidence??''}})}/></label><label>依据 {x.code}<input value={risks[x.code]?.evidence??''} onChange={e=>setRisks({...risks,[x.code]:{explanation:risks[x.code]?.explanation??'',evidence:e.target.value}})}/></label></div>)}<label>审批说明<input value={note} onChange={e=>setNote(e.target.value)}/></label><button onClick={()=>void action('/candidates/'+candidate.id+'/decide',{expected_version:candidate.draft_version,approved:true,note,confirmations:Object.entries(risks).map(([code,v])=>({code,...v}))},'审批决定已记录。')}>批准当前候选</button><button onClick={()=>void action('/candidates/'+candidate.id+'/decide',{expected_version:candidate.draft_version,approved:false,note,confirmations:[]},'驳回已记录。')}>驳回当前候选</button></fieldset>}
 {candidate.state==='approved'&&canApprove&&<fieldset disabled={locked}><legend>人工确认发布</legend><p>确认上述候选、总额、口径、有效期与开发标记；发布后不可改写。</p><label><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>我确认发布此批准版本</label><button className="primary" disabled={!confirm} onClick={()=>void action('/candidates/'+candidate.id+'/issue',{expected_version:candidate.draft_version,confirmed:true},'已生成不可变发布版本。','version')}>发布批准版本</button></fieldset>}
 </>}
 {version&&<><h2>{version.number} · {names[version.state]}</h2><p className="publication-id">修订 {version.revision} · 发布 {version.issued_at} · 审批 {version.decision_id}<br/>内容 hash {version.content_hash}</p><Content value={version.content}/><div className="modal-actions"><button disabled={locked||!canWrite||version.state!=='issued'} onClick={()=>void action('/contracts/from-quote',{quote_version_id:version.id,expected_version:version.version},'合同草稿已保存；重复操作返回同一份。','contract')}>转合同草稿</button><button disabled={locked||!canWrite} onClick={()=>void action('/versions/'+version.id+'/revise',{expected_version:version.version},'独立修订草稿已建立，请在报价工作室重新打开；旧审批不继承。')}>创建修订草稿</button></div>{canApprove&&version.state!=='withdrawn'&&<fieldset disabled={locked}><label>撤回原因<input value={note} onChange={e=>setNote(e.target.value)}/></label><button onClick={()=>void action('/versions/'+version.id+'/withdraw',{expected_version:version.version,reason:note},'撤回已记录，冻结内容保持。')}>撤回报价</button></fieldset>}</>}
 {contract&&<><h2>合同草稿 · 尚未签约</h2><p>复制时间 {contract.created_at} · 来源 {contract.source_number} · 发布 {contract.issued_at}</p><p className="publication-id">审批记录 {contract.decision_id} · 发布人 {contract.issuer_id}</p>{contract.source_state!=='issued'&&<p role="alert" className="error">来源已{names[contract.source_state]}，草稿保留；签约资格尚未实施。</p>}<Content value={contract.content}/><p>待补齐：乙方主体资料、付款节点、附件与签约信息（TASK-007）。</p><p className="publication-id">来源 {contract.quote_version_id} · hash {contract.source_hash}</p><button disabled={locked} onClick={()=>select('version',contract.quote_version_id)}>返回来源报价版本</button></>}
 </article></div></section>;
}
