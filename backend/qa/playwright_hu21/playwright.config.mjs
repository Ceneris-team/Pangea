import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'hu21.spec.mjs',
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  reporter: [['list'], ['html', { outputFolder: '../03_Evidencias/HU21/playwright', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5199',
    channel: 'msedge',
    viewport: { width: 1400, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'off',
  },
});
