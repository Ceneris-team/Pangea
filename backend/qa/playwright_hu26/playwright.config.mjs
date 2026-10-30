import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'hu26.spec.mjs',
  workers: 1,
  fullyParallel: false,
  timeout: 45000,
  reporter: [['list'], ['html', { outputFolder: '../03_Evidencias/HU26/playwright', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'msedge',
    viewport: { width: 1400, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'off',
  },
});
