import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: '**/*.e2e.spec.ts', workers: 1, timeout: 30000,
  webServer: { command: 'npx vite --config vite.e2e.config.ts --host 127.0.0.1 --port 5178 --strictPort', url: 'http://127.0.0.1:5178', reuseExistingServer: false },
});
