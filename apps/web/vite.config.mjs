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
    plugins: [react()],
    server: { host: 'localhost', port: 5173, strictPort: true,
      https: command === 'serve' ? { key: readFileSync(`${tls}localhost.key`), cert: readFileSync(`${tls}localhost.crt`) } : undefined,
      proxy: { '/api': 'http://127.0.0.1:8000' } },
  };
});
