import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'hu18.spec.mjs',
  workers: 1,
  fullyParallel: false,
  timeout: 45000,
  reporter: [['list'], ['html', { outputFolder: '../03_Evidencias/HU18/playwright', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'msedge',
    screenshot: 'only-on-failure',
    trace: 'off',
  },
});
