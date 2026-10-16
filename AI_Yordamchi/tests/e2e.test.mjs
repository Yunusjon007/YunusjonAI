// Loads the real extension into Chromium and serves look-alike Instagram,
// Telegram and ChatGPT pages from a local HTTPS server. No real accounts.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import https from 'node:https';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const base=path.resolve(import.meta.dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'aiy-e2e-'));
let openssl=true;
try {execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',tmp+'/key.pem','-out',tmp+'/cert.pem','-days','2','-subj','/CN=localhost'],{stdio:'ignore'});}
catch {openssl=false;}

const instagram=`<!doctype html><html><head><title>Instagram</title><style>body{margin:0}#m{position:relative;width:700px}.in{margin-left:20px;width:200px}.out{margin-left:480px;width:200px}[role=row]{min-height:45px}[role=textbox]{min-height:40px;width:500px}</style></head><body>
<header><h2>yunusjon.digital</h2></header>
<div id="m" data-pagelet="IGDMessagesList"><div role="row"><div dir="auto" class="out">Assalomu alaykum</div></div><div role="row"><div dir="auto" class="in">Salom yordam kerak</div></div></div>
<div><div><div><div role="textbox" contenteditable="true" data-lexical-editor="true"><p><br></p></div></div><div role="button" tabindex="0" id="send">Send</div></div></div>
<script>document.getElementById('send').onclick=()=>{const ed=document.querySelector('[role=textbox]'),t=ed.innerText.trim();if(!t)return;
 const r=document.createElement('div');r.setAttribute('role','row');r.innerHTML='<div dir="auto" class="out"></div>';r.firstChild.innerText=t;
 document.getElementById('m').append(r);ed.innerHTML='<p><br></p>';localStorage.setItem('sent',t);};</script></body></html>`;

// Opens chats from its chat list or a deep link, but resets outside hash changes.
const telegram=`<!doctype html><html><head><title>Telegram</title><style>body{margin:0;display:flex}#LeftColumn{width:300px}#MiddleColumn{width:700px;position:relative}.Message{width:200px;min-height:40px}.own{margin-left:480px}</style></head><body>
<div id="LeftColumn"><a href="#111">Ali</a><br><a href="#222">Vali</a><br><a href="#-100500">Guruh</a></div>
<div id="MiddleColumn"></div>
<script>
const chats={'111':[['in','Salom']],'222':[['in','Narxi qancha?'],['own','Hozir aytaman']],'-100500':[['in','Group news']]};
const opened={};let current='';
function render(){const m=document.getElementById('MiddleColumn');if(!current){m.innerHTML='';return;}
 m.innerHTML='<div class="MiddleHeader"><div class="Avatar" data-peer-id="'+current+'"></div><h3 class="chat-title">Chat '+current+'</h3></div><div class="messages-container"></div><div id="editable-message-text" contenteditable="true"></div><button class="Button send">Send</button>';
 const list=m.querySelector('.messages-container');chats[current].forEach(([d,t],i)=>{const e=document.createElement('div');e.className='Message'+(d==='own'?' own':'');e.id='message-'+current+'-'+i;e.innerHTML='<div class="text-content"></div>';e.firstChild.textContent=t;list.append(e);});
 m.querySelector('.send').onclick=()=>{const ed=document.getElementById('editable-message-text'),t=ed.innerText.trim();if(!t)return;chats[current].push(['own',t]);localStorage.setItem('sent-'+current,t);render();};}
function open(id){current=id;opened[id]=(opened[id]||0)+1;
 if(id==='222'&&opened[id]===2)chats['222'].push(['in','Yetkazib berish bormi?']);
 history.replaceState(null,'','#'+id);render();}
document.getElementById('LeftColumn').addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;e.preventDefault();open(a.getAttribute('href').slice(1));});
addEventListener('hashchange',()=>history.replaceState(null,'',current?'#'+current:location.pathname));
if(location.hash.length>1)open(location.hash.slice(1));
</script></body></html>`;

const chatgpt=`<!doctype html><html><head><title>ChatGPT</title></head><body><main id="thread"></main>
<form><div id="prompt-textarea" contenteditable="true"><p><br></p></div><button type="button" data-testid="send-button" aria-label="Send prompt">Go</button></form>
<script>document.querySelector('[data-testid=send-button]').onclick=()=>{const ed=document.getElementById('prompt-textarea');localStorage.setItem('prompt',ed.innerText);ed.innerHTML='<p><br></p>';
 const art=document.createElement('article');art.innerHTML='<div data-message-author-role="assistant"><p>Assalomu alaykum!</p></div>';document.getElementById('thread').append(art);
 const stop=document.createElement('button');stop.dataset.testid='stop-button';stop.textContent='Stop';document.body.append(stop);
 setTimeout(()=>{art.firstChild.innerHTML='<p>Assalomu alaykum!</p><p>Qanday yordam kerak?</p>';stop.remove();
  const c=document.createElement('button');c.setAttribute('aria-label','Copy');c.textContent='c';art.append(c);},1500);};</script></body></html>`;

async function launch() {
  const server=https.createServer({key:fs.readFileSync(tmp+'/key.pem'),cert:fs.readFileSync(tmp+'/cert.pem')},(req,res)=>{
    const host=req.headers.host.split(':')[0],u=new URL(req.url,'https://'+host);res.setHeader('content-type','text/html');
    if(host==='www.instagram.com'&&u.pathname.startsWith('/direct/t/'))return res.end(instagram);
    if(host==='web.telegram.org'&&u.pathname==='/a/')return res.end(telegram);
    if(host==='chatgpt.com'&&u.pathname==='/')return res.end(chatgpt);
    res.end('<html><body>Log in</body></html>');
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));server.unref();
  const port=server.address().port;
  const hosts=['www.instagram.com','www.facebook.com','www.messenger.com','web.telegram.org','chatgpt.com','claude.ai','gemini.google.com'];
  const context=await chromium.launchPersistentContext(fs.mkdtempSync(path.join(tmp,'profile-')),{
    executablePath:process.env.AIY_CHROMIUM||chromium.executablePath(),headless:true,viewport:{width:1200,height:900},
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu',`--disable-extensions-except=${base}`,`--load-extension=${base}`,
      '--ignore-certificate-errors','--no-proxy-server','--host-resolver-rules='+hosts.map(h=>`MAP ${h} 127.0.0.1:${port}`).join(', ')]});
  let [worker]=context.serviceWorkers();worker||=await context.waitForEvent('serviceworker');
  const panel=await context.newPage();await panel.goto(`chrome-extension://${new URL(worker.url()).host}/panel.html`);
  await panel.waitForSelector('.account');
  for(const p of context.pages())if(p!==panel&&p.url().endsWith('/panel.html'))await p.close();
  return {context,panel,close:async()=>{await context.close();server.closeAllConnections();server.close();}};
}
const queue=panel=>panel.locator('#queue').innerText();

