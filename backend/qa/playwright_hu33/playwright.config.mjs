import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'hu33.spec.mjs',
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  reporter: [['list'], ['html', { outputFolder: '../03_Evidencias/HU33-HT15/playwright', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'msedge',
    viewport: { width: 1400, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'off',
  },
});
