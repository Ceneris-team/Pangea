// QA HU34 - Personalizar widgets del panel: flujos de UI (CA1-CA5) como Cliente Final.
// Datos: BD pangea_e2e (seed del proyecto + lecturas ficticias de pH y temperatura en la ubicación DEMO), solo local.
import { test, expect } from '@playwright/test';

const CLAVE = 'Pangea2026';
const PANEL = `QA HU34 ${Date.now() % 100000}`;
const U1 = '[DEMO] Río Rímac - Margen Izquierda';
const EV = '../03_Evidencias/HU34/';

const widgets = (page) => page.locator('article', { has: page.getByRole('button', { name: 'Editar', exact: true }) });
const titulos = async (page) => (await widgets(page).locator('p.font-semibold').allTextContents()).map((t) => t.trim());
const drawer = (page) => page.locator('div', { has: page.getByRole('button', { name: /^Guardar widget|^Guardando/ }) }).last();
const verWidgets = async (page) => { await page.getByRole('heading', { name: /^Widgets/ }).evaluate((h) => h.scrollIntoView({ block: 'start' })); await page.waitForTimeout(700); };
const parametroDrawer = (page) => page.locator('select', { has: page.locator('option', { hasText: 'Selecciona un parámetro' }) });

async function anadirWidget(page, tipo, parametro) {
  await page.getByRole('button', { name: '+ Añadir widget' }).click();
  await page.getByLabel('Tipo de widget').selectOption(tipo);
  await page.getByLabel('Ubicación').selectOption({ label: U1 });
  await parametroDrawer(page).selectOption({ label: parametro });
  await page.getByRole('button', { name: 'Guardar widget' }).click();
  await expect(page.getByRole('status')).toContainText('Widget creado correctamente');
}

