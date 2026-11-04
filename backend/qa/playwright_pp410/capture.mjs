// Capturas recortadas de los informes HTML de PP-410 (evidencia para el informe PDF).
// Ejecutar desde esta carpeta: node capture.mjs
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve('..', '03_Evidencias', 'PP-410');
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

await capturaPytest('pytest_pp410.html', 'EV-PP410-INF-01_captura-informe-pytest.png', 10);
await capturaPytest('pytest_regresion.html', 'EV-PP410-INF-02_captura-informe-regresion-extracto.png', 10);
await capturaPytest('pytest_regresion_hu47.html', 'EV-PP410-INF-03_captura-informe-regresion-hu47-extracto.png', 10);

await browser.close();
console.log('capturas ok');
