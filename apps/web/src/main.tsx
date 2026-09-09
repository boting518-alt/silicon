import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { useEffect, useState } from 'react';
import type { components } from '../../../packages/api-client/schema';
import '../../../packages/ui/tokens.css';
import './style.css';

type Session = components['schemas']['SessionInfo'];
type State = 'idle' | 'loading' | 'ready' | 'error';
function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [identityMessage, setIdentityMessage] = useState('正在检查登录状态…');
  const [busy, setBusy] = useState(false);
  async function loadSession() {
    try {
      const response = await fetch('/api/v1/session', { signal: AbortSignal.timeout(6000) });
      if (response.status === 401) { setSession(null); setIdentityMessage('请先登录。'); return; }
      if (!response.ok) throw new Error();
      setSession(await response.json()); setIdentityMessage('');
    } catch { setIdentityMessage('暂时无法读取登录状态，请检查服务后重试。'); }
  }
  useEffect(() => { void loadSession(); }, []);
  async function identityAction(path: string, body?: object) {
    setBusy(true);
    try {
      const csrf = document.cookie.split('; ').find(value => value.startsWith('__Host-silicon-csrf='))?.split('=')[1] ?? '';
      const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(6000) });
      if (!response.ok) {
        setIdentityMessage(response.status === 401 ? '登录已失效，请重新登录。' : '操作未完成，请刷新登录状态或检查企业权限。');
        if (response.status === 401) setSession(null);
        return;
      }
      const result = await response.json();
      if (result.logout_url) { window.location.assign(result.logout_url); return; }
      await loadSession();
    } catch { setIdentityMessage('服务暂不可用，操作未确认完成。'); }
    finally { setBusy(false); }
  }
  const [state, setState] = useState<State>('idle');
  async function check() {
    setState('loading');
    try {
      const response = await fetch('/api/v1/ready', { signal: AbortSignal.timeout(6000) });
      if (!response.ok) throw new Error('unavailable');
      const data: components['schemas']['Status'] = await response.json();
      if (data.status !== 'ready') throw new Error('invalid response');
      setState('ready');
    } catch { setState('error'); }
  }
  return <div className="shell">
    <aside><a className="brand" href="/" aria-label="硅屿首页"><span className="logo">硅</span>硅屿 <small>SILICON</small></a><div className="current">业务工作空间</div><p className="sidebar-note">设备销售与服务</p></aside>
    <main><header><span className="eyebrow">WORKSPACE</span><span className="badge">建设中</span></header>
      <h1>硅屿业务工作空间</h1><p className="intro">从配置报价，到设备交付与服务。</p>
      <section aria-labelledby="identity"><h2 id="identity">身份与企业</h2>
        {session ? <><p>{session.user.name}</p><label>当前企业 <select aria-label="当前企业" disabled={busy}
          value={session.tenant_id ?? ''} onChange={event => void identityAction('/api/v1/session/tenant', { tenant_id: event.target.value })}>
          <option value="" disabled>请选择企业</option>{session.memberships.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>{session.memberships.length === 0 && <p>尚未加入企业，请联系管理员。</p>}
        <button disabled={busy} onClick={() => void identityAction('/api/v1/auth/logout')}>退出登录</button></> : <a href="/api/v1/auth/login">使用企业身份登录</a>}
        <button disabled={busy} onClick={() => void loadSession()}>刷新登录状态</button>
        <p role="status" aria-live="polite">{identityMessage}</p>
      </section>
      <section aria-labelledby="welcome"><div className="eyebrow">SILICON</div><h2 id="welcome">工作空间正在准备中</h2><p>客户、报价与设备功能将在后续开放。</p>
        <button onClick={check} disabled={state === 'loading'}>{state === 'loading' ? '正在检查…' : '检查连接'}</button>
        <p role="status" aria-live="polite" className={state === 'error' ? 'error' : ''}>{state === 'idle' ? '尚未检查服务连接。' : state === 'loading' ? '正在连接服务。' : state === 'ready' ? '服务连接正常。' : '服务暂不可用，请稍后重试。'}</p>
      </section>
    </main></div>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
