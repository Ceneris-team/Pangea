// QA HU28 - Crear alarma: flujos de UI (CA1-CA4) como Cliente Final.
// Datos: BD pangea_e2e (seed_usuarios_prueba + seed_dispositivos_demo), solo local, rama fabio.
import { test, expect } from '@playwright/test';

const CLAVE = 'Pangea2026';
const U1 = '[DEMO] Río Rímac - Margen Izquierda';
const U2 = '[DEMO] Planta de Tratamiento';
const U3 = '[QA] Estación NO asignada';
const NOMBRE = `QA HU28 ${Date.now() % 100000}`;
const EV = process.env.EV_DIR || '../03_Evidencias/HU28/';

const nombre = (p) => p.locator('#nmbr');
const ubic = (p) => p.locator('#id_ubccn');
const param = (p) => p.locator('#id_prmtr');
const btn = (p, n) => p.getByRole('button', { name: n, exact: true });
const textos = (loc) => loc.locator('option').allTextContents();

async function filas(page) {
  await expect(page.locator('tr', { hasText: NOMBRE })).toBeVisible();
  return page.locator('tbody tr').count();
}
async function abrirFormulario(page) {
  await page.goto('/alarmas');
  await page.getByText('Crear alarma').first().click();
  await expect(page.getByRole('heading', { name: 'Crear alarma' })).toBeVisible();
}
async function paso1Completo(page, n = NOMBRE) {
  await nombre(page).fill(n);
  await ubic(page).selectOption({ label: U1 });
  await expect(param(page)).toBeEnabled();
  const etiqueta = (await textos(param(page))).find((t) => t.startsWith('ph ('));
  await param(page).selectOption({ label: etiqueta });
}

