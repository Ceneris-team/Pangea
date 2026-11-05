import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'retest_pp185.spec.mjs', workers: 1,
  timeout: 120000,
  outputDir: '../03_Evidencias/HU21/reprueba_pp185/test-results',
  reporter: [['list'], ['html', { outputFolder: '../03_Evidencias/HU21/reprueba_pp185/playwright', open: 'never' }]],
  use: { baseURL: 'http://localhost:5200', channel: 'msedge', viewport: { width: 1400, height: 900 }, screenshot: 'only-on-failure' },
});
