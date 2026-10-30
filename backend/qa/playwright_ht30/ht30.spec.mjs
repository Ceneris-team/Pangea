// QA HT-30.2 (PP-401) - Flujos principales de Pangea de punta a punta (F1 a F7), casos CP-128 a CP-167.
// Datos: BD pangea_e2e (seed del proyecto), solo local. El backend corre con RATELIMIT_STORAGE_URL=redis://localhost:6379/5
// y se vacía ese índice antes de cada login: el límite de 5 logins cada 5 minutos es del producto y no se toca.
import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';

const CLAVE = process.env.QA_CLAVE ?? 'Pangea2026'; // contraseña del seed (app/scripts/seed_usuarios_prueba.py)
const ADMIN = 'admin@pangea-dev.com';
const TECNICO = 'tecnico@pangea-dev.com';
const CLIENTE = 'cliente@pangea-dev.com';
const COMERCIAL = 'comercial@pangea-dev.com';
const U_DEMO = '[DEMO] Río Rímac - Margen Izquierda';
const U_QA = '[QA] Estación NO asignada';
const EV = '../03_Evidencias/HT-30.2/';

const reiniciarLimite = () => execSync('docker exec pangea-redis-1 redis-cli -n 5 FLUSHDB');

async function abrirLogin(browser) {
  const page = await (await browser.newContext()).newPage();
  await page.goto('/login');
  return page;
}

async function enviarLogin(page, correo, clave) {
  reiniciarLimite();
  await page.getByPlaceholder('Ingresa tu correo').fill(correo);
  await page.getByPlaceholder('Ingresa tu contraseña').fill(clave);
  await page.locator('button.submit').click();
}

async function sesion(browser, correo) {
  const page = await abrirLogin(browser);
  await enviarLogin(page, correo, CLAVE);
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  return page;
}

const enLogin = (page) => expect(page).toHaveURL(/\/login$/, { timeout: 10000 });

test.describe('F1 Autenticación', () => {
  test('F1 login Administrador redirige a /panel-admin', async ({ browser }) => {
    const page = await abrirLogin(browser);
    await enviarLogin(page, ADMIN, CLAVE);
    await expect(page.getByText('Bienvenido, Ana Administrador')).toBeVisible();
    await expect(page).toHaveURL(/\/panel-admin$/, { timeout: 20000 });
    await expect(page.getByRole('heading', { name: 'Administración de Pangea' })).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HT302-E2E-01_login-administrador.png' });
  });

  test('F1 login Técnico CENERIS redirige al entorno de clientes', async ({ browser }) => {
    const page = await sesion(browser, TECNICO);
    await expect(page).toHaveURL(/\/clientes$/);
    await expect(page.getByRole('heading', { name: 'Entorno de clientes' })).toBeVisible();
  });

  test('F1 login Cliente Final redirige a /paneles', async ({ browser }) => {
    const page = await sesion(browser, CLIENTE);
    await expect(page).toHaveURL(/\/paneles$/);
    await expect(page.getByText('Tableros Personalizables').first()).toBeVisible();
  });

  test('F1 login Administrador Comercial redirige a /panel-comercial', async ({ browser }) => {
    const page = await sesion(browser, COMERCIAL);
    await expect(page).toHaveURL(/\/panel-comercial$/);
    await expect(page.getByText('Planes y suscripciones').first()).toBeVisible();
  });

  test('F1 contraseña incorrecta muestra «Correo o contraseña incorrectos»', async ({ browser }) => {
    const page = await abrirLogin(browser);
    await enviarLogin(page, CLIENTE, 'ClaveErronea-QA1');
    await expect(page.getByText('Correo o contraseña incorrectos')).toBeVisible();
    await enLogin(page);
    await page.screenshot({ path: EV + 'EV-HT302-E2E-02_credenciales-incorrectas.png' });
  });

  test('F1 correo con formato inválido se valida en el formulario', async ({ browser }) => {
    const page = await abrirLogin(browser);
    let peticiones = 0;
    page.on('request', (r) => { if (r.url().includes('/auth/login')) peticiones += 1; });
    await page.getByPlaceholder('Ingresa tu correo').fill('correo-sin-arroba');
    await page.getByPlaceholder('Ingresa tu contraseña').fill('cualquiera');
    await page.locator('button.submit').click();
    await expect(page.getByText('Ingresa un correo electrónico válido.')).toBeVisible();
    expect(peticiones).toBe(0);
  });

  test('F1 contraseña vacía se valida en el formulario', async ({ browser }) => {
    const page = await abrirLogin(browser);
    let peticiones = 0;
    page.on('request', (r) => { if (r.url().includes('/auth/login')) peticiones += 1; });
    await page.getByPlaceholder('Ingresa tu correo').fill(CLIENTE);
    await page.locator('button.submit').click();
    await expect(page.getByText('Ingresa tu contraseña.')).toBeVisible();
    expect(peticiones).toBe(0);
  });

  test('F1 la sesión se mantiene al recargar', async ({ browser }) => {
    const page = await sesion(browser, CLIENTE);
    await page.reload();
    await expect(page).toHaveURL(/\/paneles$/);
    await expect(page.getByText('Tableros Personalizables').first()).toBeVisible();
  });

  test('F1 cerrar sesión invalida el acceso a rutas protegidas', async ({ browser }) => {
    const page = await sesion(browser, CLIENTE);
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await enLogin(page);
    await page.goto('/paneles');
    await enLogin(page);
  });
});

