import { defineConfig } from 'vite';
import path from 'node:path';

export default defineConfig({
  define: { JARVIS_DEFAULT_AGENT_DIR: JSON.stringify(path.resolve(__dirname, '..')) },
  build: { rollupOptions: { external: ['electron', 'dotenv', 'livekit-server-sdk', /^node:/] } },
});
