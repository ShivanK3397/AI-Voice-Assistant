import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ command }) => ({
  plugins: [react(), ...(command === 'serve' ? [{
    name: 'development-refresh-csp',
    transformIndexHtml(html: string) { return html.replace("script-src 'self';", "script-src 'self' 'unsafe-inline';"); },
  }] : [])],
}));
