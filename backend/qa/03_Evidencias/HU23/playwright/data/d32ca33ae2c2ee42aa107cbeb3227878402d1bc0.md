# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: hu23.spec.mjs >> HU23 búsqueda con caracteres especiales >> CA3 el carácter % no debe actuar como comodín
- Location: hu23.spec.mjs:151:3

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 0
Received: 10
```

# Page snapshot

```yaml
- generic [active] [ref=f4e1]:
  - generic [ref=f4e4]:
    - complementary [ref=f4e5]:
      - link [ref=f4e7] [cursor=pointer]:
        - /url: /paneles
        - generic [ref=f4e8]:
          - text: Pangea
          - paragraph [ref=f4e9]: Entorno del cliente
      - navigation "Módulos del cliente" [ref=f4e10]:
        - generic [ref=f4e11]:
          - paragraph [ref=f4e12]: Operación
          - link "Tableros personalizables" [ref=f4e14] [cursor=pointer]:
            - /url: /paneles
        - generic [ref=f4e21]:
          - paragraph [ref=f4e22]: Datos
          - generic [ref=f4e23]:
            - link "Consulta de datos" [ref=f4e24] [cursor=pointer]:
              - /url: /consulta-datos
            - link "Gráficos" [ref=f4e28] [cursor=pointer]:
              - /url: /graficos
            - link "Mapa de lecturas" [ref=f4e32] [cursor=pointer]:
              - /url: /mapa-estaciones
            - link "Mapa de proyectos" [ref=f4e36] [cursor=pointer]:
              - /url: /ubicaciones/mapa
        - generic [ref=f4e40]:
          - paragraph [ref=f4e41]: Gestión
          - generic [ref=f4e42]:
            - link "Proyectos" [ref=f4e43] [cursor=pointer]:
              - /url: /ubicaciones
            - link "Dispositivos" [ref=f4e47] [cursor=pointer]:
              - /url: /dispositivos
      - button "Cerrar sesión" [ref=f4e52] [cursor=pointer]
    - generic [ref=f4e55]:
      - generic [ref=f4e57]:
        - button "Alternar modo oscuro" [ref=f4e58] [cursor=pointer]
        - generic [ref=f4e61]:
          - generic [ref=f4e62]:
            - generic [ref=f4e63]: Luis Cliente
            - generic [ref=f4e64]: Cliente Final
          - button "Abrir configuración de mi perfil" [ref=f4e65] [cursor=pointer]
      - main [ref=f4e66]:
        - generic [ref=f4e67]:
          - generic [ref=f4e68]:
            - heading "Tableros Personalizables" [level=1] [ref=f4e69]
            - paragraph [ref=f4e70]: Administra tu colección de paneles de visualización.
          - button "Crear panel" [ref=f4e72] [cursor=pointer]
        - generic [ref=f4e75]:
          - generic [ref=f4e76]: Panel eliminado correctamente
          - button "Cerrar" [ref=f4e77] [cursor=pointer]
        - generic [ref=f4e78]:
          - strong [ref=f4e79]: Vista general.
          - text: Aquí aparecen los paneles de los proyectos a los que tienes acceso.
        - generic [ref=f4e80]:
          - textbox "Buscar por nombre de panel..." [ref=f4e83]
          - table [ref=f4e85]:
            - rowgroup [ref=f4e86]:
              - row [ref=f4e87]:
                - columnheader "Nombre" [ref=f4e88]
                - columnheader "Proyectos del panel" [ref=f4e89]
                - columnheader "Fecha de creación" [ref=f4e90]
                - columnheader "Acciones" [ref=f4e91]
            - rowgroup [ref=f4e92]:
              - row [ref=f4e93]:
                - cell [ref=f4e94]:
                  - link "QA HU34 34963" [ref=f4e95] [cursor=pointer]:
                    - /url: /paneles/10
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e96]
                - cell "30/10/2026" [ref=f4e99]
                - cell [ref=f4e100]:
                  - generic [ref=f4e101]:
                    - link "Abrir" [ref=f4e102] [cursor=pointer]:
                      - /url: /paneles/10
                    - button "Duplicar" [ref=f4e103] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e104] [cursor=pointer]
                    - button "Editar" [ref=f4e105] [cursor=pointer]
                    - button "Eliminar" [ref=f4e106] [cursor=pointer]
              - row [ref=f4e107]:
                - cell [ref=f4e108]:
                  - link "QA HU34 33766" [ref=f4e109] [cursor=pointer]:
                    - /url: /paneles/9
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e110]
                - cell "30/10/2026" [ref=f4e113]
                - cell [ref=f4e114]:
                  - generic [ref=f4e115]:
                    - link "Abrir" [ref=f4e116] [cursor=pointer]:
                      - /url: /paneles/9
                    - button "Duplicar" [ref=f4e117] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e118] [cursor=pointer]
                    - button "Editar" [ref=f4e119] [cursor=pointer]
                    - button "Eliminar" [ref=f4e120] [cursor=pointer]
              - row [ref=f4e121]:
                - cell [ref=f4e122]:
                  - link "QA HU34 6922" [ref=f4e123] [cursor=pointer]:
                    - /url: /paneles/8
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e124]
                - cell "30/10/2026" [ref=f4e127]
                - cell [ref=f4e128]:
                  - generic [ref=f4e129]:
                    - link "Abrir" [ref=f4e130] [cursor=pointer]:
                      - /url: /paneles/8
                    - button "Duplicar" [ref=f4e131] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e132] [cursor=pointer]
                    - button "Editar" [ref=f4e133] [cursor=pointer]
                    - button "Eliminar" [ref=f4e134] [cursor=pointer]
              - row [ref=f4e135]:
                - cell [ref=f4e136]:
                  - link "QA HU34 26514" [ref=f4e137] [cursor=pointer]:
                    - /url: /paneles/7
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e138]
                - cell "30/10/2026" [ref=f4e141]
                - cell [ref=f4e142]:
                  - generic [ref=f4e143]:
                    - link "Abrir" [ref=f4e144] [cursor=pointer]:
                      - /url: /paneles/7
                    - button "Duplicar" [ref=f4e145] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e146] [cursor=pointer]
                    - button "Editar" [ref=f4e147] [cursor=pointer]
                    - button "Eliminar" [ref=f4e148] [cursor=pointer]
              - row [ref=f4e149]:
                - cell [ref=f4e150]:
                  - link "QA HU34 1107" [ref=f4e151] [cursor=pointer]:
                    - /url: /paneles/6
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e152]
                - cell "30/10/2026" [ref=f4e155]
                - cell [ref=f4e156]:
                  - generic [ref=f4e157]:
                    - link "Abrir" [ref=f4e158] [cursor=pointer]:
                      - /url: /paneles/6
                    - button "Duplicar" [ref=f4e159] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e160] [cursor=pointer]
                    - button "Editar" [ref=f4e161] [cursor=pointer]
                    - button "Eliminar" [ref=f4e162] [cursor=pointer]
              - row [ref=f4e163]:
                - cell [ref=f4e164]:
                  - link "QA HU26 41510" [ref=f4e165] [cursor=pointer]:
                    - /url: /paneles/5
                - cell "[DEMO] Planta de Tratamiento [DEMO] Río Rímac - Margen Izquierda" [ref=f4e166]:
                  - generic [ref=f4e167]:
                    - generic [ref=f4e168]: "[DEMO] Planta de Tratamiento"
                    - generic [ref=f4e169]: "[DEMO] Río Rímac - Margen Izquierda"
                - cell "30/10/2026" [ref=f4e170]
                - cell [ref=f4e171]:
                  - generic [ref=f4e172]:
                    - link "Abrir" [ref=f4e173] [cursor=pointer]:
                      - /url: /paneles/5
                    - button "Duplicar" [ref=f4e174] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e175] [cursor=pointer]
                    - button "Editar" [ref=f4e176] [cursor=pointer]
                    - button "Eliminar" [ref=f4e177] [cursor=pointer]
              - row [ref=f4e178]:
                - cell [ref=f4e179]:
                  - link "QA HU26 70463" [ref=f4e180] [cursor=pointer]:
                    - /url: /paneles/4
                - cell "[DEMO] Planta de Tratamiento [DEMO] Río Rímac - Margen Izquierda" [ref=f4e181]:
                  - generic [ref=f4e182]:
                    - generic [ref=f4e183]: "[DEMO] Planta de Tratamiento"
                    - generic [ref=f4e184]: "[DEMO] Río Rímac - Margen Izquierda"
                - cell "30/10/2026" [ref=f4e185]
                - cell [ref=f4e186]:
                  - generic [ref=f4e187]:
                    - link "Abrir" [ref=f4e188] [cursor=pointer]:
                      - /url: /paneles/4
                    - button "Duplicar" [ref=f4e189] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e190] [cursor=pointer]
                    - button "Editar" [ref=f4e191] [cursor=pointer]
                    - button "Eliminar" [ref=f4e192] [cursor=pointer]
              - row [ref=f4e193]:
                - cell [ref=f4e194]:
                  - link "QA HU26 50691" [ref=f4e195] [cursor=pointer]:
                    - /url: /paneles/3
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e196]
                - cell "30/10/2026" [ref=f4e199]
                - cell [ref=f4e200]:
                  - generic [ref=f4e201]:
                    - link "Abrir" [ref=f4e202] [cursor=pointer]:
                      - /url: /paneles/3
                    - button "Duplicar" [ref=f4e203] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e204] [cursor=pointer]
                    - button "Editar" [ref=f4e205] [cursor=pointer]
                    - button "Eliminar" [ref=f4e206] [cursor=pointer]
              - row [ref=f4e207]:
                - cell [ref=f4e208]:
                  - link "QA HU26 27110" [ref=f4e209] [cursor=pointer]:
                    - /url: /paneles/2
                - cell "[DEMO] Río Rímac - Margen Izquierda" [ref=f4e210]
                - cell "30/10/2026" [ref=f4e213]
                - cell [ref=f4e214]:
                  - generic [ref=f4e215]:
                    - link "Abrir" [ref=f4e216] [cursor=pointer]:
                      - /url: /paneles/2
                    - button "Duplicar" [ref=f4e217] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e218] [cursor=pointer]
                    - button "Editar" [ref=f4e219] [cursor=pointer]
                    - button "Eliminar" [ref=f4e220] [cursor=pointer]
              - row [ref=f4e221]:
                - cell [ref=f4e222]:
                  - link "QA HU26 94171" [ref=f4e223] [cursor=pointer]:
                    - /url: /paneles/1
                - cell "Sin proyecto asignado" [ref=f4e224]
                - cell "30/10/2026" [ref=f4e225]
                - cell [ref=f4e226]:
                  - generic [ref=f4e227]:
                    - link "Abrir" [ref=f4e228] [cursor=pointer]:
                      - /url: /paneles/1
                    - button "Duplicar" [ref=f4e229] [cursor=pointer]
                    - button "Compartir con empresa" [ref=f4e230] [cursor=pointer]
                    - button "Editar" [ref=f4e231] [cursor=pointer]
                    - button "Eliminar" [ref=f4e232] [cursor=pointer]
  - dialog [aria-hidden] [ref=f4e233]:
    - generic [ref=f4e234]:
      - heading [level=2] [ref=f4e235]: Mi perfil
      - button [ref=f4e236] [cursor=pointer]
  - dialog [aria-hidden] [ref=f4e240]:
    - generic [ref=f4e241]:
      - heading [level=2] [ref=f4e242]: Crear panel
      - button [ref=f4e243] [cursor=pointer]
    - generic [ref=f4e247]:
      - paragraph [ref=f4e248]: Dale un nombre a tu nuevo tablero personalizado.
      - paragraph [ref=f4e249]: Se creará sin un proyecto inicial. Después podrás añadir uno o varios proyectos.
      - generic [ref=f4e250]:
        - generic [ref=f4e251]: Nombre del panel *
        - textbox [ref=f4e252]:
          - /placeholder: Resumen de estaciones
        - paragraph [ref=f4e253]: Solo letras, números y espacios · 0/100
      - generic [ref=f4e254]:
        - button [ref=f4e255] [cursor=pointer]: Cancelar
        - button [ref=f4e256] [cursor=pointer]: Guardar
