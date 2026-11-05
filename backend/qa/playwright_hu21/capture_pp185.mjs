// Capturas recortadas de los informes HTML de la ronda 2 de HU-21. Ejecutar con: node capture_pp185.mjs
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HU21', 'reprueba_pp185');
const browser = await chromium.launch({ channel: 'msedge' });
{
  const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, 'pytest_pp185_reprueba.html')).href);
  await page.waitForSelector('#results-table tbody');
  await page.addStyleTag({ content: '#environment, #environment-header { display: none !important; } .extras-row { display: none !important; }' });
  await page.evaluate(() => { for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none'; });
  const { bottom, right } = await page.evaluate(() => {
    const rows = document.querySelectorAll('#results-table tbody.results-table-row');
    return { bottom: rows[rows.length - 1].getBoundingClientRect().bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
  });
  await page.screenshot({ path: path.join(dir, 'EV-HU21-R2-INF-01_captura-pytest.png'), fullPage: true, clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 } });
}
{
  const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, 'playwright', 'index.html')).href);
  await page.waitForSelector('.test-file-test');
  await page.waitForTimeout(500);
  const bottom = await page.evaluate(() => { const i = document.querySelectorAll('.test-file-test'); return i[i.length - 1].getBoundingClientRect().bottom + window.scrollY; });
  await page.screenshot({ path: path.join(dir, 'EV-HU21-R2-INF-02_captura-playwright.png'), fullPage: true, clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 10 } });
}
await browser.close();
