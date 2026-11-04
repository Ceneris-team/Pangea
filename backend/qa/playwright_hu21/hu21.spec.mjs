// QA HU-21 Conceder permisos (PP-414): flujos de UI de las dos modalidades, cancelación y revocación con sesión abierta.
// Datos: BD pangea_e2e_hu21 (seed_hu21.py), solo local. Se vacía el índice del límite de login antes de cada login:
// el límite de 5 logins cada 5 minutos es del producto y no se toca.
import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';
import path from 'node:path';

const CLAVE = process.env.QA_CLAVE ?? 'Pangea2026'; // contraseña del seed
const API = 'http://127.0.0.1:8021';
const EV = '../03_Evidencias/HU21/';
const PY = path.resolve('../../venv/Scripts/python.exe');
const SEED = path.resolve('seed_hu21.py');
const CF = 'cf@hu21.pangea-dev.com';
const LECTOR = 'lector@hu21.pangea-dev.com';
const LECTOR2 = 'lector2@hu21.pangea-dev.com';

let ids;
function resembrar() {
  const salida = execSync(`"${PY}" "${SEED}"`, {
    cwd: path.resolve('../../../../Pangea-hu21/backend'),
    env: {
      ...process.env, PYTHONPATH: '.',
      DATABASE_URL: 'postgresql+psycopg2://postgres:postgres@localhost:55432/pangea_e2e_hu21',
    },
  }).toString().trim().split('\n').pop();
  ids = JSON.parse(salida);
}

async function sesion(browser, correo) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto('/login');
  execSync('docker exec pangea-redis-1 redis-cli -n 1 FLUSHDB');
  await page.getByPlaceholder('Ingresa tu correo').fill(correo);
  await page.getByPlaceholder('Ingresa tu contraseña').fill(CLAVE);
  await page.locator('button.submit').click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  return page;
}

const verEmpresa = async (page, id) => { await page.goto(`/empresas?cliente=${id}`); await expect(page.getByRole('heading', { name: /^Usuarios de/ })).toBeVisible(); };
const tarjeta = (page, correo) => page.locator('div.rounded-xl', { hasText: correo }).last();
const abrirPermisos = async (page, correo) => {
  await page.goto('/usuarios');
  const fila = await buscar(page, correo);
  await fila.getByRole('button', { name: 'Gestionar permisos' }).click();
  await expect(page.getByRole('button', { name: 'GUARDAR PERMISOS' })).toBeEnabled();
};
// Abre la consulta y espera la primera lectura de /auth/acceso: desde ahí la pantalla puede detectar cambios.
const abrirConsulta = async (page) => {
  const acceso = page.waitForResponse('**/auth/acceso');
  await page.goto('/consulta-datos');
  await acceso;
};
const buscar = async (page, correo) => {
  await page.getByPlaceholder('Buscar por nombre o correo...').fill(correo);
  const fila = page.locator('tr', { hasText: correo }).first();
  await expect(fila).toBeVisible();
  return fila;
};
const casilla = (page, texto) => page.locator('label', { hasText: texto }).locator('input[type=checkbox]');
const putAnterior = (page, usuario, lista) => page.context().request.put(`${API}/usuarios/${usuario}/permisos-ubicaciones`, { data: { ubicacion_ids: lista } });
const patchMiembro = (page, cliente, miembro, datos) => page.context().request.patch(`${API}/empresas/${cliente}/usuarios/${miembro}`, { data: datos });