```

# Test source

```ts
  57  |   test('CA3 búsqueda por fragmento filtra el listado, sin distinguir mayúsculas', async () => {
  58  |     const buscar = page.getByPlaceholder('Buscar por nombre de panel...');
  59  |     await buscar.fill('hu26');
  60  |     await expect.poll(async () => (await nombresVisibles(page)).length).toBe(5);
  61  |     expect((await nombresVisibles(page)).every((n) => n.includes('HU26'))).toBe(true);
  62  |     await page.waitForTimeout(500);
  63  |     await page.screenshot({ path: EV + 'EV-HU23-E2E-02_busqueda.png' });
  64  |     await buscar.fill('QA HU34 1107');
  65  |     await expect.poll(async () => nombresVisibles(page)).toEqual(['QA HU34 1107']);
  66  |   });
  67  | 
  68  |   test('CA3 búsqueda sin coincidencias muestra el aviso de sin resultados', async () => {
  69  |     await page.getByPlaceholder('Buscar por nombre de panel...').fill('zzz-no-existe');
  70  |     await expect(page.getByText('No se encontraron paneles con ese criterio.')).toBeVisible();
  71  |     await expect(page.getByText('Aún no tienes paneles creados')).toHaveCount(0);
  72  |     await page.waitForTimeout(400);
  73  |     await page.screenshot({ path: EV + 'EV-HU23-E2E-03_busqueda-sin-resultados.png' });
  74  |   });
  75  | 
  76  |   test('CA3 borrar la búsqueda restituye el listado completo', async () => {
  77  |     await page.getByPlaceholder('Buscar por nombre de panel...').fill('');
  78  |     await expect.poll(async () => (await nombresVisibles(page)).length).toBeGreaterThanOrEqual(10);
  79  |   });
  80  | 
  81  |   test('CA2 panel con ubicación y widget: sale primero en el listado y su nombre lo abre con su contenido', async () => {
  82  |     await page.getByRole('button', { name: 'Crear panel' }).first().click();
  83  |     await page.getByPlaceholder('Resumen de estaciones').fill(NUEVO);
  84  |     await page.getByRole('button', { name: 'Guardar', exact: true }).click();
  85  |     await page.waitForURL(/\/paneles\/\d+/);
  86  |     await page.getByRole('button', { name: '+ Añadir ubicaciones' }).first().click();
  87  |     await page.locator('label:has(input[type=checkbox])', { hasText: U1 }).locator('input').check();
  88  |     await page.getByRole('button', { name: /^Agregar al panel/ }).click();
  89  |     await expect(page.getByRole('status')).toContainText('Ubicaciones añadidas correctamente');
  90  |     await page.getByRole('button', { name: '+ Añadir widget' }).click();
  91  |     await page.getByLabel('Tipo de widget').selectOption('tarjeta');
  92  |     const parametro = page.locator('select', { has: page.locator('option', { hasText: 'Selecciona un parámetro' }) });
  93  |     await expect.poll(async () => (await parametro.locator('option').count())).toBeGreaterThan(1);
  94  |     await parametro.selectOption({ index: 1 });
  95  |     await page.getByRole('button', { name: 'Guardar widget' }).click();
  96  |     await expect(page.getByRole('status')).toContainText('Widget creado correctamente');
  97  | 
  98  |     await page.goto('/paneles');
  99  |     await expect(filas(page).first().locator('td:first-child a')).toHaveText(NUEVO);
  100 |     await expect(filas(page).first().locator('td:nth-child(2)')).toContainText(U1);
  101 |     await page.waitForTimeout(500);
  102 |     await page.screenshot({ path: EV + 'EV-HU23-E2E-04_panel-nuevo-primero.png' });
  103 | 
  104 |     await filas(page).first().locator('td:first-child a').click();
  105 |     await page.waitForURL(/\/paneles\/\d+/);
  106 |     await expect(page.getByRole('heading', { name: NUEVO })).toBeVisible();
  107 |     await expect(page.getByText(U1).locator('visible=true').first()).toBeVisible();
  108 |     await expect(page.getByRole('heading', { name: /^Widgets \(1\)/ })).toBeVisible();
  109 |     await page.waitForTimeout(900);
  110 |     await page.screenshot({ path: EV + 'EV-HU23-E2E-05_panel-abierto.png' });
  111 |   });
  112 | 
  113 |   test('CA2 el botón Abrir lleva al mismo panel que el nombre', async () => {
  114 |     await page.goto('/paneles');
  115 |     const id = await filas(page).first().getByRole('link', { name: 'Abrir' }).getAttribute('href');
  116 |     const idNombre = await filas(page).first().locator('td:first-child a').getAttribute('href');
  117 |     expect(id).toBe(idNombre);
  118 |   });
  119 | 
  120 |   test('Limpieza: elimina el panel creado en la prueba', async () => {
  121 |     await page.goto('/paneles');
  122 |     await filas(page).first().getByRole('button', { name: 'Eliminar' }).click();
  123 |     await page.getByRole('button', { name: 'Confirmar' }).click();
  124 |     await expect(page.getByText(NUEVO)).toHaveCount(0, { timeout: 8000 });
  125 |   });
  126 | });
  127 | 
  128 | test.describe('HU23 usuario sin paneles', () => {
  129 |   test('Detalle: muestra «Aún no tienes paneles creados» y «Crear panel» visible y habilitado', async ({ browser }) => {
  130 |     const p = await entrar(browser, 'qa.sinpaneles@pangea-dev.com');
  131 |     await expect(p.getByText('Aún no tienes paneles creados')).toBeVisible();
  132 |     const botones = p.getByRole('button', { name: 'Crear panel' });
  133 |     expect(await botones.count()).toBeGreaterThanOrEqual(1);
  134 |     for (let i = 0; i < await botones.count(); i++) { await expect(botones.nth(i)).toBeVisible(); await expect(botones.nth(i)).toBeEnabled(); }
  135 |     await expect(p.getByText('QA Panel ajeno')).toHaveCount(0);
  136 |     await p.waitForTimeout(500);
  137 |     await p.screenshot({ path: EV + 'EV-HU23-E2E-06_sin-paneles.png' });
  138 |     await botones.last().click();
  139 |     await expect(p.getByPlaceholder('Resumen de estaciones')).toBeVisible();
  140 |   });
  141 | });
  142 | 
  143 | test.describe('HU23 otro usuario', () => {
  144 |   test('Detalle: el otro usuario ve solo su panel y no los del Cliente Final', async ({ browser }) => {
  145 |     const p = await entrar(browser, 'qa.otro@pangea-dev.com');
  146 |     await expect.poll(async () => nombresVisibles(p)).toEqual(['QA Panel ajeno']);
  147 |   });
  148 | });
  149 | 
  150 | test.describe('HU23 búsqueda con caracteres especiales', () => {
  151 |   test('CA3 el carácter % no debe actuar como comodín', async ({ browser }) => {
  152 |     const p = await entrar(browser, 'cliente@pangea-dev.com');
  153 |     await expect.poll(async () => (await nombresVisibles(p)).length).toBeGreaterThanOrEqual(10);
  154 |     await p.getByPlaceholder('Buscar por nombre de panel...').fill('%');
  155 |     await p.waitForTimeout(1200); // debounce de 400 ms + respuesta de la API
  156 |     await p.screenshot({ path: EV + 'EV-HU23-E2E-07_busqueda-porcentaje.png' });
> 157 |     expect(await filas(p).count()).toBe(0);
      |                                    ^ Error: expect(received).toBe(expected) // Object.is equality
  158 |   });
  159 | });
  160 | 
```