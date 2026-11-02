// Captura del informe de Playwright de DEF-06 (error visible), sin parche.
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const dir = path.resolve('..', '03_Evidencias', 'HU28');
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2 });
await page.goto(pathToFileURL(path.join(dir, 'playwright_def01', 'index.html')).href);
await page.waitForSelector('.test-file-test');
await page.locator('.test-file-test').first().locator('a').first().click();
await page.waitForSelector('.test-error-container');
await page.waitForTimeout(600);
const bottom = await page.evaluate(() => {
  const e = document.querySelector('.test-error-container').getBoundingClientRect();
  return e.bottom + window.scrollY;
});
await page.screenshot({ path: path.join(dir, 'EV-HU28-INF-04_captura-informe-playwright-def01.png'), fullPage: true, clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 20 } });
await browser.close();
console.log('ok');
