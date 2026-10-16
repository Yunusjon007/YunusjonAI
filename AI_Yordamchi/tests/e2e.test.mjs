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

const avatar='<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" style="width:52px;height:52px;border-radius:50%">';

// One page for every /direct/ address: chat list on the left (Primary or
// General), the open chat on the right. Opening a chat marks it read.
const instagram=`<!doctype html><html><head><title>Instagram</title><style>body{margin:0;display:flex}#list{width:360px}#thread{width:700px;position:relative}
.row{display:flex;align-items:center;gap:8px;width:340px;height:72px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:rgb(0,149,246)}
#m{position:relative;width:700px}.in{margin-left:20px;width:200px}.out{margin-left:480px;width:200px}[role=row]{min-height:45px}[role=textbox]{min-height:40px;width:500px}</style></head><body>
<div id="list"></div><div id="thread"></div>
<script>
const chats=JSON.parse(localStorage.getItem('chats')||'null')||{
  test:{name:'yunusjon.digital',folder:'inbox',unread:false,msgs:[['out','Assalomu alaykum'],['in','Salom yordam kerak']]},
  yv:{name:'Yunusjon Valiyev',folder:'general',unread:true,msgs:[['in','Salom yordam kerak']]},
  ali:{name:'Ali',folder:'general',unread:false,msgs:[['in','Eski savol']]}};
const save=()=>localStorage.setItem('chats',JSON.stringify(chats));
function render(){
  const path=location.pathname,parts=path.split('/'),open=parts[2]==='t'?parts[3]:undefined;
  if(path.startsWith('/direct/general'))sessionStorage.setItem('folder','general');
  else if(!open)sessionStorage.setItem('folder','inbox');
  if(chats[open]?.unread){chats[open].unread=false;save();}
  const list=document.getElementById('list');list.innerHTML='';
  for(const [id,c] of Object.entries(chats))if(c.folder===(sessionStorage.getItem('folder')||'inbox')){
    const r=document.createElement('div');r.className='row';r.setAttribute('role','button');r.tabIndex=0;
    r.innerHTML='${avatar}<div><div class="name"></div><div class="prev"></div></div>'+(c.unread?'<span class="dot"></span>':'');
    r.querySelector('.name').textContent=c.name;r.querySelector('.prev').textContent=c.msgs.at(-1)[1];
    r.onclick=()=>{history.pushState(null,'','/direct/t/'+id+'/');render();};list.append(r);}
  const t=document.getElementById('thread');t.innerHTML='';if(!chats[open])return;
  t.innerHTML='<header><h2></h2></header><div id="m" data-pagelet="IGDMessagesList"></div><div><div><div><div role="textbox" contenteditable="true" data-lexical-editor="true"><p><br></p></div></div><div role="button" tabindex="0" id="send">Send</div></div></div>';
  t.querySelector('h2').textContent=chats[open].name;
  for(const [d,text] of chats[open].msgs){const r=document.createElement('div');r.setAttribute('role','row');r.innerHTML='<div dir="auto" class="'+d+'"></div>';r.firstChild.innerText=text;t.querySelector('#m').append(r);}
  t.querySelector('#send').onclick=()=>{const text=t.querySelector('[role=textbox]').innerText.trim();if(!text)return;
    chats[open].msgs.push(['out',text]);save();localStorage.setItem('sent-'+open,text);render();};
}
addEventListener('popstate',render);render();
</script></body></html>`;

