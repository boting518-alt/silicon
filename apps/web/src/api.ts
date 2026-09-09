import type { components } from '../../../packages/api-client/schema';
export type Session = components['schemas']['SessionInfo'];
export type Customer = components['schemas']['CustomerDetail'];
export type CustomerInput = components['schemas']['CustomerInput'];
export type CustomerPage = components['schemas']['CustomerPage'];
export type Member = components['schemas']['Member'];

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
const messages: Record<string,string> = {
  UNAUTHENTICATED:'登录已失效，请重新登录。', FORBIDDEN:'你没有执行此操作的权限。',
  TENANT_REQUIRED:'请先选择企业。', CSRF_REJECTED:'页面验证已失效，请刷新登录状态后重试。',
  NOT_FOUND:'客户不存在或你无权查看。', VERSION_CONFLICT:'此客户已被其他人修改。请重新载入最新版本，再合并你的修改。',
  CUSTOMER_NUMBER_EXISTS:'该客户编号已存在，请使用其他编号。', IDEMPOTENCY_CONFLICT:'本次提交内容已变化，请重新打开编辑。',
  INVALID_RELATIONSHIP:'联系人或项目关系无效，请检查关联内容。', INVALID_RESPONSIBILITY:'所选内部负责人已不属于当前企业。',
};
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== 'GET') {
    headers.set('Content-Type','application/json');
    headers.set('X-CSRF-Token',document.cookie.split('; ').find(x=>x.startsWith('__Host-silicon-csrf='))?.split('=')[1] ?? '');
  }
  const response=await fetch('/api/v1'+path,{...init,headers,signal:init.signal ?? AbortSignal.timeout(10000)});
  const data=await response.json();
  if (!response.ok) throw new ApiError(response.status,data.code ?? 'INVALID_INPUT',messages[data.code] ??
    (response.status===422 ? '输入格式不正确，请检查必填项、邮箱和关联关系。' : '服务暂不可用，操作尚未确认完成。'));
  return data as T;
}
export function errorMessage(error:unknown):string { return error instanceof ApiError ? error.message : '网络暂不可用，请稍后重试；未确认保存成功。'; }
