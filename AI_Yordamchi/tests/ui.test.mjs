import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const base=path.resolve(import.meta.dirname,'..');
let browser;
test.before(async()=>{browser=await chromium.launch({executablePath:process.env.AIY_CHROMIUM||chromium.executablePath(),args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'],headless:true});});
test.after(async()=>{await browser?.close();});
async function panel({width=1280,state=null,context=null}={}){
  const p=context?await context.newPage():await browser.newPage({viewport:{width,height:960}});
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.route('https://aiy.test/**',r=>{
    const name=new URL(r.request().url()).pathname.slice(1)||'panel.html';
    const file=path.join(base,name);
    if(!fs.existsSync(file))return r.fulfill({status:404,body:'Not found'});
    return r.fulfill({contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file)});
  });
  await p.addInitScript(({state})=>{
    window.writes=[];
    window.chrome={storage:{local:{get:async()=>state?{state}:{},set:async v=>window.writes.push(v)}},
      tabs:{query:async()=>[],create:async x=>{window.opened=x;return {id:1};},update:async()=>{}},
      scripting:{executeScript:async()=>{}}};
  },{state});
  await p.goto('https://aiy.test/panel.html');
  await p.waitForFunction(()=>document.querySelectorAll('.account').length===6||document.querySelector('#notice')?.textContent.includes('boshqa oynada'));
  return {p,errors};
}
test('dashboard loads, settings save and account buttons operate',async()=>{
  const {p,errors}=await panel();assert.equal(await p.locator('.account').count(),6);
  assert.equal(await p.locator('#start').isEnabled(),true);
  await p.locator('#rules').fill('Business rules test');await p.locator('#save').click();
  await p.waitForFunction(()=>window.writes.at(-1)?.settings.rules==='Business rules test');
  await p.locator('.account').first().getByRole('button',{name:'Ochish'}).click();
  assert.equal(await p.evaluate(()=>window.opened.url),'https://www.instagram.com/direct/inbox/');
  assert.deepEqual(errors,[]);
  if(process.env.AIY_SCREENSHOT)await p.screenshot({path:process.env.AIY_SCREENSHOT,fullPage:true});
  await p.close();
});
test('mobile layout avoids horizontal overflow',async()=>{
  const {p,errors}=await panel({width:390});
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);await p.close();
});
test('customer HTML is displayed as literal text',async()=>{
  const job={id:'e1',key:'instagram:a',platform:'instagram',url:'https://www.instagram.com/direct/t/a/',
    title:'<img src=x onerror=alert(1)>',incoming:'<script>window.hacked=true</script>',reply:'Safe reply',status:'ready',created:1};
  const {p,errors}=await panel({state:{seen:{},jobs:{e1:job},logs:[],pinned:{}}});
  assert.equal(await p.locator('.job img').count(),0);assert.equal(await p.locator('.job script').count(),0);
  assert.match(await p.locator('.incoming').innerText(),/<script>/);assert.deepEqual(errors,[]);await p.close();
});
test('second dashboard cannot mutate shared state',async()=>{
  const context=await browser.newContext();const first=await panel({context});const second=await panel({context});
  assert.match(await second.p.locator('#notice').innerText(),/boshqa oynada/);
  assert.equal(await second.p.locator('#start').isEnabled(),false);
  assert.equal(await second.p.evaluate(()=>window.writes.length),0);await context.close();
});
