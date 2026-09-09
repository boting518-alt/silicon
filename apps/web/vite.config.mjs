import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const tls = fileURLToPath(new URL('../../.tools/tls/', import.meta.url));
export default defineConfig(({ command }) => {
  if (command === 'serve' && !existsSync(`${tls}localhost.key`)) {
    throw new Error('先在仓库根运行 python infra/dev_tls.py，身份会话要求本地 HTTPS。');
  }
  return {
    plugins: [react(), ...(command === 'serve' && process.env.SILICON_VISUAL_FONT ? [{
      name: 'silicon-visual-harness',
      configureServer(server) {
        const font = readFileSync(process.env.SILICON_VISUAL_FONT);
        server.middlewares.use('/__visual_font', (_req,res) => {res.setHeader('Content-Type','font/collection');res.end(font);});
      },
      transformIndexHtml(html) {
        return html.replace('</head>', `<script>const OriginalDate=Date;window.Date=class extends OriginalDate{constructor(...a){super(...(a.length?a:['2026-09-08T04:00:00.000Z']))}static now(){return new OriginalDate('2026-09-08T04:00:00.000Z').getTime()}};</script><style>@font-face{font-family:SiliconBaseline;src:url('/__visual_font')}html,body,button,input,select,textarea{font-family:SiliconBaseline,sans-serif!important}*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}</style></head>`);
      },
    }] : [])],
    server: { host: 'localhost', port: 5173, strictPort: true,
      https: command === 'serve' ? { key: readFileSync(`${tls}localhost.key`), cert: readFileSync(`${tls}localhost.crt`) } : undefined,
      proxy: { '/api': 'http://127.0.0.1:8000' } },
  };
});
