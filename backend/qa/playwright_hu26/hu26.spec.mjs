// QA HU26 - Añadir ubicaciones al panel: flujos de UI (CA1-CA4) como Cliente Final.
// Datos: BD pangea_e2e (seed_usuarios_prueba + seed_dispositivos_demo + suscripción con "tableros"), solo local.
import { test, expect } from '@playwright/test';

const CLAVE = 'Pangea2026';
const PANEL = `QA HU26 ${Date.now() % 100000}`;
const U1 = '[DEMO] Río Rímac - Margen Izquierda';
const U2 = '[DEMO] Planta de Tratamiento';
const U3 = '[QA] Estación NO asignada';
const EV = '../03_Evidencias/HU26/';

const abrirSelector = (page) => page.getByRole('button', { name: '+ Añadir ubicaciones' }).first().click();
const agregar = (page) => page.getByRole('button', { name: /^Agregar al panel|^Guardando/ });
const tarjeta = (page, nombre) => page.locator('article', { has: page.getByRole('button', { name: nombre, exact: true }) });

test.describe.serial('HU26 flujos de UI como Cliente Final', () => {
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

  test('CP-E2E-01 panel nuevo sin ubicaciones ofrece "Añadir ubicaciones"', async () => {
    await expect(page.getByText('Este panel todavía no tiene ubicaciones configuradas.')).toBeVisible();
    await expect(page.getByRole('button', { name: '+ Añadir ubicaciones' })).toBeVisible();
  });

  test('CA1 el selector lista las ubicaciones disponibles de la cuenta', async () => {
    await abrirSelector(page);
    await expect(page.getByText('Selecciona una o más ubicaciones asignadas a tu cuenta.')).toBeVisible();
    await expect(page.locator('label:has(input[type=checkbox])', { hasText: U1 })).toBeVisible();
    await expect(page.locator('label:has(input[type=checkbox])', { hasText: U2 })).toBeVisible();
    await expect(page.locator('label:has(input[type=checkbox])', { hasText: U3 })).toHaveCount(0);
    await page.screenshot({ path: EV + 'EV-HU26-E2E-01_selector-ubicaciones.png' });
  });

  test('CA2 sin selección el botón AGREGAR AL PANEL está deshabilitado', async () => {
    await expect(agregar(page)).toBeDisabled();
    await page.locator('label:has(input[type=checkbox])', { hasText: U1 }).locator('input').check();
    await expect(agregar(page)).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Agregar al panel (1)' })).toBeVisible();
  });

  test('CA2/CA3 agregar muestra el mensaje y la tarjeta con nombre y últimos valores', async () => {
    await agregar(page).click();
    await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
    const t = tarjeta(page, U1);
    await expect(t).toBeVisible();
    await expect(t).toContainText('Última lectura');
    await expect(t).toContainText(/ph/i);
    await expect(t).toContainText(/7[.,]42/);
    await page.waitForTimeout(700);
    await page.screenshot({ path: EV + 'EV-HU26-E2E-02_ubicacion-anadida-con-valores.png' });
  });

  test('CA2 sin duplicados: la ubicación ya añadida no vuelve a ofrecerse', async () => {
    await abrirSelector(page);
    await expect(page.locator('label:has(input[type=checkbox])', { hasText: U2 })).toBeVisible();
    await expect(page.locator('label:has(input[type=checkbox])', { hasText: U1 })).toHaveCount(0);
    await page.locator('label:has(input[type=checkbox])', { hasText: U2 }).locator('input').check();
    await agregar(page).click();
    await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
    await expect(tarjeta(page, U2)).toBeVisible();
    await expect(tarjeta(page, U2)).toContainText('Sin datos registrados');
    await abrirSelector(page);
    await expect(page.getByText('No hay más ubicaciones disponibles.')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU26-E2E-03_sin-mas-ubicaciones.png' });
    await page.getByRole('button', { name: 'Cancelar' }).click();
  });

  test('CA4 cancelar el modal de Quitar no retira la ubicación', async () => {
    await tarjeta(page, U2).getByRole('button', { name: 'Quitar del panel' }).click();
    await expect(page.getByText(`Quitar ${U2}`)).toBeVisible();
    await expect(page.getByText('Los datos de telemetría permanecerán disponibles.')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU26-E2E-04_modal-quitar.png' });
    await page.getByRole('button', { name: 'Cancelar' }).last().click();
    await expect(tarjeta(page, U2)).toBeVisible();
  });

  test('CA4 quitar retira la ubicación y muestra el mensaje; la telemetría sigue', async () => {
    await tarjeta(page, U1).getByRole('button', { name: 'Quitar del panel' }).click();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByRole('status')).toContainText('Ubicación retirada del panel');
    await expect(tarjeta(page, U1)).toHaveCount(0);
    await expect(tarjeta(page, U2)).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU26-E2E-05_ubicacion-retirada.png' });
    // La ubicación y sus lecturas siguen en el sistema: se vuelve a añadir y recupera los valores.
    await abrirSelector(page);
    await page.locator('label:has(input[type=checkbox])', { hasText: U1 }).locator('input').check();
    await agregar(page).click();
    await expect(tarjeta(page, U1)).toContainText(/7[.,]42/);
  });

  test('persistencia: al recargar el panel conserva las ubicaciones', async () => {
    await page.reload();
    await expect(tarjeta(page, U1)).toBeVisible();
    await expect(tarjeta(page, U2)).toBeVisible();
  });
});
