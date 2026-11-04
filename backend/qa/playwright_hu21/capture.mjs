// Capturas recortadas de los informes HTML de HU-21. Ejecutar con: node capture.mjs
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HU21');
const FILAS = 10;
const browser = await chromium.launch({ channel: 'msedge' });

async function pytestHtml(archivo, salida) {
  const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, archivo)).href);
  await page.waitForSelector('#results-table tbody');
  await page.addStyleTag({ content: '#environment, #environment-header { display: none !important; } .extras-row { display: none !important; }' });
  await page.evaluate(() => { for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none'; });
  const { bottom, right } = await page.evaluate((n) => {
    const rows = document.querySelectorAll('#results-table tbody.results-table-row');
    const last = rows[Math.min(n, rows.length) - 1].getBoundingClientRect();
    return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
  }, FILAS);
  await page.screenshot({ path: path.join(dir, salida), fullPage: true, clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 } });
}

await pytestHtml('pytest_hu21.html', 'EV-HU21-INF-01_captura-informe-pytest.png');
await pytestHtml('pytest_regresion.html', 'EV-HU21-INF-03_captura-regresion-extracto.png');
await pytestHtml('pytest_regresion_sin_variable.html', 'EV-HU21-INF-04_captura-regresion-sin-variable-extracto.png');

const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2 });
await page.goto(pathToFileURL(path.join(dir, 'playwright', 'index.html')).href);
await page.waitForSelector('.test-file-test');
await page.waitForTimeout(500);
const bottom = await page.evaluate((n) => { const i = document.querySelectorAll('.test-file-test'); return i[Math.min(n, i.length) - 1].getBoundingClientRect().bottom + window.scrollY; }, FILAS);
await page.screenshot({ path: path.join(dir, 'EV-HU21-INF-02_captura-informe-playwright.png'), fullPage: true, clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 10 } });
await browser.close();