test('auto mode answers an Instagram message through ChatGPT',{skip:!openssl&&'openssl is unavailable',timeout:120000},async()=>{
  const {context,panel,close}=await launch();
  try {
    const chat=await context.newPage();await chat.goto('https://www.instagram.com/direct/t/test/');await panel.bringToFront();
    await panel.locator('[data-social][value=facebook]').uncheck();await panel.locator('[data-social][value=telegram]').uncheck();
    await panel.selectOption('#mode','auto');await panel.click('#inspect');
    await panel.getByRole('button',{name:'Shu xabarga javob tayyorlash'}).click();
    await panel.click('#start');
    await panel.waitForFunction(()=>/Yuborish tasdiqlandi|Qo‘lda tekshirish|Chatdagi qoralama|Suhbat o‘zgargan/.test(document.getElementById('queue').innerText),null,{timeout:90000});
    assert.match(await queue(panel),/Yuborish tasdiqlandi/);
    assert.equal(await chat.evaluate(()=>localStorage.getItem('sent')?.replace(/\s+/g,' ')),'Assalomu alaykum! Qanday yordam kerak?');
    await panel.click('#stop');
  } finally {await close();}
});

test('Telegram private chats are opened from the chat list and answered; groups are skipped',{skip:!openssl&&'openssl is unavailable',timeout:150000},async()=>{
  const {context,panel,close}=await launch();
  try {
    await panel.evaluate(async()=>{const {settings={}}=await chrome.storage.local.get('settings');
      await chrome.storage.local.set({settings:{...settings,interval:2,platforms:['telegram'],mode:'auto'}});});
    await panel.reload();await panel.waitForSelector('.account');
    await panel.click('#start');
    await panel.waitForFunction(()=>/Yuborish tasdiqlandi|Qo‘lda tekshirish|Chatdagi qoralama|Suhbat o‘zgargan/.test(document.getElementById('queue').innerText),null,{timeout:120000});
    assert.match(await queue(panel),/Yuborish tasdiqlandi/);assert.match(await queue(panel),/Yetkazib berish bormi\?/);
    assert.match(await panel.locator('#status-telegram').innerText(),/2 \/ 2/);
    const tg=context.pages().find(p=>p.url().startsWith('https://web.telegram.org/a/'));
    assert.equal(await tg.evaluate(()=>localStorage.getItem('sent-222')?.replace(/\s+/g,' ')),'Assalomu alaykum! Qanday yordam kerak?');
    assert.equal(await tg.evaluate(()=>localStorage.getItem('sent--100500')),null);
    await panel.click('#stop');
  } finally {await close();}
});
