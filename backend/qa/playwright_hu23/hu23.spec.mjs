// QA HU23 - Listar paneles: flujos de UI (CA1-CA3 y detalles) como Cliente Final.
// Datos: BD pangea_e2e local. Cuentas de prueba: cliente@pangea-dev.com (seed), qa.sinpaneles@ y qa.otro@ (creadas solo para esta prueba).
import { test, expect } from '@playwright/test';

const CLAVE = 'Pangea2026';
const EV = '../03_Evidencias/HU23/';
const NUEVO = `QA HU23 ${Date.now() % 100000}`;
const U1 = '[DEMO] Río Rímac - Margen Izquierda';

async function entrar(browser, correo) {
  const page = await (await browser.newContext()).newPage();
  await page.goto('/');
  await page.getByPlaceholder('Ingresa tu correo').fill(correo);
  await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
  await page.locator('button.submit').click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  await page.goto('/paneles');
  await expect(page.getByRole('heading', { name: 'Tableros Personalizables' })).toBeVisible();
  return page;
}
const filas = (page) => page.locator('tbody tr').filter({ has: page.getByRole('link', { name: 'Abrir' }) });
const nombresVisibles = async (page) => (await filas(page).locator('td:first-child a').allTextContents()).map((t) => t.trim());
const fechaNum = (t) => { const [d, m, a] = t.trim().split('/').map(Number); return a * 10000 + m * 100 + d; };

test.describe.serial('HU23 listar paneles como Cliente Final', () => {
  let page;
  test.beforeAll(async ({ browser }) => { page = await entrar(browser, 'cliente@pangea-dev.com'); });

  test('CA1 el listado muestra nombre, fecha de creación y acciones de cada panel', async () => {
    await expect(page.getByRole('columnheader', { name: 'Nombre' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Fecha de creación' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Acciones' })).toBeVisible();
    await expect(filas(page).first()).toBeVisible();
    expect(await filas(page).count()).toBeGreaterThanOrEqual(10);
    const primera = filas(page).first();
    await expect(primera.locator('td:nth-child(3)')).toHaveText(/^\d{2}\/\d{2}\/\d{4}$/);
    for (const accion of ['Abrir', 'Duplicar', 'Editar', 'Eliminar']) await expect(primera.getByRole(accion === 'Abrir' ? 'link' : 'button', { name: accion })).toBeVisible();
    await page.waitForTimeout(600);
    await page.screenshot({ path: EV + 'EV-HU23-E2E-01_listado.png' });
  });

  test('Detalle: orden por fecha de creación descendente por defecto', async () => {
    const fechas = (await filas(page).locator('td:nth-child(3)').allTextContents()).map(fechaNum);
    expect(fechas.length).toBeGreaterThan(1);
    for (let i = 1; i < fechas.length; i++) expect(fechas[i - 1]).toBeGreaterThanOrEqual(fechas[i]);
    // Dentro del mismo día, el panel creado después va primero.
    const nombres = await nombresVisibles(page);
    expect(nombres.indexOf('QA HU34 34963')).toBeLessThan(nombres.indexOf('QA HU34 1107'));
    expect(nombres.indexOf('QA HU34 1107')).toBeLessThan(nombres.indexOf('QA HU26 41510'));
  });

  test('Detalle: solo se ven los paneles propios (no el de otro usuario)', async () => {
    expect(await nombresVisibles(page)).not.toContain('QA Panel ajeno');
    await expect(page.getByText('QA Panel ajeno')).toHaveCount(0);
  });

  test('CA3 búsqueda por fragmento filtra el listado, sin distinguir mayúsculas', async () => {
    const buscar = page.getByPlaceholder('Buscar por nombre de panel...');
    await buscar.fill('hu26');
    await expect.poll(async () => (await nombresVisibles(page)).length).toBe(5);
    expect((await nombresVisibles(page)).every((n) => n.includes('HU26'))).toBe(true);
    await page.waitForTimeout(500);
    await page.screenshot({ path: EV + 'EV-HU23-E2E-02_busqueda.png' });
    await buscar.fill('QA HU34 1107');
    await expect.poll(async () => nombresVisibles(page)).toEqual(['QA HU34 1107']);
  });

  test('CA3 búsqueda sin coincidencias muestra el aviso de sin resultados', async () => {
    await page.getByPlaceholder('Buscar por nombre de panel...').fill('zzz-no-existe');
    await expect(page.getByText('No se encontraron paneles con ese criterio.')).toBeVisible();
    await expect(page.getByText('Aún no tienes paneles creados')).toHaveCount(0);
    await page.waitForTimeout(400);
    await page.screenshot({ path: EV + 'EV-HU23-E2E-03_busqueda-sin-resultados.png' });
  });

  test('CA3 borrar la búsqueda restituye el listado completo', async () => {
    await page.getByPlaceholder('Buscar por nombre de panel...').fill('');
    await expect.poll(async () => (await nombresVisibles(page)).length).toBeGreaterThanOrEqual(10);
  });

  test('CA2 panel con ubicación y widget: sale primero en el listado y su nombre lo abre con su contenido', async () => {
    await page.getByRole('button', { name: 'Crear panel' }).first().click();
    await page.getByPlaceholder('Resumen de estaciones').fill(NUEVO);
    await page.getByRole('button', { name: 'Guardar', exact: true }).click();
    await page.waitForURL(/\/paneles\/\d+/);
    await page.getByRole('button', { name: '+ Añadir ubicaciones' }).first().click();
    await page.locator('label:has(input[type=checkbox])', { hasText: U1 }).locator('input').check();
    await page.getByRole('button', { name: /^Agregar al panel/ }).click();
    await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
    await page.getByRole('button', { name: '+ Añadir widget' }).click();
    await page.getByLabel('Tipo de widget').selectOption('tarjeta');
    const parametro = page.locator('select', { has: page.locator('option', { hasText: 'Selecciona un parámetro' }) });
    await expect.poll(async () => (await parametro.locator('option').count())).toBeGreaterThan(1);
    await parametro.selectOption({ index: 1 });
    await page.getByRole('button', { name: 'Guardar widget' }).click();
    await expect(page.getByRole('status')).toContainText('Widget creado correctamente');

    await page.goto('/paneles');
    await expect(filas(page).first().locator('td:first-child a')).toHaveText(NUEVO);
    await expect(filas(page).first().locator('td:nth-child(2)')).toContainText(U1);
    await page.waitForTimeout(500);
    await page.screenshot({ path: EV + 'EV-HU23-E2E-04_panel-nuevo-primero.png' });

    await filas(page).first().locator('td:first-child a').click();
    await page.waitForURL(/\/paneles\/\d+/);
    await expect(page.getByRole('heading', { name: NUEVO })).toBeVisible();
    await expect(page.getByText(U1).locator('visible=true').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: /^Widgets \(1\)/ })).toBeVisible();
    await page.waitForTimeout(900);
    await page.screenshot({ path: EV + 'EV-HU23-E2E-05_panel-abierto.png' });
  });

  test('CA2 el botón Abrir lleva al mismo panel que el nombre', async () => {
    await page.goto('/paneles');
    const id = await filas(page).first().getByRole('link', { name: 'Abrir' }).getAttribute('href');
    const idNombre = await filas(page).first().locator('td:first-child a').getAttribute('href');
    expect(id).toBe(idNombre);
  });

  test('Limpieza: elimina el panel creado en la prueba', async () => {
    await page.goto('/paneles');
    await filas(page).first().getByRole('button', { name: 'Eliminar' }).click();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByText(NUEVO)).toHaveCount(0, { timeout: 8000 });
  });
});

