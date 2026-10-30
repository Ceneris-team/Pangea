// QA HU18 - Desactivar dispositivo: flujos de UI (CA1, CA2, CA3 y roles).
// Datos: BD pangea_e2e sembrada con seed_usuarios_prueba + seed_dispositivos_demo (solo local).
// Una sola sesión por rol (el backend limita los intentos de login por minuto).
import { test, expect } from '@playwright/test';

const CLAVE = 'Pangea2026';
const DISP = '[DEMO] Sonda EU (decimal coma)';
const EV = '../03_Evidencias/HU18/';

async function entrar(page, correo) {
  await page.goto('/');
  await page.getByPlaceholder('Ingresa tu correo').fill(correo);
  await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
  await page.locator('button.submit').click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  // CENERIS/Administrador eligen empresa antes de ver el menú de módulos.
  if (!/clientes/.test(page.url())) await page.getByRole('link', { name: 'Entorno de clientes' }).first().click({ timeout: 3000 }).catch(() => {});
  const entrarEmpresa = page.getByRole('button', { name: /Entrar al entorno de/ }).first();
  if (await entrarEmpresa.waitFor({ timeout: 6000 }).then(() => true, () => false)) await entrarEmpresa.click();
}

async function irAListado(page) {
  const enlace = page.getByRole('link', { name: 'Dispositivos', exact: true }).first();
  if (await enlace.waitFor({ timeout: 8000 }).then(() => true, () => false)) await enlace.click();
  else await page.goto('/dispositivos');
  await expect(page.locator('table')).toBeVisible();
  const buscador = page.getByRole('searchbox').or(page.getByPlaceholder(/buscar/i)).first();
  await buscador.fill('Sonda EU');
  await expect(fila(page)).toBeVisible();
}

const fila = (page) => page.locator('tr', { hasText: DISP });

test.describe.serial('HU18 flujos de UI como Técnico CENERIS', () => {
  let page;
  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await entrar(page, 'tecnico@pangea-dev.com');
    await irAListado(page);
  });
  test.afterAll(async () => page.context().close());

  test('CP-UI-01 CA1: Desactivar sobre un dispositivo Activo pide confirmación', async () => {
    await expect(fila(page)).toContainText('Activo');
    await fila(page).getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.getByText(`Desactivar dispositivo '${DISP}'`)).toBeVisible();
    await expect(page.getByText(/se detendrá la ingesta de sus archivos/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancelar' })).toBeVisible();
    await page.screenshot({ path: EV + 'EV-CP-052_modal-confirmacion.png' });
  });

  test('CP-UI-02 Cancelar no cambia el estado', async () => {
    await page.getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.getByText(`Desactivar dispositivo '${DISP}'`)).toHaveCount(0);
    await expect(fila(page)).toContainText('Activo');
    await expect(fila(page).getByRole('button', { name: 'Desactivar' })).toBeVisible();
  });

  test('CP-UI-03 CA2/CA3: confirmar desactiva, muestra el mensaje y ofrece Reactivar', async () => {
    await fila(page).getByRole('button', { name: 'Desactivar' }).click();
    // El modal bloquea el botón 3 s (cuenta regresiva); el botón de acción es el último del modal.
    const confirmar = page.getByRole('button', { name: /^Desactivar( \(\d\))?$/ }).last();
    await expect(confirmar).toBeEnabled({ timeout: 8000 });
    await confirmar.click();
    await expect(page.getByText('Dispositivo desactivado correctamente')).toBeVisible();
    await expect(fila(page)).toContainText('Inactivo');
    await expect(fila(page).getByRole('button', { name: 'Reactivar' })).toBeVisible();
    await expect(fila(page).getByRole('button', { name: 'Desactivar' })).toHaveCount(0);
    await page.screenshot({ path: EV + 'EV-CP-054_inactivo-con-reactivar.png' });
  });

  test('CP-UI-04 el estado Inactivo persiste al recargar', async () => {
    await page.reload();
    await irAListado(page);
    await expect(fila(page)).toContainText('Inactivo');
    await expect(fila(page).getByRole('button', { name: 'Reactivar' })).toBeVisible();
  });

  test('CP-UI-05 CA3: Reactivar devuelve el dispositivo a Activo', async () => {
    await fila(page).getByRole('button', { name: 'Reactivar' }).click();
    const confirmar = page.getByRole('button', { name: /^Reactivar( \(\d\))?$/ }).last();
    await expect(confirmar).toBeEnabled({ timeout: 8000 });
    await confirmar.click();
    await expect(page.getByText('Dispositivo reactivado correctamente')).toBeVisible();
    await expect(fila(page)).toContainText('Activo');
    await expect(fila(page).getByRole('button', { name: 'Desactivar' })).toBeVisible();
  });
});

test('CP-UI-06 Administrador ve la acción Desactivar', async ({ page }) => {
  await entrar(page, 'admin@pangea-dev.com');
  await irAListado(page);
  await expect(fila(page).getByRole('button', { name: 'Desactivar' })).toBeVisible();
});

test('CP-UI-07 Cliente Final no ve Desactivar ni Reactivar', async ({ page }) => {
  await entrar(page, 'cliente@pangea-dev.com');
  await page.goto('/dispositivos');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('table')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Desactivar' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reactivar' })).toHaveCount(0);
  await page.screenshot({ path: EV + 'EV-CP-058_cliente-sin-acciones.png' });
});