test.describe.serial('Flujo anterior: Usuarios > Gestionar permisos', () => {
  let admin;
  test.beforeAll(async ({ browser }) => { resembrar(); admin = await sesion(browser, 'admin@pangea-dev.com'); });
  test.afterAll(async () => { await admin.context().close(); });

  test('CA-01 Gestionar permisos solo se ofrece a Cliente Final; la cuenta empresarial va a Empresas', async () => {
    await admin.goto('/usuarios');
    await expect((await buscar(admin, CF)).getByRole('button', { name: 'Gestionar permisos' })).toBeVisible();
    await expect((await buscar(admin, 'admin@pangea-dev.com')).getByRole('button', { name: 'Gestionar permisos' })).toHaveCount(0);
    const empresa = await buscar(admin, LECTOR);
    await expect(empresa.getByRole('button', { name: 'Gestionar permisos' })).toHaveCount(0);
    await expect(empresa.getByRole('link', { name: 'Gestionar en empresa' })).toBeVisible();
  });

  test('CA-02 el panel muestra usuario, correo, tipo, empresa, sede, estado y selección actual', async () => {
    await abrirPermisos(admin, CF);
    const drawer = admin.getByText('Permisos de proyecto').locator('..').locator('..');
    await expect(admin.getByText(`(${CF}) · Cliente Final`)).toBeVisible();
    await expect(admin.getByText('Clara Final', { exact: true }).first()).toBeVisible();
    await expect(admin.getByText('QA Andina · Sede Lima · Activa').first()).toBeVisible();
    await expect(admin.getByText('QA Sur · Sede Arequipa · Activa')).toBeVisible();
    await expect(casilla(admin, 'QA Andina · Sede Lima · Activa').filter({ visible: true }).first()).toBeChecked();
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-01_panel-anterior.png' });
    void drawer;
  });

  test('CA-02 un proyecto que el alcance impide no se ofrece y se explica el motivo', async () => {
    const sur = admin.locator('label', { hasText: 'QA Sur · Sede Arequipa' });
    await expect(sur.locator('input')).toBeDisabled();
    await expect(sur).toContainText('no corresponde a la única sede');
    const inactivo = admin.locator('label', { hasText: 'Antiguo QA' });
    await expect(inactivo.locator('input')).toBeDisabled();
    await expect(inactivo).toContainText('inactivos');
  });

  test('CA-04 CANCELAR descarta y al reabrir se ve lo último guardado', async () => {
    const relaves = admin.locator('label', { hasText: 'Relaves QA' }).locator('input');
    await relaves.check();
    await admin.getByRole('button', { name: 'CANCELAR' }).click();
    await expect(admin.getByRole('button', { name: 'GUARDAR PERMISOS' })).toHaveCount(0);
    await abrirPermisos(admin, CF);
    await expect(admin.locator('label', { hasText: 'Relaves QA' }).locator('input')).not.toBeChecked();
  });

  test('CA-04 cerrar la edición sin guardar también descarta', async () => {
    await admin.locator('label', { hasText: 'Relaves QA' }).locator('input').check();
    await admin.getByRole('button', { name: 'Cerrar panel' }).click();
    await expect(admin.getByRole('button', { name: 'GUARDAR PERMISOS' })).toHaveCount(0);
    await abrirPermisos(admin, CF);
    await expect(admin.locator('label', { hasText: 'Relaves QA' }).locator('input')).not.toBeChecked();
  });

  test('CA-03 si el guardado falla se muestra el motivo y la selección queda para reintentar', async () => {
    await admin.locator('label', { hasText: 'Relaves QA' }).locator('input').check();
    await admin.route('**/permisos-ubicaciones', (r) => (r.request().method() === 'PUT'
      ? r.fulfill({ status: 409, contentType: 'application/json', json: { detail: 'Los permisos cambiaron mientras guardabas, vuelve a intentarlo' } })
      : r.continue()));
    await admin.getByRole('button', { name: 'GUARDAR PERMISOS' }).click();
    await expect(admin.getByText('Los permisos cambiaron mientras guardabas, vuelve a intentarlo')).toBeVisible();
    await expect(admin.locator('label', { hasText: 'Relaves QA' }).locator('input')).toBeChecked();
    await admin.unroute('**/permisos-ubicaciones');
  });

  test('CA-03 GUARDAR PERMISOS confirma con el mensaje exacto y persiste', async () => {
    await admin.getByRole('button', { name: 'GUARDAR PERMISOS' }).click();
    await expect(admin.getByText('Permisos actualizados correctamente')).toBeVisible();
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-02_permisos-guardados.png' });
    await abrirPermisos(admin, CF);
    await expect(admin.locator('label', { hasText: 'Relaves QA' }).locator('input')).toBeChecked();
  });

  test('CA-02 durante la carga no se puede guardar', async () => {
    await admin.getByRole('button', { name: 'CANCELAR' }).click();
    await admin.route('**/permisos-ubicaciones', async (r) => { await new Promise((f) => setTimeout(f, 1500)); await r.continue(); });
    await (await buscar(admin, CF)).getByRole('button', { name: 'Gestionar permisos' }).click();
    await expect(admin.getByText('Cargando proyectos…')).toBeVisible();
    await expect(admin.getByRole('button', { name: 'GUARDAR PERMISOS' })).toBeDisabled();
    await expect(admin.getByRole('button', { name: 'GUARDAR PERMISOS' })).toBeEnabled({ timeout: 5000 });
    await admin.unroute('**/permisos-ubicaciones');
    await admin.getByRole('button', { name: 'CANCELAR' }).click();
  });

  test('CA-07 retirar todo deja la consulta con el mensaje exacto', async ({ browser }) => {
    await abrirPermisos(admin, CF);
    for (const texto of ['Norte QA', 'Relaves QA']) {
      const marcadas = admin.locator('label', { hasText: texto }).locator('input:checked');
      while (await marcadas.count()) await marcadas.first().uncheck();
    }
    await admin.getByRole('button', { name: 'GUARDAR PERMISOS' }).click();
    await expect(admin.getByText('Permisos actualizados correctamente')).toBeVisible();
    const cf = await sesion(browser, CF);
    await cf.goto('/consulta-datos');
    await expect(cf.getByText('No tienes proyectos asignados. Contacta al administrador.')).toBeVisible();
    await cf.screenshot({ path: EV + 'EV-HU21-E2E-03_sin-proyectos.png' });
    await cf.context().close();
  });
});

