// QA HU28 - DEF-01: abrir el modulo Alarmas no debe romper la pantalla (prerrequisito de CA1).
import { test, expect } from '@playwright/test';
const EV = process.env.EV_DIR || '../03_Evidencias/HU28/';

test('CA1 prerrequisito: el modulo Alarmas y el formulario cargan sin errores de JavaScript', async ({ page }) => {
  const errores = [];
  page.on('pageerror', (e) => errores.push(e.message));
  await page.goto('/');
  await page.getByPlaceholder('Ingresa tu correo').fill('cliente@pangea-dev.com');
  await page.getByPlaceholder('Ingresa tu contraseña').fill('Pangea2026');
  await page.locator('button.submit').click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
  await page.getByRole('link', { name: 'Alarmas' }).first().click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: EV + 'EV-HU28-DEF01_pantalla-en-blanco-alarmas.png' });
  expect(errores, 'errores de JavaScript: ' + errores.join(' | ')).toEqual([]);
  await expect(page.getByText('Crear alarma').first()).toBeVisible({ timeout: 5000 });
});
