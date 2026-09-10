import type { components } from '../../../packages/api-client/schema';
export type Session = components['schemas']['SessionInfo'];
export type Customer = components['schemas']['CustomerDetail'];
export type CustomerInput = components['schemas']['CustomerInput'];
export type CustomerPage = components['schemas']['CustomerPage'];
export type Member = components['schemas']['Member'];

export class ApiError extends Error {
  status:number; code:string;
  constructor(status:number,code:string,message:string){super(message);this.status=status;this.code=code;}
}
const messages: Record<string,string> = {
  CONTEXT_CHANGED:'企业上下文已变化，旧表单已失效。请重新选择企业；不会自动保存或迁移旧草稿。',
  CONTEXT_REQUIRED:'页面缺少企业上下文，请重新选择企业。',
  UNAUTHENTICATED:'登录已失效，请重新登录。', FORBIDDEN:'你没有执行此操作的权限。',
  TENANT_REQUIRED:'请先选择企业。', CSRF_REJECTED:'页面验证已失效，请刷新登录状态后重试。',
  NOT_FOUND:'客户不存在或你无权查看。', VERSION_CONFLICT:'此客户已被其他人修改。请重新载入最新版本，再合并你的修改。',
  CUSTOMER_NUMBER_EXISTS:'该客户编号已存在，请使用其他编号。', IDEMPOTENCY_CONFLICT:'本次提交内容已变化，请重新打开编辑。',
  INVALID_RELATIONSHIP:'联系人或项目关系无效，请检查关联内容。', INVALID_RESPONSIBILITY:'所选内部负责人已不属于当前企业。',
};
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== 'GET') {
    if(!headers.has('Content-Type'))headers.set('Content-Type','application/json');
    headers.set('X-CSRF-Token',document.cookie.split('; ').find(x=>x.startsWith('__Host-silicon-csrf='))?.split('=')[1] ?? '');
  }
  const response=await fetch('/api/v1'+path,{...init,headers,signal:init.signal ?? AbortSignal.timeout(10000)});
  const data=await response.json();
  if (!response.ok) throw new ApiError(response.status,data.code ?? 'INVALID_INPUT',messages[data.code] ??
    (response.status===422 ? '输入格式不正确，请检查必填项、邮箱和关联关系。' : '服务暂不可用，操作尚未确认完成。'));
  return data as T;
}
export function errorMessage(error:unknown):string { return error instanceof ApiError ? error.message : '网络暂不可用，请稍后重试；未确认保存成功。'; }

export type CrmContext = {tenant_id:string;context_id:string};
export type ContextTicket = CrmContext & {generation:number;signal:AbortSignal};
export class StaleResponse extends Error {}
/** Requests are pinned when issued, never rebound when a later session arrives. */
export class CrmRequests {
  private generation=0;
  private controller=new AbortController();
  private context:CrmContext|null=null;
  bind(context:CrmContext|null){this.controller.abort();this.controller=new AbortController();this.generation++;this.context=context;}
  capture():ContextTicket {
    if(!this.context)throw new StaleResponse('Select an enterprise first');
    return {...this.context,generation:this.generation,signal:this.controller.signal};
  }
  isCurrent(ticket:ContextTicket){return ticket.generation===this.generation && !ticket.signal.aborted;}
  async request<T>(ticket:ContextTicket,path:string,init:RequestInit={}):Promise<T>{
    if(!this.isCurrent(ticket))throw new StaleResponse();
    const headers=new Headers(init.headers);
    headers.set('X-Expected-Tenant',ticket.tenant_id);headers.set('X-Session-Context',ticket.context_id);
    try {
      const value=await api<T>(path,{...init,headers,signal:AbortSignal.any([ticket.signal,AbortSignal.timeout(10000),...(init.signal?[init.signal]:[])])});
      // Abort is best effort: a fully successful old response must also be fenced.
      if(!this.isCurrent(ticket))throw new StaleResponse();
      return value;
    }catch(e){if(!this.isCurrent(ticket))throw new StaleResponse();throw e;}
  }
}
export const crmRequests=new CrmRequests();
export function isContextError(e:unknown){return e instanceof ApiError && ['CONTEXT_CHANGED','CONTEXT_REQUIRED'].includes(e.code);}