test.describe.serial('Flujo empresarial: Mi empresa > Usuarios > Editar', () => {
  let admin;
  test.beforeAll(async ({ browser }) => { resembrar(); admin = await sesion(browser, 'admin-a@hu21.pangea-dev.com'); });
  test.afterAll(async () => { await admin.context().close(); });

  test('CA-02 muestra contexto, tipo de cuenta, proyectos con sede y estado y explica el alcance del rol', async () => {
    await verEmpresa(admin, ids.a);
    await expect(admin.getByRole('heading', { name: 'Usuarios de QA Andina' })).toBeVisible();
    const lector = tarjeta(admin, LECTOR2);
    await expect(lector).toContainText('Leo Lector');
    await expect(lector).toContainText(`${LECTOR2} · Lector · Activo · Usuario Empresa`);
    await lector.getByRole('button', { name: 'Editar' }).click();
    await expect(lector.locator('label', { hasText: 'Norte QA · Sede Lima · Activa' }).locator('input')).toBeChecked();
    await expect(lector.locator('label', { hasText: 'Norte QA · Sede Cusco · Activa' }).locator('input')).not.toBeChecked();
    await expect(lector.locator('label', { hasText: 'Antiguo QA · Sede Lima · Inactiva' }).locator('input')).toBeDisabled();
    await expect(lector).toContainText('Selecciona al menos un proyecto activo');
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-04_edicion-empresa.png' });
    await lector.getByLabel(/^Rol de/).selectOption('Tecnico');
    await expect(lector).toContainText('Este rol accede a todos los proyectos de QA Andina, incluidos los nuevos.');
    await lector.getByLabel(/^Rol de/).selectOption('Lector');
  });

  test('CA-04 Cancelar descarta y al reabrir se ve lo guardado', async () => {
    const lector = tarjeta(admin, LECTOR2);
    await lector.locator('label', { hasText: 'Sede Cusco' }).locator('input').check();
    await lector.getByRole('button', { name: 'Cancelar' }).click();
    await expect(lector.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0);
    await lector.getByRole('button', { name: 'Editar' }).click();
    await expect(lector.locator('label', { hasText: 'Sede Cusco' }).locator('input')).not.toBeChecked();
  });

  test('CA-07 Lector sin proyectos se rechaza con explicación y ofrece desactivar, sin llamar a la API', async () => {
    const lector = tarjeta(admin, LECTOR2);
    let peticiones = 0;
    admin.on('request', (r) => { if (r.method() === 'PATCH') peticiones += 1; });
    while (await lector.locator('label input:checked').count()) await lector.locator('label input:checked').first().uncheck();
    await lector.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(admin.getByRole('alert')).toContainText('Asigna al menos un proyecto activo al Lector o desactiva su membresía');
    await expect(lector.getByRole('button', { name: 'Desactivar' })).toBeVisible();
    expect(peticiones).toBe(0);
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-05_lector-sin-proyectos.png' });
  });

  test('CA-03 si la API rechaza se muestra el motivo y la selección sigue disponible', async () => {
    const lector = tarjeta(admin, LECTOR2);
    await lector.locator('label', { hasText: 'Sede Cusco' }).locator('input').check();
    await admin.route('**/empresas/*/usuarios/*', (r) => r.fulfill({ status: 409, contentType: 'application/json', json: { detail: 'No se pudo guardar el acceso. Vuelve a intentarlo' } }));
    await lector.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(admin.getByRole('alert')).toContainText('No se pudo guardar el acceso');
    await expect(lector.locator('label', { hasText: 'Sede Cusco' }).locator('input')).toBeChecked();
    await admin.unroute('**/empresas/*/usuarios/*');
  });

  test('CA-03 Guardar cambios confirma con el mensaje exacto y persiste', async () => {
    const lector = tarjeta(admin, LECTOR2);
    await lector.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(admin.getByText('Acceso actualizado correctamente')).toBeVisible();
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-06_acceso-actualizado.png' });
    await admin.reload();
    await expect(tarjeta(admin, LECTOR2)).toBeVisible();
    await tarjeta(admin, LECTOR2).getByRole('button', { name: 'Editar' }).click();
    await expect(tarjeta(admin, LECTOR2).locator('label', { hasText: 'Sede Cusco' }).locator('input')).toBeChecked();
    await tarjeta(admin, LECTOR2).getByRole('button', { name: 'Cancelar' }).click();
  });

  test('CA-07 el último Administrador activo no se puede desactivar ni pasar a Lector', async () => {
    const yo = tarjeta(admin, 'admin-a@hu21.pangea-dev.com');
    await yo.getByRole('button', { name: 'Desactivar' }).click();
    await expect(admin.getByRole('alert')).toContainText('No puedes dejar la empresa sin administrador');
    await yo.getByRole('button', { name: 'Editar' }).click();
    await yo.getByLabel(/^Rol de/).selectOption('Tecnico');
    await yo.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(admin.getByRole('alert')).toContainText('No puedes dejar la empresa sin administrador');
    await yo.getByRole('button', { name: 'Cancelar' }).click();
  });

  test('CA-07 desactivar y reactivar conserva los proyectos', async () => {
    const lector = tarjeta(admin, LECTOR2);
    await lector.getByRole('button', { name: 'Desactivar' }).click();
    await expect(tarjeta(admin, LECTOR2)).toContainText('Inactivo');
    await tarjeta(admin, LECTOR2).getByRole('button', { name: 'Activar' }).click();
    await expect(tarjeta(admin, LECTOR2)).toContainText('· Activo ·');
  });

  test('CA-01 el Administrador de empresa no ve Gestionar permisos ni el enlace a Usuarios de la cuenta anterior', async () => {
    await expect(tarjeta(admin, 'cf@hu21.pangea-dev.com')).toContainText('Cuenta anterior');
    await expect(tarjeta(admin, 'cf@hu21.pangea-dev.com').getByRole('link', { name: 'Ver en usuarios' })).toHaveCount(0);
    await expect(tarjeta(admin, 'cf@hu21.pangea-dev.com').getByRole('button', { name: 'Editar' })).toHaveCount(0);
  });
});

