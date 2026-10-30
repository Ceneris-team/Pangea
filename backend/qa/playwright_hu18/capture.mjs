// Capturas recortadas de los informes HTML de HU18 (evidencia para el informe PDF).
// Ejecutar desde esta carpeta: node capture.mjs
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'HU18');
const browser = await chromium.launch({ channel: 'msedge' });

// pytest-html: título, fecha, resumen y primeras `filas` resultados (sin tabla de entorno).
async function capturaPytest(html, png, filas) {
  const page = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(path.join(dir, html)).href);
  await page.waitForSelector('#results-table tbody');
  await page.addStyleTag({ content: '#environment, #environment-header, .extras-row { display: none !important; }' });
  await page.evaluate(() => {
    for (const p of document.querySelectorAll('p')) if (p.textContent.startsWith('(Un)check')) p.style.display = 'none';
  });
  const { bottom, right } = await page.evaluate((n) => {
    const rows = document.querySelectorAll('#results-table tbody.results-table-row');
    const last = rows[Math.min(n, rows.length) - 1].getBoundingClientRect();
    return { bottom: last.bottom + window.scrollY, right: document.querySelector('#results-table').getBoundingClientRect().right };
  }, filas);
  await page.screenshot({
    path: path.join(dir, png),
    fullPage: true,
    clip: { x: 0, y: 0, width: Math.ceil(right) + 8, height: Math.ceil(bottom) + 1 },
  });
  await page.close();
}

await capturaPytest('pytest_hu18.html', 'EV-HU18-INF-05_captura-informe-pytest.png', 10);
await capturaPytest('pytest_hu18_ftp_real.html', 'EV-HU18-INF-06_captura-informe-ftp-real.png', 10);
await capturaPytest('pytest_regresion.html', 'EV-HU18-INF-08_captura-informe-regresion-extracto.png', 10);

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
  await page.screenshot({
    path: path.join(dir, 'EV-HU18-INF-07_captura-informe-playwright.png'),
    fullPage: true,
    clip: { x: 0, y: 0, width: 1000, height: Math.ceil(bottom) + 10 },
  });
  await page.close();
}

await browser.close();
console.log('capturas ok');