test.describe.serial('HU34 flujos de UI como Cliente Final', () => {
  let page;
  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await page.goto('/');
    await page.getByPlaceholder('Ingresa tu correo').fill('cliente@pangea-dev.com');
    await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
    await page.locator('button.submit').click();
    await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
    await page.goto('/paneles');
    await page.getByRole('button', { name: 'Crear panel' }).click();
    await page.getByPlaceholder('Resumen de estaciones').fill(PANEL);
    await page.getByRole('button', { name: 'Guardar', exact: true }).click();
    await page.waitForURL(/\/paneles\/\d+/);
  });

  test('Precondición: sin ubicaciones no se ofrece "Añadir widget"', async () => {
    await expect(page.getByText('Este panel todavía no tiene ubicaciones configuradas.')).toBeVisible();
    await expect(page.getByRole('button', { name: '+ Añadir widget' })).toHaveCount(0);
    await page.getByRole('button', { name: '+ Añadir ubicaciones' }).first().click();
    await page.locator('label:has(input[type=checkbox])', { hasText: U1 }).locator('input').check();
    await page.getByRole('button', { name: /^Agregar al panel/ }).click();
    await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
    await expect(page.getByText('Aún no hay widgets.', { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: '+ Añadir widget' })).toBeVisible();
  });

  test('CA1 "Añadir widget" muestra el selector de tipos de widget', async () => {
    await page.getByRole('button', { name: '+ Añadir widget' }).click();
    await expect(page.getByText('Añadir widget', { exact: true }).last()).toBeVisible();
    const opciones = (await page.getByLabel('Tipo de widget').locator('option').allTextContents()).map((t) => t.trim());
    expect(opciones).toEqual(expect.arrayContaining(['Gráfico de línea', 'Gráfico de área', 'Tarjeta de valor actual']));
    test.info().annotations.push({ type: 'OBS', description: `Opciones del selector: ${opciones.join(' | ')}` });
    await page.waitForTimeout(800);
    await page.screenshot({ path: EV + 'EV-HU34-E2E-01_selector-tipo-widget.png' });
  });

  test('CA2 sin parámetro el botón GUARDAR WIDGET está deshabilitado; solo se ofrecen ubicaciones del panel', async () => {
    await expect(page.getByRole('button', { name: 'Guardar widget' })).toBeDisabled();
    const ubicaciones = (await page.getByLabel('Ubicación').locator('option').allTextContents()).map((t) => t.trim());
    expect(ubicaciones).toEqual([U1]);
    await parametroDrawer(page).selectOption({ label: 'ph (pH)' });
    await expect(page.getByRole('button', { name: 'Guardar widget' })).toBeEnabled();
    await page.getByRole('button', { name: 'Cancelar' }).click();
    await expect(widgets(page)).toHaveCount(0);
  });

  test('CA2 guardar agrega línea, área y tarjeta con datos de telemetría', async () => {
    await anadirWidget(page, 'linea', 'ph (pH)');
    await expect(widgets(page)).toHaveCount(1);
    await expect(page.getByRole('img', { name: `Gráfico de ph en ${U1}` })).toBeVisible();
    await anadirWidget(page, 'area', 'temperatura (C°)');
    await expect(page.getByRole('img', { name: `Gráfico de temperatura en ${U1}` })).toBeVisible();
    await anadirWidget(page, 'tarjeta', 'ph (pH)');
    await expect(widgets(page)).toHaveCount(3);
    await expect(widgets(page).nth(2)).toContainText(/7[.,]42/);
    await expect(widgets(page).nth(2)).toContainText('Última lectura');
    expect(await titulos(page)).toEqual(['ph', 'temperatura', 'ph']);
    await verWidgets(page);
    await page.screenshot({ path: EV + 'EV-HU34-E2E-02_widgets-con-telemetria.png' });
  });

  test('CA3 editar un widget y GUARDAR WIDGET muestra "Widget actualizado correctamente"', async () => {
    await widgets(page).nth(0).getByRole('button', { name: 'Editar', exact: true }).click();
    await expect(page.getByText('Editar widget', { exact: true }).last()).toBeVisible();
    await expect(page.getByLabel('Tipo de widget')).toHaveValue('linea');
    await page.getByLabel('Tipo de widget').selectOption('area');
    await parametroDrawer(page).selectOption({ label: 'temperatura (C°)' });
    await page.getByRole('button', { name: 'Guardar widget' }).click();
    await expect(page.getByRole('status')).toContainText('Widget actualizado correctamente');
    expect(await titulos(page)).toEqual(['temperatura', 'temperatura', 'ph']);
    await expect(widgets(page).nth(0).getByRole('img', { name: `Gráfico de temperatura en ${U1}` })).toBeVisible();
    await verWidgets(page);
    await page.screenshot({ path: EV + 'EV-HU34-E2E-03_widget-actualizado.png' });
  });

  test('CA4 cancelar el modal de Eliminar no retira el widget', async () => {
    await widgets(page).nth(1).getByRole('button', { name: 'Eliminar' }).click();
    await expect(page.getByText('Eliminar widget')).toBeVisible();
    await expect(page.getByText('Los datos de telemetría y la ubicación permanecerán disponibles.')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU34-E2E-04_modal-eliminar.png' });
    await page.getByRole('button', { name: 'Cancelar' }).last().click();
    await expect(widgets(page)).toHaveCount(3);
  });

  test('CA4 eliminar y confirmar retira el widget y muestra "Widget eliminado correctamente"', async () => {
    await widgets(page).nth(1).getByRole('button', { name: 'Eliminar' }).click();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByRole('status')).toContainText('Widget eliminado correctamente');
    await expect(widgets(page)).toHaveCount(2);
    // La ubicación sigue en el panel y la telemetría sigue disponible para los otros widgets.
    await expect(page.getByRole('button', { name: U1, exact: true })).toBeVisible();
    await expect(widgets(page).nth(1)).toContainText(/7[.,]42/);
    await verWidgets(page);
    await page.screenshot({ path: EV + 'EV-HU34-E2E-05_widget-eliminado.png' });
  });

  test('CA5 arrastrar un widget guarda la nueva disposición y se mantiene al recargar', async () => {
    await anadirWidget(page, 'linea', 'ph (pH)');
    await expect(widgets(page).locator('svg[role=img]')).toHaveCount(2);
    expect(await titulos(page)).toEqual(['temperatura', 'ph', 'ph']);
    const tipos = async () => widgets(page).evaluateAll((els) => els.map((e) => (e.querySelector('svg[role=img]') ? 'grafico' : 'tarjeta')));
    expect(await tipos()).toEqual(['grafico', 'tarjeta', 'grafico']);
    const orden = page.waitForResponse((r) => r.url().endsWith('/widgets/orden') && r.request().method() === 'PUT');
    await widgets(page).nth(2).dragTo(widgets(page).nth(0));
    expect((await orden).status()).toBe(200);
    expect(await titulos(page)).toEqual(['ph', 'temperatura', 'ph']);
    expect(await tipos()).toEqual(['grafico', 'grafico', 'tarjeta']);
    await page.reload();
    await expect(widgets(page)).toHaveCount(3);
    await expect(widgets(page).locator('svg[role=img]')).toHaveCount(2);
    expect(await titulos(page)).toEqual(['ph', 'temperatura', 'ph']);
    expect(await tipos()).toEqual(['grafico', 'grafico', 'tarjeta']);
    await verWidgets(page);
    await page.screenshot({ path: EV + 'EV-HU34-E2E-06_orden-tras-recargar.png' });
  });
});
