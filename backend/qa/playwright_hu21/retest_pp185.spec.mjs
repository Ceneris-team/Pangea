// RG-38: peticiones reales; solo se retrasa /auth/acceso para controlar la carrera.
import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const ROOT = path.resolve(HERE, '../../..');
const EV = path.resolve(HERE, '../03_Evidencias/HU21/reprueba_pp185');
const API = 'http://localhost:8022';
let ids;
test.beforeEach(() => {
  const output = execFileSync(path.join(ROOT, 'backend/venv/Scripts/python.exe'), [path.join(HERE, 'run_retest_pp185.py'), '--seed'], {
    cwd: path.join(ROOT, 'backend'), env: { ...process.env, PYTHONPATH: '.' }, encoding: 'utf8',
  });
  ids = JSON.parse(output.trim().split('\n').pop());
});
async function login(browser, correo) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const t0 = Date.now();
  const traza = m => { if (process.env.PP185_TRAZA) console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s ${correo.split('@')[0]}] ${m}`); };
  page.on('response', r => { if (/\/auth\/(acceso|perfil)/.test(r.url())) traza(`${r.status()} ${new URL(r.url()).pathname}`); });
  page.on('requestfailed', r => { if (/\/auth\//.test(r.url())) traza(`FALLO ${new URL(r.url()).pathname} ${r.failure()?.errorText}`); });
  page.on('framenavigated', f => { if (f === page.mainFrame()) traza(`NAV ${f.url()}`); });
  // Redis 14 pertenece exclusivamente a esta reprueba.
  execFileSync('docker', ['exec', 'pangea-redis-1', 'redis-cli', '-n', '14', 'FLUSHDB']);
  const response = await context.request.post(API + '/auth/login', { data: { correo, contrasena: 'Pangea2026' } });
  expect(response.ok(), await response.text()).toBeTruthy();
  await page.goto('/consulta-datos');
  if (correo !== 'admin@pangea-dev.com') await expect(page.getByText('Norte QA').first()).toBeVisible();
  return page;
}
async function revoke(admin, tipo) {
  const inicio = Date.now();
  if (process.env.PP185_TRAZA) console.log('[revoke] inicio', tipo);
  const response = tipo === 'anterior'
    ? await admin.context().request.put(`${API}/usuarios/${ids.cf}/permisos-ubicaciones`, { data: { ubicacion_ids: [ids.p2] } })
    : await admin.context().request.patch(`${API}/empresas/${ids.a}/usuarios/${ids.m_lector2}`, { data: { rol: 'Lector', estado: 'Activo', proyecto_ids: [ids.p2] } });
  expect(response.ok(), await response.text()).toBeTruthy();
  if (process.env.PP185_TRAZA) console.log('[revoke] fin', response.status(), Date.now() - inicio, 'ms');
}
for (const tipo of ['anterior', 'empresa']) {
  test(`RG-38 ${tipo}: revocación antes de la primera respuesta, sin cargar datos retirados`, async ({ browser }) => {
    const admin = await login(browser, 'admin@pangea-dev.com');
    const page = await login(browser, tipo === 'anterior' ? 'cf@hu21.pangea-dev.com' : 'lector2@hu21.pangea-dev.com');
    // Las cuentas anteriores no eligen proyecto: su estado real es solo el filtro de la URL.
    if (tipo === 'empresa') await page.evaluate((p) => {
      sessionStorage.setItem('pangea_proyecto_v2', String(p));
      sessionStorage.setItem('pangea_proyecto', String(p));
    }, ids.p1);
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    let seen;
    const intercepted = new Promise(resolve => { seen = resolve; });
    let first = true;
    let dataRequests = 0;
    page.on('request', req => { if (/\/mediciones(?:\?|\/|$)/.test(req.url())) dataRequests++; });
    await page.route('**/auth/acceso', async route => {
      if (first) { first = false; seen(); await gate; }
      await route.continue();
    });
    try {
      await page.goto(`/consulta-datos?ubicacion_id=${ids.p1}`);
      await intercepted;
      await expect(page.getByText('Comprobando tus permisos…')).toBeVisible();
      expect(dataRequests).toBe(0);
      await revoke(admin, tipo);
    } finally { release(); }
    await expect(page.getByText('Tus permisos cambiaron.', { exact: false })).toBeVisible({ timeout: 25000 });
    await expect(page.getByText('Relaves QA').first()).toBeVisible();
    await expect(page.getByText('Norte QA')).toHaveCount(0);
    await expect(page).toHaveURL(/\/consulta-datos$/);
    const stored = await page.evaluate(() => ({ project: sessionStorage.getItem('pangea_proyecto_v2'), old: sessionStorage.getItem('pangea_proyecto'), access: JSON.parse(sessionStorage.getItem('pangea_acceso')) }));
    expect(stored.project).not.toBe(String(ids.p1));
    expect(stored.old).not.toBe(String(ids.p1));
    expect(stored.access.usuario).toBe(tipo === 'anterior' ? 'cf@hu21.pangea-dev.com' : 'lector2@hu21.pangea-dev.com');
    // Control directo: /mediciones cruza lo pedido con lo permitido, así que responde 200 sin el proyecto retirado.
    const rango = `fecha_inicio=${encodeURIComponent(new Date(Date.now() - 864e5).toISOString())}`;
    const retirado = await (await page.context().request.get(API + `/mediciones?ubicacion_ids=${ids.p1}&${rango}`)).text();
    const permitido = await (await page.context().request.get(API + `/mediciones?ubicacion_ids=${ids.p2}&${rango}`)).text();
    expect(retirado).not.toContain('Norte QA');
    expect(permitido).toContain('Relaves QA');
    await page.screenshot({ path: path.join(EV, `RG38-${tipo}.png`), fullPage: true });
    await page.context().close(); await admin.context().close();
  });
}
test('RG-38 versión por usuario detecta cambio al recargar sin selección guardada', async ({ browser }) => {
  const admin = await login(browser, 'admin@pangea-dev.com');
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  const previous = await page.evaluate(() => JSON.parse(sessionStorage.getItem('pangea_acceso')));
  expect(previous.usuario).toBe('cf@hu21.pangea-dev.com');
  await revoke(admin, 'anterior');
  await page.evaluate(() => { sessionStorage.removeItem('pangea_proyecto_v2'); sessionStorage.removeItem('pangea_proyecto'); });
  await page.reload();
  await expect(page.getByText('Tus permisos cambiaron.', { exact: false })).toBeVisible({ timeout: 25000 });
  const current = await page.evaluate(() => JSON.parse(sessionStorage.getItem('pangea_acceso')));
  expect(current.usuario).toBe(previous.usuario);
  expect(current.version).not.toBe(previous.version);
  await expect(page.getByText('Norte QA')).toHaveCount(0);
  await expect(page.getByText('Relaves QA').first()).toBeVisible();
  await page.screenshot({ path: path.join(EV, 'RG38-version-recarga.png'), fullPage: true });
  await page.context().close(); await admin.context().close();
});
test('RG-38 sesión abierta descarta resultados tras revocar sin nuevo login', async ({ browser }) => {
  const admin = await login(browser, 'admin@pangea-dev.com');
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await revoke(admin, 'anterior');
  await expect(page.getByText('Tus permisos cambiaron.', { exact: false })).toBeVisible({ timeout: 25000 });
  await expect(page.getByText('Norte QA')).toHaveCount(0);
  await expect(page.getByText('Relaves QA').first()).toBeVisible();
  await expect(page).toHaveURL(/consulta-datos/);
  await page.screenshot({ path: path.join(EV, 'RG38-sesion-abierta.png'), fullPage: true });
  await page.context().close(); await admin.context().close();
});
// Riesgos nuevos del commit 67a8309 sobre la interfaz.
test('RG-37 interfaz: el motivo de proyecto inactivo llega a pantalla y conserva la selección', async ({ browser }) => {
  const admin = await login(browser, 'admin@pangea-dev.com');
  await admin.goto(`/empresas?cliente=${ids.a}`);
  const tarjeta = admin.locator('div.rounded-xl', { hasText: 'lector2@hu21.pangea-dev.com' }).last();
  await tarjeta.getByRole('button', { name: 'Editar' }).click();
  await tarjeta.locator('label', { hasText: 'Sede Cusco' }).locator('input').check();
  // Solo se altera el envío: la API real rechaza el proyecto inactivo que la casilla no deja marcar.
  await admin.route('**/empresas/*/usuarios/*', async route => {
    if (route.request().method() !== 'PATCH') return route.continue();
    const cuerpo = route.request().postDataJSON();
    await route.continue({ postData: JSON.stringify({ ...cuerpo, proyecto_ids: [...cuerpo.proyecto_ids, ids.pi] }) });
  });
  await tarjeta.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(admin.getByRole('alert')).toContainText('Hay proyectos inactivos: Antiguo QA');
  await expect(admin.getByRole('alert')).not.toContainText('no pertenecen');
  await expect(tarjeta.locator('label', { hasText: 'Sede Cusco' }).locator('input')).toBeChecked();
  await admin.screenshot({ path: path.join(EV, 'RG37-motivo-en-pantalla.png'), fullPage: true });
  await admin.context().close();
});
test('DEF-12: un fallo de /auth/acceso muestra salida y se recupera al reintentar', async ({ browser }) => {
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  await page.route('**/auth/acceso', route => route.fulfill({ status: 500, contentType: 'application/json', json: { detail: 'Error' } }));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'No pudimos comprobar tus permisos' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible();
  await expect(page.getByText('Norte QA')).toHaveCount(0);
  await page.screenshot({ path: path.join(EV, 'DEF12-sin-verificar.png'), fullPage: true });
  await page.unroute('**/auth/acceso');
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.getByText('Norte QA').first()).toBeVisible();
});
test('DEF-12: el fallo de red también ofrece salida y el intervalo se recupera sin recargar', async ({ browser }) => {
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  await page.route('**/auth/acceso', route => route.abort());
  await page.reload();
  await expect(page.getByRole('heading', { name: 'No pudimos comprobar tus permisos' })).toBeVisible();
  await page.unroute('**/auth/acceso');
  await expect(page.getByText('Norte QA').first()).toBeVisible({ timeout: 25000 });
});
test('DEF-12: un fallo durante la sesión no expulsa de la pantalla ya validada', async ({ browser }) => {
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  await page.route('**/auth/acceso', route => route.fulfill({ status: 500, contentType: 'application/json', json: { detail: 'Error' } }));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await page.waitForTimeout(1000);
  await expect(page.getByRole('heading', { name: 'No pudimos comprobar tus permisos' })).toHaveCount(0);
  await expect(page.getByText('Norte QA').first()).toBeVisible();
});
test('DEF-13: un enlace nunca autorizado se limpia sin informar un cambio de permisos falso', async ({ browser }) => {
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  const version = await page.evaluate(() => JSON.parse(sessionStorage.getItem('pangea_acceso')).version);
  await page.goto(`/consulta-datos?ubicacion_id=${ids.pb}`);
  await expect(page.getByText('No tienes acceso al proyecto del enlace', { exact: false })).toBeVisible();
  await expect(page.getByText('Tus permisos cambiaron.', { exact: false })).toHaveCount(0);
  await expect(page.getByText('Tu acceso cambió')).toHaveCount(0);
  await expect(page).toHaveURL(/\/consulta-datos$/);
  await expect(page.getByText('Norte QA').first()).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('pangea_acceso')).version)).toBe(version);
  await page.screenshot({ path: path.join(EV, 'DEF13-aviso-enlace.png'), fullPage: true });
});
test('DEF-13: el Lector conserva su proyecto válido al abrir un enlace ajeno', async ({ browser }) => {
  const page = await login(browser, 'lector2@hu21.pangea-dev.com');
  await page.evaluate((p) => sessionStorage.setItem('pangea_proyecto_v2', String(p)), ids.p2);
  await page.goto(`/consulta-datos?ubicacion_id=${ids.p3}`);
  await expect(page.getByText('No tienes acceso al proyecto del enlace', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('pangea_proyecto_v2'))).toBe(String(ids.p2));
});
test('Riesgo: /graficos con proyecto retirado tampoco muestra datos', async ({ browser }) => {
  const admin = await login(browser, 'admin@pangea-dev.com');
  const page = await login(browser, 'cf@hu21.pangea-dev.com');
  const series = [];
  page.on('response', r => { if (r.url().includes('/mediciones/series')) series.push(r.status()); });
  await revoke(admin, 'anterior');
  await page.goto(`/graficos?ubicacion_id=${ids.p1}`);
  await page.waitForTimeout(3000);
  const texto = await page.locator('body').innerText();
  console.log('RIESGO_GRAFICOS:', JSON.stringify({ series, norte: texto.includes('Norte QA'), url: page.url() }));
  await page.screenshot({ path: path.join(EV, 'riesgo-graficos-revocado.png'), fullPage: true });
  expect(texto).not.toContain('Norte QA');
  expect(series.every(s => s !== 200)).toBeTruthy();
});