test.describe.serial('HU28 flujos de UI como Cliente Final', () => {
  let page;
  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await page.goto('/');
    await page.getByPlaceholder('Ingresa tu correo').fill('cliente@pangea-dev.com');
    await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
    await page.locator('button.submit').click();
    await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  });

  test('CA1 "Crear alarma" muestra el formulario con Nombre, Parámetro y Ubicación', async () => {
    await page.goto('/alarmas');
    await page.getByText('Crear alarma').first().click();
    await expect(page).toHaveURL(/\/alarmas\/nueva/);
    await expect(page.getByLabel(/Nombre de la alarma/)).toBeVisible();
    await expect(page.getByLabel(/Parámetro a monitorear/)).toBeVisible();
    await expect(page.getByLabel(/Ubicación asociada/)).toBeVisible();
    await expect(btn(page, 'Siguiente')).toBeVisible();
    await expect(btn(page, 'Cancelar')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU28-E2E-01_formulario-paso1.png' });
  });

  test('PP-226 el selector de ubicaciones solo ofrece las asignadas al usuario', async () => {
    await expect(ubic(page).locator('option', { hasText: U1 })).toHaveCount(1);
    const t = await textos(ubic(page));
    expect(t).toContain(U1);
    expect(t).toContain(U2);
    expect(t).not.toContain(U3);
    await expect(param(page)).toBeDisabled();
  });

  test('PP-226 el selector de parámetros muestra solo los numéricos de la ubicación elegida', async () => {
    await ubic(page).selectOption({ label: U1 });
    await expect(param(page)).toBeEnabled();
    const t1 = (await textos(param(page))).join('|');
    expect(t1).toMatch(/ph/);
    expect(t1).toMatch(/conductividad/);
    expect(t1).not.toMatch(/mensaje_/);
    await page.screenshot({ path: EV + 'EV-HU28-E2E-02_parametros-ubicacion1.png' });
    await ubic(page).selectOption({ label: U2 });
    await expect(param(page)).toBeEnabled();
    const t2 = (await textos(param(page))).join('|');
    expect(t2).toMatch(/contador_puerta/);
    expect(t2).not.toMatch(/conductividad/);
    expect(t2).not.toMatch(/mensaje_/);
  });

  test('cambiar de ubicación descarta el parámetro elegido', async () => {
    await ubic(page).selectOption({ label: U1 });
    await param(page).selectOption({ index: 1 });
    await expect(param(page)).not.toHaveValue('');
    await ubic(page).selectOption({ label: U2 });
    await expect(param(page)).toHaveValue('');
  });

  test('CA2 (negativo) SIGUIENTE sin completar obligatorios no avanza y avisa', async () => {
    await page.reload();
    await btn(page, 'Siguiente').click();
    await expect(page.getByText('El nombre de la alarma es obligatorio')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU28-E2E-03_error-nombre-obligatorio.png' });
    await nombre(page).fill('   ');
    await btn(page, 'Siguiente').click();
    await expect(page.getByText('El nombre de la alarma es obligatorio')).toBeVisible();
    await nombre(page).fill(NOMBRE);
    await btn(page, 'Siguiente').click();
    await expect(page.getByText('Selecciona la ubicación asociada')).toBeVisible();
    await ubic(page).selectOption({ label: U1 });
    await expect(param(page)).toBeEnabled();
    await btn(page, 'Siguiente').click();
    await expect(page.getByText('Selecciona el parámetro a monitorear')).toBeVisible();
    await expect(page.locator('#oprdr')).toHaveCount(0);
  });

  test('nombre: máximo 100 caracteres en el campo', async () => {
    await nombre(page).fill('A'.repeat(130));
    expect((await nombre(page).inputValue()).length).toBe(100);
    await expect(page.getByText('100/100 caracteres')).toBeVisible();
  });

  test('CA2 SIGUIENTE con obligatorios completos lleva al paso de condiciones', async () => {
    await page.reload();
    await paso1Completo(page);
    await btn(page, 'Siguiente').click();
    await expect(page.locator('#oprdr')).toBeVisible();
    await expect(page.locator('#vlr_umbrl')).toBeVisible();
    await expect(page.getByText(NOMBRE)).toBeVisible();
    await expect(btn(page, 'Guardar')).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HU28-E2E-04_paso2-condiciones.png' });
  });

  test('Atrás conserva lo tecleado en el paso 1', async () => {
    await btn(page, 'Atrás').click();
    await expect(nombre(page)).toHaveValue(NOMBRE);
    await expect(ubic(page).locator('option:checked')).toHaveText(U1);
    await expect(param(page)).not.toHaveValue('');
    await btn(page, 'Siguiente').click();
  });

  test('CA3 (negativo) GUARDAR sin umbral muestra error y no crea', async () => {
    await btn(page, 'Guardar').click();
    await expect(page.getByText('Indica el valor umbral de la condición')).toBeVisible();
    await expect(page).toHaveURL(/\/alarmas\/nueva/);
  });

  test('CA3 GUARDAR crea la alarma Activa, la agrega al listado y muestra el mensaje', async () => {
    await page.locator('#oprdr').selectOption('>');
    await page.locator('#vlr_umbrl').fill('8.5');
    await btn(page, 'Guardar').click();
    await expect(page).toHaveURL(/\/alarmas$/);
    await expect(page.getByText('Alarma creada correctamente')).toBeVisible();
    const fila = page.locator('tr', { hasText: NOMBRE });
    await expect(fila).toHaveCount(1);
    await expect(fila).toContainText('Activa');
    await expect(fila).toContainText(/ph/i);
    await page.screenshot({ path: EV + 'EV-HU28-E2E-05_alarma-creada-en-listado.png' });
  });

  test('CA4 CANCELAR en el paso 1 vuelve al listado sin crear registro', async () => {
    await page.goto('/alarmas');
    const antes = await filas(page);
    await page.getByText('Crear alarma').first().click();
    await nombre(page).fill('QA HU28 cancelada paso1');
    await btn(page, 'Cancelar').click();
    await expect(page).toHaveURL(/\/alarmas$/);
    await expect(page.locator('tr', { hasText: 'QA HU28 cancelada paso1' })).toHaveCount(0);
    expect(await filas(page)).toBe(antes);
    await page.screenshot({ path: EV + 'EV-HU28-E2E-06_cancelar-paso1.png' });
  });

  test('CA4 CANCELAR en el paso 2 descarta todo y no crea registro', async () => {
    const antes = await filas(page);
    await page.getByText('Crear alarma').first().click();
    await paso1Completo(page, 'QA HU28 cancelada paso2');
    await btn(page, 'Siguiente').click();
    await page.locator('#vlr_umbrl').fill('3');
    await btn(page, 'Cancelar').click();
    await expect(page).toHaveURL(/\/alarmas$/);
    await expect(page.locator('tr', { hasText: 'QA HU28 cancelada paso2' })).toHaveCount(0);
    expect(await filas(page)).toBe(antes);
    // al volver a abrir el formulario está vacío
    await page.getByText('Crear alarma').first().click();
    await expect(nombre(page)).toHaveValue('');
  });

  test('error: nombre con caracteres no válidos lo rechaza el backend y no crea', async () => {
    await page.goto('/alarmas');
    const antes = await filas(page);
    await page.getByText('Crear alarma').first().click();
    await paso1Completo(page, '<script>alert(1)</script>');
    await btn(page, 'Siguiente').click();
    // En dev (ronda 2) el nombre se valida en el paso 1: no avanza y explica la regla.
    await expect(page.locator('#oprdr')).toHaveCount(0);
    await expect(page).toHaveURL(/\/alarmas\/nueva/);
    await page.waitForTimeout(800);
    await page.screenshot({ path: EV + 'EV-HU28-E2E-07_error-nombre-invalido.png' });
    // DEF-02: el mensaje de error debe ser legible y explicar la regla del nombre
    await expect(page.getByText('[object Object]')).toHaveCount(0);
    await expect(page.getByText(/alfanum/i)).toBeVisible();
    await page.goto('/alarmas');
    expect(await filas(page)).toBe(antes);
  });
});
