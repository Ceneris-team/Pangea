import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const dir = path.resolve('..', '03_Evidencias', 'HT-06');
const FILAS = 22;
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
await page.goto(pathToFileURL(path.join(dir, 'pytest_ht06_local.html')).href);
await page.waitForSelector('#results-table tbody');
await page.addStyleTag({ content: '#environment, #environment-header, .extras-row { display: none !important; }' });
await page.evaluate(() => { for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none'; });
const { bottom, right } = await page.evaluate((n) => {
  const rows = document.querySelectorAll('#results-table tbody.results-table-row');
  const last = rows[Math.min(n, rows.length) - 1].getBoundingClientRect();
  return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
}, FILAS);
await page.screenshot({ path: path.join(dir, 'EV-HT-06-INF-02_captura-informe-pytest.png'), fullPage: true,
  clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 } });
await browser.close();
console.log('captura ok');
