import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import type { components } from '../../../packages/api-client/schema';
import '../../../packages/ui/tokens.css';
import './style.css';

type State = 'idle' | 'loading' | 'ready' | 'error';
function App() {
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
      <section aria-labelledby="welcome"><div className="eyebrow">SILICON</div><h2 id="welcome">工作空间正在准备中</h2><p>客户、报价与设备功能将在后续开放。</p>
        <button onClick={check} disabled={state === 'loading'}>{state === 'loading' ? '正在检查…' : '检查连接'}</button>
        <p role="status" aria-live="polite" className={state === 'error' ? 'error' : ''}>{state === 'idle' ? '尚未检查服务连接。' : state === 'loading' ? '正在连接服务。' : state === 'ready' ? '服务连接正常。' : '服务暂不可用，请稍后重试。'}</p>
      </section>
    </main></div>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