test.describe('F2 Control de acceso por rol', () => {
  test('F2 sin sesión las rutas protegidas redirigen a /login', async ({ browser }) => {
    const page = await (await browser.newContext()).newPage();
    for (const ruta of ['/usuarios', '/paneles', '/consulta-datos']) {
      await page.goto(ruta);
      await enLogin(page);
    }
  });

  test('F2 Cliente Final no entra a /usuarios', async ({ browser }) => {
    const page = await sesion(browser, CLIENTE);
    await page.goto('/usuarios');
    await enLogin(page);
  });

  test('F2 Cliente Final no entra a /cola-ingesta', async ({ browser }) => {
    const page = await sesion(browser, CLIENTE);
    await page.goto('/cola-ingesta');
    await enLogin(page);
  });

  test('F2 Técnico CENERIS no entra a /usuarios', async ({ browser }) => {
    const page = await sesion(browser, TECNICO);
    await page.goto('/usuarios');
    await enLogin(page);
  });

  test('F2 Administrador Comercial entra a planes y no a usuarios', async ({ browser }) => {
    const page = await sesion(browser, COMERCIAL);
    await page.goto('/planes-suscripciones');
    await expect(page).toHaveURL(/\/planes-suscripciones$/);
    await expect(page.getByRole('heading', { name: 'Planes y suscripciones' })).toBeVisible();
    await page.goto('/usuarios');
    await enLogin(page);
  });

  test('F2 CENERIS sin cliente elegido es enviado a /clientes', async ({ browser }) => {
    const page = await sesion(browser, TECNICO);
    await page.goto('/dispositivos');
    await expect(page).toHaveURL(/\/clientes$/);
    await expect(page.getByRole('heading', { name: 'Entorno de clientes' })).toBeVisible();
  });

  test('F2 Administrador entra a /usuarios', async ({ browser }) => {
    const page = await sesion(browser, ADMIN);
    await page.goto('/usuarios');
    await expect(page).toHaveURL(/\/usuarios$/);
    await expect(page.getByRole('cell', { name: CLIENTE })).toBeVisible();
  });
});

test.describe.serial('F3 Entorno CENERIS y dispositivos', () => {
  let page;
  test.beforeAll(async ({ browser }) => { page = await sesion(browser, TECNICO); });

  test('F3 búsqueda de empresa sin coincidencias', async () => {
    await page.getByLabel('Buscar cliente').fill('zzz-sin-coincidencia');
    await expect(page.getByText('No se encontraron clientes.')).toBeVisible();
    await page.getByLabel('Buscar cliente').fill('');
  });

  test('F3 Técnico elige empresa y entra a su entorno', async () => {
    await page.getByLabel('Buscar cliente').fill('Demo');
    await expect(page.getByRole('heading', { name: 'Cliente Demo' })).toBeVisible();
    await page.getByRole('button', { name: 'Entrar al entorno de Cliente Demo' }).click();
    await expect(page).toHaveURL(/\/ubicaciones$/);
    await expect(page.getByRole('cell', { name: U_DEMO })).toBeVisible();
  });

  test('F3 listado de dispositivos con filtro por estado', async () => {
    await page.goto('/dispositivos');
    await expect(page.getByRole('heading', { name: 'Gestión de Dispositivos' })).toBeVisible();
    const filas = page.locator('tbody tr');
    await expect(filas.filter({ hasText: 'Inactivo' })).toHaveCount(1);
    await page.locator('select', { has: page.locator('option', { hasText: 'Todos los estados' }) }).selectOption({ label: 'Activo' });
    await expect(filas.filter({ hasText: 'Inactivo' })).toHaveCount(0);
    await expect(filas).toHaveCount(5);
    await page.screenshot({ path: EV + 'EV-HT302-E2E-03_dispositivos-activos.png' });
  });

  test('F3 abrir la ficha de un dispositivo', async () => {
    await page.getByRole('row', { name: /\[DEMO\] CR1000 Río A/ }).getByRole('button', { name: 'Configurar' }).click();
    await expect(page).toHaveURL(/\/dispositivos\/\d+$/);
    await expect(page.getByText('[DEMO] CR1000 Río A').first()).toBeVisible();
  });

  test('F3 añadir dispositivo sin nombre se rechaza', async () => {
    await page.goto('/dispositivos');
    await page.getByRole('button', { name: 'Añadir dispositivo' }).click();
    await page.getByRole('button', { name: /^(Guardar|Añadir|Registrar)/ }).last().click();
    await expect(page.getByText('El nombre del dispositivo es obligatorio')).toBeVisible();
  });
});