// Opens chats from its chat list or a deep link, but resets outside hash
// changes. Like Telegram in a background tab, it keeps chats unread until a reply.
const telegram=`<!doctype html><html><head><title>Telegram</title><style>body{margin:0;display:flex}#LeftColumn{width:320px}#MiddleColumn{width:700px;position:relative}
.ListItem-button{display:flex;align-items:center;gap:8px;width:300px;height:64px}.ChatBadge{display:inline-block;min-width:20px;height:20px;border-radius:10px;background:rgb(10,198,48);color:#fff;text-align:center}
.Message{width:200px;min-height:40px}.own{margin-left:480px}</style></head><body>
<div id="LeftColumn"></div><div id="MiddleColumn"></div>
<script>
const chats={'111':{name:'Ali',unread:0,msgs:[['in','Salom'],['own','Va alaykum assalom']]},
  '222':{name:'Dr.Yunusbek Yusupovich',unread:1,msgs:[['own','Hozir aytaman'],['in','Salom yordam kerak']]},
  '-100500':{name:'Toshkent rentgen',unread:3,msgs:[['in','Group news']]}};
let current='';
function render(){
  const left=document.getElementById('LeftColumn');left.innerHTML='';
  for(const [id,c] of Object.entries(chats)){const a=document.createElement('a');a.className='ListItem-button';a.href='#'+id;
    a.innerHTML='${avatar}<div><div class="name"></div><div class="prev"></div></div>'+(c.unread?'<span class="ChatBadge">'+c.unread+'</span>':'');
    a.querySelector('.name').textContent=c.name;a.querySelector('.prev').textContent=c.msgs.at(-1)[1];left.append(a);}
  const m=document.getElementById('MiddleColumn');if(!current){m.innerHTML='';return;}
  m.innerHTML='<div class="MiddleHeader"><div class="Avatar" data-peer-id="'+current+'"></div><h3 class="chat-title"></h3></div><div class="messages-container"></div><div id="editable-message-text" contenteditable="true"></div><button class="Button send">Send</button>';
  m.querySelector('h3').textContent=chats[current].name;
  chats[current].msgs.forEach(([d,t],i)=>{const e=document.createElement('div');e.className='Message'+(d==='own'?' own':'');e.id='message-'+current+'-'+i;e.innerHTML='<div class="text-content"></div>';e.firstChild.textContent=t;m.querySelector('.messages-container').append(e);});
  m.querySelector('.send').onclick=()=>{const t=document.getElementById('editable-message-text').innerText.trim();if(!t)return;
    chats[current].msgs.push(['own',t]);chats[current].unread=0;localStorage.setItem('sent-'+current,t);render();};
}
function open(id){current=id;history.replaceState(null,'','#'+id);render();}
document.getElementById('LeftColumn').addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;e.preventDefault();open(a.getAttribute('href').slice(1));});
addEventListener('hashchange',()=>history.replaceState(null,'',current?'#'+current:location.pathname));
render();if(location.hash.length>1)open(location.hash.slice(1));
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
    if(host==='www.instagram.com'&&u.pathname.startsWith('/direct/'))return res.end(instagram);
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

const finished=panel=>panel.waitForFunction(()=>/Yuborish tasdiqlandi|Qo‘lda tekshirish|Chatdagi qoralama|Suhbat o‘zgargan/.test(document.getElementById('queue').innerText),null,{timeout:120000});
const sent=(page,id)=>page.evaluate(id=>localStorage.getItem('sent-'+id)?.replace(/\s+/g,' ')??null,id);
async function configure(panel,settings) {
  await panel.evaluate(async settings=>{const saved=(await chrome.storage.local.get('settings')).settings||{};
    await chrome.storage.local.set({settings:{...saved,...settings}});},settings);
  await panel.reload();await panel.waitForSelector('.account');
}
const reply='Assalomu alaykum! Qanday yordam kerak?';

test('an open chat can be answered from the manual check',{skip:!openssl&&'openssl is unavailable',timeout:150000},async()=>{
  const {context,panel,close}=await launch();
  try {
    await configure(panel,{platforms:['instagram'],mode:'auto'});
    const chat=await context.newPage();await chat.goto('https://www.instagram.com/direct/t/test/');await panel.bringToFront();
    await panel.click('#inspect');await panel.getByRole('button',{name:'Shu xabarga javob tayyorlash'}).click();
    await panel.click('#start');await finished(panel);
    assert.match(await queue(panel),/Yuborish tasdiqlandi/);assert.equal(await sent(chat,'test'),reply);
    await panel.click('#stop');
  } finally {await close();}
});

test('an unread Instagram message in General is answered without opening any chat by hand',{skip:!openssl&&'openssl is unavailable',timeout:150000},async()=>{
  const {context,panel,close}=await launch();
  try {
    await configure(panel,{platforms:['instagram'],mode:'auto',interval:2});
    await panel.click('#start');await finished(panel);
    assert.match(await queue(panel),/Yunusjon Valiyev[\s\S]*Yuborish tasdiqlandi|Yuborish tasdiqlandi[\s\S]*Yunusjon Valiyev/);
    const ig=context.pages().find(p=>p.url().startsWith('https://www.instagram.com/'));
    assert.equal(await sent(ig,'yv'),reply);
    // Read chats are left alone, even when their last message is incoming.
    assert.equal(await sent(ig,'ali'),null);assert.equal(await sent(ig,'test'),null);
    await panel.click('#stop');
  } finally {await close();}
});

test('an unread Telegram private chat is answered; groups are skipped',{skip:!openssl&&'openssl is unavailable',timeout:150000},async()=>{
  const {context,panel,close}=await launch();
  try {
    await configure(panel,{platforms:['telegram'],mode:'auto',interval:2});
    await panel.click('#start');await finished(panel);
    assert.match(await queue(panel),/Yuborish tasdiqlandi/);
    assert.match(await panel.locator('#status-telegram').innerText(),/1 ta o‘qilmagan/);
    const tg=context.pages().find(p=>p.url().startsWith('https://web.telegram.org/a/'));
    assert.equal(await sent(tg,'222'),reply);
    assert.equal(await sent(tg,'-100500'),null);assert.equal(await sent(tg,'111'),null);
    await panel.click('#stop');
  } finally {await close();}
});
