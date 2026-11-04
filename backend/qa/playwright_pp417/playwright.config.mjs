import {defineConfig} from '@playwright/test';
export default defineConfig({testMatch:'pp417.spec.mjs',workers:1,timeout:45000,reporter:[['list'],['html',{outputFolder:'../03_Evidencias/HU-27/playwright',open:'never'}]],use:{baseURL:'http://127.0.0.1:5173',channel:'msedge',viewport:{width:1400,height:900},screenshot:'only-on-failure'}});
