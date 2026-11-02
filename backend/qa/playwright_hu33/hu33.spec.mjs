// QA PP-408 (HU-15-T04) - Exportación asíncrona de HU33: lo que ve el usuario (CA1 y CA5), casos CP-168 en adelante.
// Datos: BD pangea_e2e (seed del proyecto), solo local, sin S3 ni worker: la generación del archivo se prueba con pytest.
import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';

const CLAVE = process.env.QA_CLAVE ?? 'Pangea2026';
const CLIENTE = 'cliente@pangea-dev.com';
const EV = '../03_Evidencias/HU33-HT15/';

async function aplicarRango(page, inicio, fin) {
  await page.getByRole('button', { name: /^Filtros/ }).click();
  await page.getByLabel('Fecha inicio').fill(inicio);
  await page.getByLabel('Fecha fin').fill(fin);
  await page.locator('div:has(> button:text-is("LIMPIAR FILTRO")) > button:text-is("APLICAR")').click();
  if (await page.getByRole('dialog', { name: 'Filtros' }).isVisible()) await page.getByRole('button', { name: 'Cerrar panel' }).click();
}

test.describe.serial('HU33 Exportación desde Consulta de datos', () => {
  let page;
  test.beforeAll(async ({ browser }) => {
    execSync('docker exec pangea-redis-1 redis-cli -n 5 FLUSHDB');
    const ctx = await browser.newContext();
    page = await ctx.newPage();
    await page.goto('/login');
    await page.getByPlaceholder('Ingresa tu correo').fill(CLIENTE);
    await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
    await page.locator('button.submit').click();
    await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
    await page.goto('/consulta-datos');
    await page.getByRole('button', { name: 'Exportar datos CSV / Excel' }).click();
  });
  test.afterAll(async () => { await page.context().close(); });

  test('HU33 el panel informa límite de rango y vigencia de 24 horas', async () => {
    const aviso = page.getByText(/Máximo 31 días y .* registros\. Disponible durante 24 horas/);
    await expect(aviso).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: EV + 'EV-HU33-E2E-01_panel-limites.png' });
  });

  test('HU33 CA1 solicitar exportación responde de inmediato y no bloquea la interfaz', async () => {
    await aplicarRango(page, '2026-10-29T00:00', '2026-10-31T00:00');
    const boton = page.getByRole('button', { name: 'Solicitar exportación' });
    await expect(boton).toBeEnabled();
    const t0 = Date.now();
    await boton.click();
    await expect(page.getByRole('status')).toBeVisible({ timeout: 5000 });
    const ms = Date.now() - t0;
    expect(ms).toBeLessThan(5000);
    // La interfaz sigue usable mientras la exportación se prepara.
    await page.getByLabel('Formato de exportación').selectOption('xlsx');
    await expect(page.getByLabel('Formato de exportación')).toHaveValue('xlsx');
    await expect(page.getByText(/#\d+ · CSV · (Pendiente|En proceso|Fallida)/).first()).toBeVisible();
    console.log(`EVIDENCIA CA1: mensaje de confirmación en ${ms} ms`);
    await page.screenshot({ path: EV + 'EV-HU33-E2E-02_solicitud-en-proceso.png' });
  });

  test('HU33 CA5 un rango mayor al máximo se rechaza con mensaje claro', async () => {
    await aplicarRango(page, '2026-09-01T00:00', '2026-10-31T00:00');
    const antes = await page.locator('ul li', { hasText: /#\d+ ·/ }).count();
    await page.getByRole('button', { name: 'Solicitar exportación' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'El máximo por exportación es de 31 días. Aplica un rango menor.' })).toBeVisible();
    expect(await page.locator('ul li', { hasText: /#\d+ ·/ }).count()).toBe(antes);
    await page.screenshot({ path: EV + 'EV-HU33-E2E-03_rango-excedido.png' });
  });

  test('HU33 CA3 la exportación queda Lista con vigencia de 24 horas y se descarga', async () => {
    await expect(page.locator('li', { hasText: /· Lista/ }).first()).toBeVisible({ timeout: 40000 });
    await expect(page.getByText(/Disponible hasta/).first()).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU33-E2E-04_exportacion-lista.png' });
    await page.route('**/docs**', (r) => r.fulfill({ status: 200, body: 'descarga simulada' }));
    let cuerpo; let estado;
    await page.route(/\/exportaciones\/\d+\/descarga$/, async (route) => {
      const r = await route.fetch();
      estado = r.status(); cuerpo = await r.json();
      await route.fulfill({ response: r, json: cuerpo });
    });
    await page.getByRole('button', { name: 'Descargar' }).first().click();
    await expect.poll(() => estado).toBe(200);
    expect(cuerpo.url).toContain('X-Expires=');
  });
});