test.describe.serial('Roles sin gestión y alcance CENERIS', () => {
  test.beforeAll(() => resembrar());

  test('CA-01 Técnico de empresa no ve acciones de gestión', async ({ browser }) => {
    const tec = await sesion(browser, 'tec-a@hu21.pangea-dev.com');
    await tec.goto(`/empresas?cliente=${ids.a}`);
    await tec.waitForURL((u) => !u.pathname.startsWith('/empresas'));
    await expect(tec.getByRole('link', { name: 'Dispositivos' })).toBeVisible();
    await expect(tec.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0);
    await expect(tec.getByRole('button', { name: 'Desactivar' })).toHaveCount(0);
    await tec.goto('/usuarios');
    await tec.waitForURL((u) => !u.pathname.startsWith('/usuarios'));
    await tec.context().close();
  });

  test('CA-01 Lector no ve acciones de gestión y solo su proyecto', async ({ browser }) => {
    const lector = await sesion(browser, LECTOR);
    await lector.goto(`/empresas?cliente=${ids.a}`);
    await lector.waitForURL((u) => !u.pathname.startsWith('/empresas'));
    await lector.goto('/ubicaciones');
    await expect(lector.getByText('Norte QA').first()).toBeVisible();
    await expect(lector.getByText('Relaves QA')).toHaveCount(0);
    await expect(lector.getByRole('button', { name: 'Gestionar permisos' })).toHaveCount(0);
    await lector.context().close();
  });

  test('CA-01 Técnico CENERIS no ve Gestionar permisos ni edición de miembros', async ({ browser }) => {
    const tec = await sesion(browser, 'tecnico@pangea-dev.com');
    await tec.goto(`/empresas?cliente=${ids.a}`);
    await expect(tec.getByRole('heading', { name: /^Proyectos de/ })).toBeVisible();
    await expect(tec.getByRole('button', { name: 'Editar' })).toHaveCount(0);
    await expect(tec.getByRole('button', { name: 'Desactivar' })).toHaveCount(0);
    await tec.goto('/usuarios');
    await expect(tec.getByRole('button', { name: 'Gestionar permisos' })).toHaveCount(0);
    await tec.context().close();
  });

  test('CA-02 Administrador CENERIS ve la cuenta anterior identificada y, al cambiar de empresa, se cierra la edición', async ({ browser }) => {
    const admin = await sesion(browser, 'admin@pangea-dev.com');
    await verEmpresa(admin, ids.a);
    await expect(tarjeta(admin, 'cf@hu21.pangea-dev.com')).toContainText('Cuenta anterior');
    await expect(tarjeta(admin, 'cf@hu21.pangea-dev.com').getByRole('link', { name: 'Ver en usuarios' })).toBeVisible();
    await tarjeta(admin, LECTOR2).getByRole('button', { name: 'Editar' }).click();
    await expect(admin.getByRole('button', { name: 'Guardar cambios' })).toBeVisible();
    await admin.getByLabel('Empresa a gestionar').selectOption(String(ids.b));
    await expect(admin.getByRole('heading', { name: 'Usuarios de QA Sur' })).toBeVisible();
    await expect(admin.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0);
    await admin.screenshot({ path: EV + 'EV-HU21-E2E-07_cambio-empresa.png' });
    await admin.context().close();
  });
});

