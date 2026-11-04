# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: hu21.spec.mjs >> Revocación durante la carga >> CA-06 la revocación se detecta aunque ocurra antes de la primera lectura de acceso
- Location: hu21.spec.mjs:385:3

# Error details

```
Error: expect(locator).toBeHidden() failed

Locator:  getByText('Norte QA').first()
Expected: hidden
Received: visible
Timeout:  30000ms

Call log:
  - Expect "toBeHidden" getByText('Norte QA').first() with timeout 30000ms
  - waiting for getByText('Norte QA').first()
    62 × locator resolved to <td class="px-6 py-4">Norte QA</td>
       - unexpected value "visible"

```

```yaml
- cell "Norte QA"
```

# Test source

```ts
  296 |     await tarjeta(admin, LECTOR2).getByRole('button', { name: 'Editar' }).click();
  297 |     await expect(admin.getByRole('button', { name: 'Guardar cambios' })).toBeVisible();
  298 |     await admin.getByLabel('Empresa a gestionar').selectOption(String(ids.b));
  299 |     await expect(admin.getByRole('heading', { name: 'Usuarios de QA Sur' })).toBeVisible();
  300 |     await expect(admin.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0);
  301 |     await admin.screenshot({ path: EV + 'EV-HU21-E2E-07_cambio-empresa.png' });
  302 |     await admin.context().close();
  303 |   });
  304 | });
  305 | 
  306 | test.describe.serial('Revocación con sesión abierta', () => {
  307 |   test.beforeEach(() => resembrar());
  308 | 
  309 |   test('CA-06 Lector: al revocar, la interfaz descarta selección y resultados sin nuevo login', async ({ browser }) => {
  310 |     const admin = await sesion(browser, 'admin-a@hu21.pangea-dev.com');
  311 |     const lector = await sesion(browser, LECTOR2);
  312 |     await abrirConsulta(lector);
  313 |     await expect(lector.getByText('Relaves QA').first()).toBeVisible();
  314 |     const r = await patchMiembro(admin, ids.a, ids.m_lector2, { rol: 'Lector', estado: 'Activo', proyecto_ids: [ids.p1] });
  315 |     expect(r.ok()).toBeTruthy();
  316 |     await expect(lector.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
  317 |     await expect(lector).toHaveURL(/consulta-datos/);
  318 |     await expect(lector.getByText('Relaves QA')).toHaveCount(0);
  319 |     await lector.screenshot({ path: EV + 'EV-HU21-E2E-08_revocacion-sesion-abierta.png' });
  320 |     await admin.context().close(); await lector.context().close();
  321 |   });
  322 | 
  323 |   test('CA-06 Cliente Final: la revocación llega a la sesión abierta sin nuevo login', async ({ browser }) => {
  324 |     const admin = await sesion(browser, 'admin@pangea-dev.com');
  325 |     const cf = await sesion(browser, CF);
  326 |     await abrirConsulta(cf);
  327 |     await expect(cf.getByText('Norte QA').first()).toBeVisible();
  328 |     const r = await putAnterior(admin, ids.cf, [ids.p2]);
  329 |     expect(r.ok()).toBeTruthy();
  330 |     await expect(cf.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
  331 |     await expect(cf.getByText('Relaves QA').first()).toBeVisible();
  332 |     await expect(cf.getByText('Norte QA')).toHaveCount(0);
  333 |     await admin.context().close(); await cf.context().close();
  334 |   });
  335 | 
  336 |   test('CA-07 desactivar la membresía bloquea la sesión abierta', async ({ browser }) => {
  337 |     const admin = await sesion(browser, 'admin-a@hu21.pangea-dev.com');
  338 |     const lector = await sesion(browser, LECTOR);
  339 |     await abrirConsulta(lector);
  340 |     await expect(lector.getByText('Norte QA').first()).toBeVisible();
  341 |     const r = await patchMiembro(admin, ids.a, ids.m_lector, { rol: 'Lector', estado: 'Inactivo', proyecto_ids: [ids.p1] });
  342 |     expect(r.ok()).toBeTruthy();
  343 |     await expect(lector.getByRole('heading', { name: 'Tu acceso cambió' })).toBeVisible({ timeout: 25000 });
  344 |     await lector.screenshot({ path: EV + 'EV-HU21-E2E-09_membresia-desactivada.png' });
  345 |     await admin.context().close(); await lector.context().close();
  346 |   });
  347 | 
  348 |   test('CA-06 el mapa en vivo se recupera con el nuevo alcance tras la revocación', async ({ browser }) => {
  349 |     const admin = await sesion(browser, 'admin@pangea-dev.com');
  350 |     const cf = await sesion(browser, CF);
  351 |     await cf.goto('/mapa-estaciones');
  352 |     await expect(cf.getByText('En vivo')).toBeVisible({ timeout: 15000 });
  353 |     const r = await putAnterior(admin, ids.cf, [ids.p2]);
  354 |     expect(r.ok()).toBeTruthy();
  355 |     await expect(cf.getByText('Tus permisos cambiaron')).toBeVisible({ timeout: 25000 });
  356 |     await admin.context().close(); await cf.context().close();
  357 |   });
  358 | 
  359 |   test('CA-05 un enlace directo a un dispositivo no autorizado no muestra sus datos', async ({ browser }) => {
  360 |     const cf = await sesion(browser, CF);
  361 |     await cf.goto(`/dispositivos/${ids.d2}`);
  362 |     await cf.waitForLoadState('networkidle');
  363 |     await expect(cf.getByText('Datalogger Relaves QA')).toHaveCount(0);
  364 |     await cf.screenshot({ path: EV + 'EV-HU21-E2E-10_enlace-directo.png' });
  365 |     await cf.goto(`/ubicaciones/${ids.p2}`);
  366 |     await cf.waitForLoadState('networkidle');
  367 |     await expect(cf.getByText('Relaves QA')).toHaveCount(0);
  368 |     await cf.context().close();
  369 |   });
  370 | 
  371 |   test('CA-05 un proyecto manipulado en la selección guardada no entrega datos de otro proyecto', async ({ browser }) => {
  372 |     const lector = await sesion(browser, LECTOR);
  373 |     await lector.goto('/consulta-datos');
  374 |     await lector.evaluate(([c, p]) => { sessionStorage.setItem('pangea_cliente', String(c)); sessionStorage.setItem('pangea_proyecto_v2', String(p)); }, [ids.a, ids.p2]);
  375 |     await lector.goto('/consulta-datos');
  376 |     await lector.waitForLoadState('networkidle');
  377 |     await expect(lector.getByText('Relaves QA')).toHaveCount(0);
  378 |     await lector.context().close();
  379 |   });
  380 | });
  381 | 
  382 | test.describe('Revocación durante la carga', () => {
  383 |   test.beforeEach(() => resembrar());
  384 | 
  385 |   test('CA-06 la revocación se detecta aunque ocurra antes de la primera lectura de acceso', async ({ browser }) => {
  386 |     const admin = await sesion(browser, 'admin@pangea-dev.com');
  387 |     const cf = await sesion(browser, CF);
  388 |     let primera = true;
  389 |     await cf.route('**/auth/acceso', async (ruta) => {
  390 |       if (primera) { primera = false; await new Promise((f) => setTimeout(f, 5000)); }
  391 |       await ruta.continue();
  392 |     });
  393 |     await cf.goto('/consulta-datos');
  394 |     await expect(cf.getByText('Norte QA').first()).toBeVisible();
  395 |     expect((await putAnterior(admin, ids.cf, [ids.p2])).ok()).toBeTruthy();
> 396 |     await expect(cf.getByText('Norte QA').first()).toBeHidden({ timeout: 30000 }).catch(async (e) => {
      |                                                    ^ Error: expect(locator).toBeHidden() failed
  397 |       await cf.screenshot({ path: EV + 'EV-HU21-E2E-11_def-resultados-tras-revocar.png' });
  398 |       throw e;
  399 |     });
  400 |     await admin.context().close(); await cf.context().close();
  401 |   });
  402 | });
  403 | 
```