test.describe.serial('F4 Consulta de datos', () => {
  let page;
  test.beforeAll(async ({ browser }) => { page = await sesion(browser, CLIENTE); await page.goto('/consulta-datos'); });

  const filas = () => page.locator('tbody tr');
  const abrirFiltros = () => page.getByRole('button', { name: /^Filtros/ }).click();
  const cerrarFiltros = () => page.getByRole('button', { name: 'Cerrar panel' }).click();

  test('F4 consulta de datos por proyecto y parámetro', async () => {
    await expect(page.getByRole('heading', { name: 'Consulta de Datos' })).toBeVisible();
    for (const col of ['Parámetro', 'Proyecto', 'Valor', 'Fecha']) await expect(page.getByRole('columnheader', { name: col })).toBeVisible();
    await abrirFiltros();
    await page.locator('label', { hasText: /^ph/ }).first().click();
    await page.locator('label', { hasText: U_DEMO }).first().click();
    // Hay dos «APLICAR» en el panel (rango de fechas y selección); se usa el que acompaña a «LIMPIAR FILTROS».
    await page.locator('div:has(> button:text-is("LIMPIAR FILTROS")) > button:text-is("APLICAR")').click();
    await expect(page.getByText('Cargando datos...')).toHaveCount(0, { timeout: 15000 });
    await expect(filas().first()).toBeVisible();
    const parametros = await filas().locator('td:nth-child(1)').allTextContents();
    expect(parametros.length).toBeGreaterThan(0);
    expect(new Set(parametros.map((t) => t.trim()))).toEqual(new Set(['ph']));
    await cerrarFiltros();
    await page.waitForTimeout(500);
    await page.screenshot({ path: EV + 'EV-HT302-E2E-04_consulta-ph.png' });
  });

  test('F4 filtro avanzado con mínimo mayor que máximo', async () => {
    await abrirFiltros();
    await page.getByLabel('Valor mínimo').fill('10');
    await page.getByLabel('Valor máximo').fill('5');
    await page.getByRole('button', { name: 'APLICAR FILTROS' }).click();
    await expect(page.getByText('El valor mínimo no puede ser mayor que el valor máximo.')).toBeVisible();
    await page.getByRole('button', { name: 'LIMPIAR FILTROS AVANZADOS' }).click();
  });

  test('F4 limpiar filtros restablece la consulta', async () => {
    await page.getByRole('button', { name: 'LIMPIAR FILTROS', exact: true }).first().click();
    await cerrarFiltros();
    await expect.poll(async () => new Set((await filas().locator('td:nth-child(1)').allTextContents()).map((t) => t.trim())).has('temperatura')).toBe(true);
  });
});

