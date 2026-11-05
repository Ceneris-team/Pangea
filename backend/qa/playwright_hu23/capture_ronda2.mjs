// Captura recortada del informe pytest de la ronda 2 de HU23 (evidencia para el informe PDF).
// Ejecutar desde esta carpeta: node capture_ronda2.mjs
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HU23');
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
await page.goto(pathToFileURL(path.join(dir, 'pytest_hu23_reprueba.html')).href);
await page.waitForSelector('#results-table tbody');
await page.addStyleTag({ content: '#environment, #environment-header, .extras-row { display: none !important; }' });
await page.evaluate(() => {
  for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none';
});
const { bottom, right } = await page.evaluate(() => {
  const rows = document.querySelectorAll('#results-table tbody.results-table-row');
  const last = rows[Math.min(10, rows.length) - 1].getBoundingClientRect();
  return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
});
await page.screenshot({
  path: path.join(dir, 'EV-HU23-R2-04_captura-informe-pytest-reprueba.png'),
  fullPage: true,
  clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 },
});
await browser.close();
console.log('captura ok');
