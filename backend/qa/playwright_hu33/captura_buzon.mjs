// Captura de la bandeja de Mailpit con el correo de exportación recibido (PP-408, CP-220).
import { chromium } from '@playwright/test';
import path from 'node:path';
const dir = path.resolve('..', '03_Evidencias', 'HU33-HT15');
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1200, height: 760 }, deviceScaleFactor: 2 });
await page.goto('http://127.0.0.1:8025/');
await page.waitForSelector('a.message, .message');
await page.locator('.message').first().click();
await page.waitForTimeout(1200);
await page.screenshot({ path: path.join(dir, 'EV-HU33-E2E-06_buzon-correo-recibido.png') });
await browser.close();
