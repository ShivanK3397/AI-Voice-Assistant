import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig({
  resolve: { alias: { 'livekit-client': path.resolve(__dirname, 'tests/fake-room.ts') } },
  plugins: [react(), {
    name: 'test-refresh-csp',
    transformIndexHtml(html: string) { return html.replace("script-src 'self';", "script-src 'self' 'unsafe-inline';"); },
  }],
});