test.describe.serial('F5 Tableros personalizables', () => {
  let page;
  const PANEL = `QA HT30 ${Date.now() % 100000}`;
  test.beforeAll(async ({ browser }) => { page = await sesion(browser, CLIENTE); });

  test('F5 listado de paneles ordenado por fecha', async () => {
    for (const col of ['Nombre', 'Fecha de creación', 'Acciones']) await expect(page.getByRole('columnheader', { name: col })).toBeVisible();
    await expect(page.locator('tbody tr', { hasText: 'QA HU' }).first()).toBeVisible();
    const nombres = (await page.locator('tbody tr td:first-child').allTextContents()).map((t) => t.trim());
    expect(nombres.length).toBeGreaterThan(1);
    // Los paneles del seed QA se crearon en orden: el más nuevo (mayor id) debe ir primero.
    expect(nombres[0]).toMatch(/QA HU34/);
  });

  test('F5 crear panel sin nombre se rechaza', async () => {
    await page.getByRole('button', { name: 'Crear panel' }).first().click();
    await page.getByRole('button', { name: 'Guardar', exact: true }).click();
    await expect(page.getByText('El nombre del panel es obligatorio')).toBeVisible();
  });

  test('F5 nombre de panel con caracteres especiales se rechaza', async () => {
    await page.getByPlaceholder('Resumen de estaciones').fill('Panel #1!');
    await page.getByRole('button', { name: 'Guardar', exact: true }).click();
    await expect(page.getByText('El nombre solo puede contener letras, números y espacios')).toBeVisible();
  });

  test('F5 crear panel abre su detalle', async () => {
    await page.getByPlaceholder('Resumen de estaciones').fill(PANEL);
    await page.getByRole('button', { name: 'Guardar', exact: true }).click();
    await page.waitForURL(/\/paneles\/\d+$/);
    await expect(page.getByText(PANEL).first()).toBeVisible();
  });

  test('F5 añadir ubicación y widget al panel', async () => {
    await page.getByRole('button', { name: '+ Añadir ubicaciones' }).first().click();
    await page.locator('label:has(input[type=checkbox])', { hasText: U_DEMO }).locator('input').check();
    await page.getByRole('button', { name: /^Agregar al panel/ }).click();
    await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
    await page.getByRole('button', { name: '+ Añadir widget' }).click();
    await page.getByLabel('Tipo de widget').selectOption('linea');
    await page.getByLabel('Ubicación').selectOption({ label: U_DEMO });
    await page.locator('select', { has: page.locator('option', { hasText: 'Selecciona un parámetro' }) }).selectOption({ label: 'ph (pH)' });
    await page.getByRole('button', { name: 'Guardar widget' }).click();
    await expect(page.getByRole('status')).toContainText('Widget creado correctamente');
    await expect(page.getByRole('img', { name: `Gráfico de ph en ${U_DEMO}` })).toBeVisible();
    await page.waitForTimeout(800);
    await page.screenshot({ path: EV + 'EV-HT302-E2E-05_panel-con-widget.png' });
  });

  test('F5 buscar panel por nombre', async () => {
    await page.goto('/paneles');
    const buscar = page.getByPlaceholder('Buscar por nombre de panel...');
    await buscar.fill('HT30');
    await expect(page.locator('tbody tr', { hasText: PANEL })).toBeVisible();
    await expect(page.locator('tbody tr', { hasText: 'QA HU34' })).toHaveCount(0);
    await buscar.fill('zzz');
    await expect(page.getByText('No se encontraron paneles con ese criterio.')).toBeVisible();
    await buscar.fill('');
  });

  test('F5 eliminar panel con confirmación', async () => {
    await page.locator('tbody tr', { hasText: PANEL }).getByRole('button', { name: 'Eliminar' }).click();
    await page.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('tbody tr', { hasText: PANEL })).toHaveCount(0);
  });
});

