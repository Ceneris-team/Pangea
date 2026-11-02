// Capturas recortadas de los informes HTML de HT-30.2 (PP-402) para el registro de evidencias y el informe PDF.
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HT-30.2');
const FILAS = 10;
const browser = await chromium.launch({ channel: 'msedge' });

// pytest-html: título, fecha, resumen y primeras FILAS (sin tabla de entorno). Con «solo fallidas» muestra el extracto de los fallos.
async function pytest(html, png, soloFallidas) {
  const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, html)).href);
  await page.waitForSelector('#results-table tbody');
  await page.addStyleTag({ content: '#environment, #environment-header { display: none !important; }' });
  await page.evaluate(() => { for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none'; });
  if (soloFallidas) {
    await page.evaluate(() => { for (const c of document.querySelectorAll('input.filter[data-test-result="passed"]')) if (c.checked) c.click(); });
    await page.waitForTimeout(300);
  }
  await page.getByText('Hide all details').click(); // solo las filas, sin el traceback de cada fallo
  await page.waitForTimeout(300);
  const { bottom, right } = await page.evaluate((n) => {
    const rows = [...document.querySelectorAll('#results-table tbody.results-table-row')].filter((r) => r.offsetParent !== null);
    const last = rows[Math.min(n, rows.length) - 1].getBoundingClientRect();
    return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
  }, FILAS);
  await page.screenshot({ path: path.join(dir, png), fullPage: true, clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 } });
  await page.close();
}

await pytest('pytest_regresion.html', 'EV-HT302-INF-04_captura-regresion-fallidas-extracto.png', true);
await pytest('pytest_regresion_sin_suscripcion.html', 'EV-HT302-INF-05_captura-regresion-sin-suscripcion-extracto.png', false);
// PP-403: reprueba de DEF-02 (historial de git) y DEF-04 (sondeo FTP de HU-18); primero las 2 fallidas de DEF-02.
await pytest('pytest_reverificacion.html', 'EV-HT302-INF-09_captura-reverificacion-extracto.png', false);

// Playwright: cabecera con contadores y lista completa de pruebas.
{
  const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, 'playwright', 'index.html')).href);
  await page.waitForSelector('.test-file-test');
  await page.waitForTimeout(500);
  const bottom = await page.evaluate(() => {
    const i = document.querySelectorAll('.test-file-test');
    return i[i.length - 1].getBoundingClientRect().bottom + window.scrollY;
  });
  await page.screenshot({ path: path.join(dir, 'EV-HT302-INF-06_captura-informe-playwright.png'), fullPage: true,
    clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 10 } });
}
await browser.close();
