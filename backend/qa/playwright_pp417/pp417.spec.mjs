import {test,expect} from '@playwright/test';
const sesiones = new Map();
async function abrir(page,correo='listado@pp417.pangea-dev.com'){
 if(sesiones.has(correo)){
   const s=sesiones.get(correo);
   await page.context().addCookies(s.cookies);
   await page.addInitScript(origins=>{for(const o of origins)if(o.origin===location.origin)for(const v of o.localStorage)localStorage.setItem(v.name,v.value);},s.origins);
 } else {
 await page.goto('/login');
 await page.getByPlaceholder('Ingresa tu correo').fill(correo);
 await page.getByPlaceholder('Ingresa tu contraseña').fill('QaLocal417!2026');
 await page.locator('button.submit').click();
 await page.waitForURL(u=>!u.pathname.includes('login'));
 sesiones.set(correo,await page.context().storageState());
 }
 await page.goto('/alarmas');
 await expect(page.getByRole('heading',{name:'Gestión de Alarmas y Notificaciones'})).toBeVisible();
 await expect(page.getByText('Cargando datos...')).toHaveCount(0);
}
test('CA1 tabla con columnas y 10 alarmas propias',async({page})=>{
 await abrir(page);
 for(const n of ['Nombre','Parámetro','Condición','Estado','Acciones']) await expect(page.getByRole('columnheader',{name:n,exact:true})).toBeVisible();
 await expect(page.locator('tbody tr')).toHaveCount(10);
 await expect(page.getByText('Alarma ajena')).toHaveCount(0);
 await expect(page.getByText('Nivel PP417',{exact:true}).first()).toBeVisible();
 await expect(page.getByText('> 3.5 m',{exact:true}).first()).toBeVisible();
 await page.screenshot({path:'../03_Evidencias/HU-27/listado.png'});
});
test('CA2 filtro Activa e Inactiva y limpiar',async({page})=>{
 await abrir(page);
 await page.locator('select').selectOption('Activa');
 await expect(page.locator('tbody tr')).toHaveCount(7);
 await expect(page.locator('tbody tr').filter({hasText:'Inactiva'})).toHaveCount(0);
 await page.locator('select').selectOption('Inactiva');
 await expect(page.locator('tbody tr')).toHaveCount(6);
 await expect(page.locator('tbody tr').filter({hasText:'Inactiva'})).toHaveCount(6);
 await page.getByRole('button',{name:'Limpiar filtros'}).click();
 await expect(page.locator('tbody tr')).toHaveCount(10);
});
test('CA3 búsqueda parcial y combinada',async({page})=>{
 await abrir(page);
 await page.getByPlaceholder('Buscar por nombre...').fill('NIVEL 1');
 await expect(page.locator('tbody tr')).toHaveCount(3);
 await page.locator('select').selectOption('Inactiva');
 await expect(page.locator('tbody tr')).toHaveCount(1);
 await expect(page.getByRole('cell',{name:'Nivel 11',exact:true})).toBeVisible();
});
test('paginación y reinicio al filtrar',async({page})=>{
 await abrir(page);
 await page.getByRole('button',{name:'Siguiente',exact:true}).click();
 await expect(page.locator('tbody tr')).toHaveCount(3);
 await page.locator('select').selectOption('Activa');
 await expect(page.locator('tbody tr')).toHaveCount(7);
 await expect(page.getByRole('button',{name:'Anterior',exact:true})).toBeDisabled();
});
test('sin coincidencias conserva Crear alarma',async({page})=>{
 await abrir(page);
 await page.getByPlaceholder('Buscar por nombre...').fill('inexistente');
 await expect(page.getByText('No se encontraron alarmas con ese criterio.')).toBeVisible();
 await expect(page.getByRole('button',{name:'Crear alarma',exact:true})).toBeEnabled();
});
test('usuario sin alarmas: mensaje y Crear alarma habilitado',async({page})=>{
 await abrir(page,'vacio@pp417.pangea-dev.com');
 await expect(page.getByText('Aún no tienes alarmas configuradas.')).toBeVisible();
 const crear=page.getByRole('button',{name:'Crear alarma',exact:true});
 await expect(crear).toBeEnabled();
 await page.screenshot({path:'../03_Evidencias/HU-27/sin-alarmas.png'});
 await crear.click();
 await expect(page).toHaveURL(/alarmas\/nueva/);
});

