import {chromium} from '@playwright/test';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const dir=path.resolve('../03_Evidencias/HU-27');
const browser=await chromium.launch({channel:'msedge'});
for(const [file,out,pw] of [['pytest_hu27.html','pytest.png',false],['playwright/index.html','playwright.png',true]]){
 const page=await browser.newPage({viewport:{width:pw?1000:900,height:900},deviceScaleFactor:2});
 await page.goto(pathToFileURL(path.join(dir,file)).href);
 if(pw){await page.waitForSelector('.test-file-test'); const bottom=await page.locator('.test-file-test').last().evaluate(e=>e.getBoundingClientRect().bottom+window.scrollY); await page.screenshot({path:path.join(dir,out),clip:{x:0,y:0,width:1000,height:Math.ceil(bottom)+10}});}
 else {await page.waitForSelector('#results-table tbody'); await page.addStyleTag({content:'#environment,#environment-header{display:none!important}'});await page.evaluate(()=>{for(const p of document.querySelectorAll('p'))if(p.textContent.startsWith('(Un)check'))p.style.display='none';});const b=await page.locator('#results-table tbody.results-table-row').nth(9).evaluate(e=>e.getBoundingClientRect().bottom+window.scrollY);await page.screenshot({path:path.join(dir,out),clip:{x:0,y:0,width:900,height:Math.ceil(b)+5}});}
 await page.close();
}
await browser.close();
