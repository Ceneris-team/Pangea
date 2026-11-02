// Capturas recortadas de los informes HTML de HU33 (PP-408) para el registro de evidencias y el informe PDF.
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HU33-HT15');
const FILAS = 10;
const browser = await chromium.launch({ channel: 'msedge' });

// pytest-html: título, fecha, resumen y primeras filas (sin tabla de entorno).
async function pytest(html, png, soloFallidas, filas = FILAS) {
  const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, html)).href);
  await page.waitForSelector('#results-table tbody');
  await page.addStyleTag({ content: '#environment, #environment-header { display: none !important; }' });
  await page.evaluate(() => { for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none'; });
  if (soloFallidas) {
    await page.evaluate(() => { for (const c of document.querySelectorAll('input.filter[data-test-result="passed"]')) if (c.checked) c.click(); });
    await page.waitForTimeout(300);
  }
  await page.getByText('Hide all details').click();
  await page.waitForTimeout(300);
  const { bottom, right } = await page.evaluate((n) => {
    const rows = [...document.querySelectorAll('#results-table tbody.results-table-row')].filter((r) => r.offsetParent !== null);
    const last = rows[Math.min(n, rows.length) - 1].getBoundingClientRect();
    return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
  }, filas);
  await page.screenshot({ path: path.join(dir, png), fullPage: true, clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 } });
  await page.close();
}

await pytest('pytest_exportaciones.html', 'EV-HU33-INF-01_captura-pytest-exportaciones-extracto.png', false, 10);
await pytest('pytest_criterios_hu15.html', 'EV-HU33-INF-12_captura-pytest-criterios-ronda2.png', false, 8);
await pytest('pytest_benchmark_mes.html', 'EV-HU33-INF-02_captura-benchmark-mes-completo.png', false, 2);
await pytest('pytest_regresion.html', 'EV-HU33-INF-03_captura-regresion-extracto.png', false, 8);
{
  const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, 'playwright', 'index.html')).href);
  await page.waitForSelector('.test-file-test');
  await page.waitForTimeout(500);
  const bottom = await page.evaluate(() => { const i = document.querySelectorAll('.test-file-test'); return i[i.length - 1].getBoundingClientRect().bottom + window.scrollY; });
  await page.screenshot({ path: path.join(dir, 'EV-HU33-INF-04_captura-informe-playwright.png'), fullPage: true, clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 10 } });
}
await browser.close();