test.describe.serial('Revocación con sesión abierta', () => {
  test.beforeEach(() => resembrar());

  test('CA-06 Lector: al revocar, la interfaz descarta selección y resultados sin nuevo login', async ({ browser }) => {
    const admin = await sesion(browser, 'admin-a@hu21.pangea-dev.com');
    const lector = await sesion(browser, LECTOR2);
    await abrirConsulta(lector);
    await expect(lector.getByText('Relaves QA').first()).toBeVisible();
    const r = await patchMiembro(admin, ids.a, ids.m_lector2, { rol: 'Lector', estado: 'Activo', proyecto_ids: [ids.p1] });
    expect(r.ok()).toBeTruthy();
    await expect(lector.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
    await expect(lector).toHaveURL(/consulta-datos/);
    await expect(lector.getByText('Relaves QA')).toHaveCount(0);
    await lector.screenshot({ path: EV + 'EV-HU21-E2E-08_revocacion-sesion-abierta.png' });
    await admin.context().close(); await lector.context().close();
  });

  test('CA-06 Cliente Final: la revocación llega a la sesión abierta sin nuevo login', async ({ browser }) => {
    const admin = await sesion(browser, 'admin@pangea-dev.com');
    const cf = await sesion(browser, CF);
    await abrirConsulta(cf);
    await expect(cf.getByText('Norte QA').first()).toBeVisible();
    const r = await putAnterior(admin, ids.cf, [ids.p2]);
    expect(r.ok()).toBeTruthy();
    await expect(cf.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
    await expect(cf.getByText('Relaves QA').first()).toBeVisible();
    await expect(cf.getByText('Norte QA')).toHaveCount(0);
    await admin.context().close(); await cf.context().close();
  });

  test('CA-07 desactivar la membresía bloquea la sesión abierta', async ({ browser }) => {
    const admin = await sesion(browser, 'admin-a@hu21.pangea-dev.com');
    const lector = await sesion(browser, LECTOR);
    await abrirConsulta(lector);
    await expect(lector.getByText('Norte QA').first()).toBeVisible();
    const r = await patchMiembro(admin, ids.a, ids.m_lector, { rol: 'Lector', estado: 'Inactivo', proyecto_ids: [ids.p1] });
    expect(r.ok()).toBeTruthy();
    await expect(lector.getByRole('heading', { name: 'Tu acceso cambió' })).toBeVisible({ timeout: 25000 });
    await lector.screenshot({ path: EV + 'EV-HU21-E2E-09_membresia-desactivada.png' });
    await admin.context().close(); await lector.context().close();
  });

  test('CA-06 el mapa en vivo se recupera con el nuevo alcance tras la revocación', async ({ browser }) => {
    const admin = await sesion(browser, 'admin@pangea-dev.com');
    const cf = await sesion(browser, CF);
    await cf.goto('/mapa-estaciones');
    await expect(cf.getByText('En vivo')).toBeVisible({ timeout: 15000 });
    const r = await putAnterior(admin, ids.cf, [ids.p2]);
    expect(r.ok()).toBeTruthy();
    await expect(cf.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
    await admin.context().close(); await cf.context().close();
  });

  test('CA-05 un enlace directo a un dispositivo no autorizado no muestra sus datos', async ({ browser }) => {
    const cf = await sesion(browser, CF);
    await cf.goto(`/dispositivos/${ids.d2}`);
    await cf.waitForLoadState('networkidle');
    await expect(cf.getByText('Datalogger Relaves QA')).toHaveCount(0);
    await cf.screenshot({ path: EV + 'EV-HU21-E2E-10_enlace-directo.png' });
    await cf.goto(`/ubicaciones/${ids.p2}`);
    await cf.waitForLoadState('networkidle');
    await expect(cf.getByText('Relaves QA')).toHaveCount(0);
    await cf.context().close();
  });

  test('CA-05 un proyecto manipulado en la selección guardada no entrega datos de otro proyecto', async ({ browser }) => {
    const lector = await sesion(browser, LECTOR);
    await lector.goto('/consulta-datos');
    await lector.evaluate(([c, p]) => { sessionStorage.setItem('pangea_cliente', String(c)); sessionStorage.setItem('pangea_proyecto_v2', String(p)); }, [ids.a, ids.p2]);
    await lector.goto('/consulta-datos');
    await lector.waitForLoadState('networkidle');
    await expect(lector.getByText('Relaves QA')).toHaveCount(0);
    await lector.context().close();
  });
});

test.describe('Revocación durante la carga', () => {
  test.beforeEach(() => resembrar());

  test('CA-06 la revocación se detecta aunque ocurra antes de la primera lectura de acceso', async ({ browser }) => {
    const admin = await sesion(browser, 'admin@pangea-dev.com');
    const cf = await sesion(browser, CF);
    let primera = true;
    await cf.route('**/auth/acceso', async (ruta) => {
      if (primera) { primera = false; await new Promise((f) => setTimeout(f, 5000)); }
      await ruta.continue();
    });
    await cf.goto('/consulta-datos');
    await expect(cf.getByText('Norte QA').first()).toBeVisible();
    expect((await putAnterior(admin, ids.cf, [ids.p2])).ok()).toBeTruthy();
    await expect(cf.getByText('Norte QA').first()).toBeHidden({ timeout: 30000 }).catch(async (e) => {
      await cf.screenshot({ path: EV + 'EV-HU21-E2E-11_def-resultados-tras-revocar.png' });
      throw e;
    });
    await admin.context().close(); await cf.context().close();
  });
});