test.describe('HU23 usuario sin paneles', () => {
  test('Detalle: muestra «Aún no tienes paneles creados» y «Crear panel» visible y habilitado', async ({ browser }) => {
    const p = await entrar(browser, 'qa.sinpaneles@pangea-dev.com');
    await expect(p.getByText('Aún no tienes paneles creados')).toBeVisible();
    const botones = p.getByRole('button', { name: 'Crear panel' });
    expect(await botones.count()).toBeGreaterThanOrEqual(1);
    for (let i = 0; i < await botones.count(); i++) { await expect(botones.nth(i)).toBeVisible(); await expect(botones.nth(i)).toBeEnabled(); }
    await expect(p.getByText('QA Panel ajeno')).toHaveCount(0);
    await p.waitForTimeout(500);
    await p.screenshot({ path: EV + 'EV-HU23-E2E-06_sin-paneles.png' });
    await botones.last().click();
    await expect(p.getByPlaceholder('Resumen de estaciones')).toBeVisible();
  });
});

test.describe('HU23 otro usuario', () => {
  test('Detalle: el otro usuario ve solo su panel y no los del Cliente Final', async ({ browser }) => {
    const p = await entrar(browser, 'qa.otro@pangea-dev.com');
    await expect.poll(async () => nombresVisibles(p)).toEqual(['QA Panel ajeno']);
  });
});

test.describe('HU23 búsqueda con caracteres especiales', () => {
  test('CA3 el carácter % no debe actuar como comodín', async ({ browser }) => {
    const p = await entrar(browser, 'cliente@pangea-dev.com');
    await expect.poll(async () => (await nombresVisibles(p)).length).toBeGreaterThanOrEqual(10);
    await p.getByPlaceholder('Buscar por nombre de panel...').fill('%');
    await p.waitForTimeout(1200); // debounce de 400 ms + respuesta de la API
    await p.screenshot({ path: EV + 'EV-HU23-E2E-07_busqueda-porcentaje.png' });
    expect(await filas(p).count()).toBe(0);
  });
});