test.describe.serial('F6 Administración y permisos', () => {
  let admin;
  const filaCliente = () => admin.getByRole('row', { name: new RegExp(CLIENTE) });
  const casilla = (nombre) => admin.locator('label', { hasText: nombre }).locator('input[type=checkbox]');
  const abrirPermisos = async () => { await filaCliente().getByRole('button', { name: 'Gestionar permisos' }).click(); await expect(casilla(U_QA)).toBeVisible(); };
  const proyectosDelCliente = async (browser) => {
    const c = await sesion(browser, CLIENTE);
    await c.goto('/consulta-datos');
    await c.getByRole('button', { name: /^Filtros/ }).click();
    const fs = c.getByRole('dialog', { name: 'Filtros' }).locator('fieldset', { has: c.locator('legend', { hasText: 'Proyectos' }) });
    await expect(fs.locator('label').first()).toBeVisible();
    const nombres = (await fs.locator('label').allTextContents()).map((t) => t.trim());
    await c.context().close();
    return nombres;
  };
  test.beforeAll(async ({ browser }) => {
    // Precondición: el cliente del seed no tiene acceso a la estación [QA] (por si una corrida anterior se cortó a mitad).
    execSync(`docker exec pangea-db-1 psql -U postgres -d pangea_e2e -c "delete from prms_ubccn p using usr u, ubccn b where p.id_usr = u.id_usr and p.id_ubccn = b.id_ubccn and u.crr = '${CLIENTE}' and b.nmbr = '${U_QA}'"`);
    admin = await sesion(browser, ADMIN);
    await admin.goto('/usuarios');
  });

  test('F6 Gestionar permisos solo para Cliente Final', async () => {
    await expect(filaCliente()).toBeVisible();
    await expect(admin.getByRole('button', { name: 'Gestionar permisos' })).toHaveCount(1);
    await expect(filaCliente().getByRole('button', { name: 'Gestionar permisos' })).toBeVisible();
  });

  test('F6 guardar permisos de ubicación', async () => {
    await abrirPermisos();
    await expect(casilla(U_QA)).not.toBeChecked();
    await casilla(U_QA).check();
    await admin.getByRole('button', { name: 'GUARDAR PERMISOS' }).click();
    await expect(admin.getByText('Permisos actualizados correctamente')).toBeVisible();
    await admin.screenshot({ path: EV + 'EV-HT302-E2E-06_permisos-guardados.png' });
  });

  test('F6 cancelar no modifica los permisos', async () => {
    await admin.goto('/usuarios');
    await abrirPermisos();
    await casilla(U_DEMO).uncheck();
    await admin.getByRole('button', { name: 'CANCELAR' }).click();
    await expect(casilla(U_QA)).toHaveCount(0);
    await abrirPermisos();
    await expect(casilla(U_DEMO)).toBeChecked();
    await expect(casilla(U_QA)).toBeChecked();
  });

  test('F6 el cliente solo ve las ubicaciones permitidas', async ({ browser }) => {
    expect(await proyectosDelCliente(browser)).toContain(U_QA);
    // Se restablece el permiso original y el cliente deja de verla sin volver a configurar nada.
    await casilla(U_QA).uncheck();
    await admin.getByRole('button', { name: 'GUARDAR PERMISOS' }).click();
    await expect(admin.getByText('Permisos actualizados correctamente')).toBeVisible();
    const despues = await proyectosDelCliente(browser);
    expect(despues).not.toContain(U_QA);
    expect(despues).toContain(U_DEMO);
  });

  test('F6 Administrador ve el listado de empresas', async () => {
    await admin.goto('/empresas');
    await expect(admin.getByRole('heading', { name: 'Empresas y proyectos' })).toBeVisible();
    await expect(admin.getByText(/\d+ proyectos · \d+ usuarios activos/).first()).toBeVisible();
    await expect(admin.getByRole('button', { name: 'Registrar empresa' }).first()).toBeVisible();
  });
});

test.describe('F7 Recuperar contraseña', () => {
  const MSG = 'Te hemos enviado un correo con las instrucciones para recuperar tu contraseña';
  test.beforeEach(() => reiniciarLimite()); // /auth/olvide-contrasena admite 5 solicitudes cada 15 minutos

  test('F7 recuperar contraseña con correo registrado', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('link', { name: /Olvidaste tu contraseña/ }).click();
    await expect(page).toHaveURL(/\/olvide-contrasena$/);
    await page.getByPlaceholder('Ingresa tu correo').fill(CLIENTE);
    await page.getByRole('button', { name: 'Enviar' }).click();
    await expect(page.getByText(MSG)).toBeVisible();
    await page.screenshot({ path: EV + 'EV-HT302-E2E-07_recuperar-contrasena.png' });
  });

  test('F7 correo no registrado no revela si la cuenta existe', async ({ page }) => {
    await page.goto('/olvide-contrasena');
    await page.getByPlaceholder('Ingresa tu correo').fill('noexiste@pangea-dev.com');
    await page.getByRole('button', { name: 'Enviar' }).click();
    await expect(page.getByText(MSG)).toBeVisible();
  });

  test('F7 correo con formato inválido en recuperación', async ({ page }) => {
    await page.goto('/olvide-contrasena');
    await page.getByPlaceholder('Ingresa tu correo').fill('correo-sin-arroba');
    await page.getByRole('button', { name: 'Enviar' }).click();
    await expect(page.getByText('Ingresa un correo electrónico válido.')).toBeVisible();
  });

  test('F7 volver a iniciar sesión', async ({ page }) => {
    await page.goto('/olvide-contrasena');
    await page.getByRole('link', { name: 'Volver a iniciar sesión' }).click();
    await enLogin(page);
  });
});
