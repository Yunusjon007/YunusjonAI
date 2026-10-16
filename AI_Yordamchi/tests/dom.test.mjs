import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const base=path.resolve(import.meta.dirname,'..');
const shared=fs.readFileSync(path.join(base,'shared.js'),'utf8'),content=fs.readFileSync(path.join(base,'content.js'),'utf8');
let browser;
test.before(async()=>{browser=await chromium.launch({executablePath:process.env.AIY_CHROMIUM || chromium.executablePath(),args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'],headless:true});});
test.after(async()=>{await browser?.close();});
const css='<style>body{margin:0} #messages{position:relative;width:700px;} .in{margin-left:20px;width:200px} .out{margin-left:480px;width:200px} [role=row]{height:45px} [role=textbox]{height:40px;width:500px} </style>';
function fixture({fallback=false,latest='incoming',draft=''}={}){
  const item=(id,dir,text)=>fallback?`<div dir="auto" class="${dir==='incoming'?'in':'out'}">${text}</div>`:
    `<div role="row" data-message-id="${id}" data-direction="${dir}"><div dir="auto" class="${dir==='incoming'?'in':'out'}">${text}</div></div>`;
  return css+`<aside><div dir="auto">SIDEBAR SHOULD NOT BE READ</div></aside><div id="messages" data-pagelet="IGDMessagesList">`+
    item('m1','outgoing','Old answer')+item('m2',latest,'Salom')+
    `</div><form><div role="textbox" data-lexical-editor="true" contenteditable="true">${draft}</div><button type="button" aria-label="Send" id="send">Send</button></form>`;
}
async function pageWith(html,url='https://www.instagram.com/direct/t/test/'){
  const page=await browser.newPage({viewport:{width:1000,height:800}});
  await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:html}));
  await page.goto(url);
  await page.evaluate(()=>{
    window.chrome={runtime:{id:'test-extension',onMessage:{addListener:fn=>window.listener=fn}}};
    window.call=(type,extra={})=>new Promise(resolve=>window.listener({aiy:true,type,...extra},{id:'test-extension'},resolve));
  });
  await page.addScriptTag({content:shared});await page.addScriptTag({content});return page;
}
const call=(p,type,extra={})=>p.evaluate(({type,extra})=>window.call(type,extra),{type,extra});
test('Instagram reads message panel and excludes editor/sidebar',async()=>{
  const p=await pageWith(fixture({draft:'Draft is not an incoming message'}));
  const r=await call(p,'snapshot');assert.ok(r.ok);assert.equal(r.data.rows.length,2);
  assert.equal(r.data.latest.text,'Salom');assert.equal(r.data.latest.direction,'incoming');
  assert.equal(r.data.draft,true);assert.ok(!JSON.stringify(r.data.rows).includes('SIDEBAR'));await p.close();
});
test('Instagram alternative DOM uses layout without manual CSS',async()=>{
  const p=await pageWith(fixture({fallback:true}));const {data}=await call(p,'snapshot');
  assert.equal(data.rows[0].direction,'outgoing');assert.equal(data.rows[1].direction,'incoming');await p.close();
});
test('outgoing latest message is never sendable',async()=>{
  const p=await pageWith(fixture({latest:'outgoing'}));assert.equal((await call(p,'snapshot')).data.sendable,false);await p.close();
});
test('content rejects stale signature before filling composer',async()=>{
  const p=await pageWith(fixture());const r=await call(p,'socialSend',{signature:'wrong',key:'instagram:test',text:'Reply',jobId:'j'});
  assert.equal(r.ok,false);assert.equal(await p.locator('[role=textbox]').innerText(),'');await p.close();
});
test('existing draft remains unchanged',async()=>{
  const p=await pageWith(fixture({draft:'My draft'}));const {data:s}=await call(p,'snapshot');
  const r=await call(p,'socialSend',{signature:s.signature,key:s.key,text:'Reply',jobId:'j'});
  assert.equal(r.ok,false);assert.equal(await p.locator('[role=textbox]').innerText(),'My draft');await p.close();
});
test('cancel arriving before send does not fill or click',async()=>{
  const p=await pageWith(fixture());const {data:s}=await call(p,'snapshot');await call(p,'cancel',{jobId:'j'});
  const r=await call(p,'socialSend',{signature:s.signature,key:s.key,text:'Reply',jobId:'j'});
  assert.equal(r.data.status,'cancelled');assert.equal(await p.locator('[role=textbox]').innerText(),'');await p.close();
});
test('new incoming message during typing prevents send',async()=>{
  const p=await pageWith(fixture());const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>{
    window.clicks=0;document.getElementById('send').onclick=()=>window.clicks++;
    document.querySelector('[role=textbox]').addEventListener('input',()=>{
      const el=document.createElement('div');el.setAttribute('role','row');el.dataset.messageId='m3';el.dataset.direction='incoming';
      el.innerHTML='<div dir="auto" class="in">New question</div>';document.getElementById('messages').append(el);
    },{once:true});
  });
  const r=await call(p,'socialSend',{signature:s.signature,key:s.key,text:'Reply',jobId:'j'});
  assert.equal(r.ok,false);assert.equal(await p.evaluate(()=>window.clicks),0);assert.equal(await p.locator('[role=textbox]').innerText(),'');await p.close();
});
test('draft-only fills editor without clicking send',async()=>{
  const p=await pageWith(fixture());const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>{window.clicks=0;document.getElementById('send').onclick=()=>window.clicks++;});
  const r=await call(p,'socialSend',{signature:s.signature,key:s.key,text:'Draft reply',jobId:'j',draftOnly:true});
  assert.equal(r.data.status,'drafted');assert.equal(await p.evaluate(()=>window.clicks),0);
  assert.equal(await p.locator('[role=textbox]').innerText(),'Draft reply');await p.close();
});
test('send confirms exact newly rendered outgoing message',async()=>{
  const p=await pageWith(fixture());const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>document.getElementById('send').onclick=()=>{
    const ed=document.querySelector('[role=textbox]'),row=document.createElement('div');
    row.setAttribute('role','row');row.dataset.messageId='m3';row.dataset.direction='outgoing';
    const b=document.createElement('div');b.dir='auto';b.className='out';b.textContent=ed.innerText;row.append(b);
    document.getElementById('messages').append(row);ed.textContent='';
  });
  const r=await call(p,'socialSend',{signature:s.signature,key:s.key,text:'Hello!',jobId:'j'});
  assert.equal(r.data.status,'sent');await p.close();
});
test('large media after text blocks automatic reply',async()=>{
  const p=await pageWith(fixture());await p.evaluate(()=>{
    const v=document.createElement('video');v.style='display:block;width:200px;height:150px;margin-top:20px';document.getElementById('messages').append(v);
  });const {data}=await call(p,'snapshot');assert.equal(data.sendable,false);assert.equal(data.latest.unsupported,true);await p.close();
});
test('Telegram A skips service rows and recognizes own messages',async()=>{
  const p=await pageWith(css+`<div id="MiddleColumn"><div class="messages-container"><div class="Message is-service">Today</div><div class="Message own" id="message-1"><div class="text-content">Old<span class="MessageMeta">12:00</span></div></div><div class="Message" id="message-2"><div class="text-content">Hello</div></div></div><div id="editable-message-text" contenteditable="true"> </div></div>`,'https://web.telegram.org/a/#123');
  const r=await call(p,'snapshot');assert.ok(r.ok);assert.equal(r.data.rows.length,2);assert.equal(r.data.rows[0].text,'Old');assert.equal(r.data.latest.direction,'incoming');await p.close();
});
test('Facebook semantic grid is scoped to messages',async()=>{
  const p=await pageWith(fixture().replace('data-pagelet="IGDMessagesList"','role="grid"'),'https://www.facebook.com/messages/t/test/');
  const r=await call(p,'snapshot');assert.ok(r.ok);assert.equal(r.data.latest.text,'Salom');await p.close();
});
test('AI rejects reuse of existing conversation',async()=>{
  const p=await pageWith('<div id="prompt-textarea" contenteditable="true"></div><article><div data-message-author-role="assistant">Old customer</div><button aria-label="Copy">Copy</button></article>','https://chatgpt.com/');
  const r=await call(p,'aiSubmit',{text:'New customer'});assert.equal(r.ok,false);assert.match(r.error,/Yangi/);await p.close();
});
test('AI completion requires response controls and no streaming',async()=>{
  const p=await pageWith('<div id="prompt-textarea" contenteditable="true"></div><article><div data-message-author-role="assistant">Reply</div><button aria-label="Copy">Copy</button></article><button data-testid="stop-button">Stop</button>','https://chatgpt.com/');
  const r=await call(p,'aiState');assert.equal(r.data.complete,true);assert.equal(r.data.busy,true);await p.close();
});
test('Claude and Gemini have separate visible answer selectors',async()=>{
  for(const [url,body]of [
    ['https://claude.ai/new','<div contenteditable="true" class="ProseMirror"></div><div data-is-streaming="false"><div class="font-claude-response">Claude reply</div></div>'],
    ['https://gemini.google.com/app','<rich-textarea><div contenteditable="true"></div></rich-textarea><model-response><div class="markdown">Gemini reply</div><button aria-label="Copy">Copy</button></model-response>']
  ]){const p=await pageWith(body,url);const r=await call(p,'aiState');assert.equal(r.data.ready,true);assert.equal(r.data.complete,true);assert.match(r.data.text,/reply/);await p.close();}
});
test('multi-line prompt is accepted by paragraph-based AI editors',async()=>{
  // ChatGPT, Claude and Gemini render each prompt line as its own paragraph.
  const p=await pageWith('<div id="prompt-textarea" contenteditable="true"><p><br></p></div><button data-testid="send-button">Send</button>','https://chatgpt.com/');
  await p.evaluate(()=>document.querySelector('[data-testid=send-button]').onclick=()=>{
    document.getElementById('prompt-textarea').innerHTML='<p><br></p>';
    const stop=document.createElement('button');stop.dataset.testid='stop-button';document.body.append(stop);
  });
  const r=await call(p,'aiSubmit',{text:'Rules line.\n\nBIZNES:\n[\n  {\n    "speaker": "incoming"\n  }\n]'});
  assert.equal(r.ok,true,r.error);assert.equal(r.data.submitted,true);await p.close();
});
test('multi-line reply is confirmed as sent from a paragraph-based composer',async()=>{
  const p=await pageWith(fixture().replace('contenteditable="true"></div>','contenteditable="true"><p><br></p></div>'));
  const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>document.getElementById('send').onclick=()=>{
    const ed=document.querySelector('[role=textbox]'),row=document.createElement('div');
    row.setAttribute('role','row');row.dataset.messageId='m3';row.dataset.direction='outgoing';
    const b=document.createElement('div');b.dir='auto';b.className='out';b.innerText=ed.innerText.replace(/\n+/g,'\n');row.append(b);
    document.getElementById('messages').append(row);ed.innerHTML='<p><br></p>';
  });
  const r=await call(p,'socialSend',{signature:s.signature,event:s.event,key:s.key,text:'Assalomu alaykum!\n\nQanday yordam bera olaman?',jobId:'j'});
  assert.equal(r.data.status,'sent');await p.close();
});
test('Enter sends when no send button is recognizable',async()=>{
  const p=await pageWith(fixture().replace('<button type="button" aria-label="Send" id="send">Send</button>',''));
  const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>{const ed=document.querySelector('[role=textbox]');ed.addEventListener('keydown',e=>{
    if(e.key!=='Enter')return;const row=document.createElement('div');
    row.setAttribute('role','row');row.dataset.messageId='m3';row.dataset.direction='outgoing';
    row.innerHTML='<div dir="auto" class="out"></div>';row.firstChild.textContent=ed.innerText;
    document.getElementById('messages').append(row);ed.textContent='';
  });});
  const r=await call(p,'socialSend',{signature:s.signature,event:s.event,key:s.key,text:'Hello!',jobId:'j'});
  assert.equal(r.data.status,'sent');await p.close();
});
test('read receipt changing the rows does not block the reply',async()=>{
  const p=await pageWith(fixture());const {data:s}=await call(p,'snapshot');
  await p.evaluate(()=>{const row=document.createElement('div');row.setAttribute('role','row');
    row.innerHTML='<div dir="auto" style="margin-left:300px;width:60px">Seen</div>';document.getElementById('messages').prepend(row);
    document.getElementById('send').onclick=()=>{const ed=document.querySelector('[role=textbox]'),r=document.createElement('div');
      r.setAttribute('role','row');r.dataset.messageId='m3';r.dataset.direction='outgoing';r.innerHTML='<div dir="auto" class="out"></div>';
      r.firstChild.textContent=ed.innerText;document.getElementById('messages').append(r);ed.textContent='';};});
  const {data:now}=await call(p,'snapshot');assert.notEqual(now.signature,s.signature);assert.equal(now.event,s.event);
  const r=await call(p,'socialSend',{signature:s.signature,event:s.event,key:s.key,text:'Hello!',jobId:'j'});
  assert.equal(r.data.status,'sent');await p.close();
});
