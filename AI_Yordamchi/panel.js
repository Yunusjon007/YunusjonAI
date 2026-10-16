import {Controller,terminalStates} from './engine.js';
const A=globalThis.AIY,$=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let engine,locked=false,renderedQueue='',previews=[];
function notice(text=''){$('notice').textContent=text;$('notice').hidden=!text;}
function button(text,fn,cls='secondary') {const b=node('button',text,cls);b.addEventListener('click',()=>Promise.resolve().then(fn).catch(e=>notice(e.message)));return b;}
function settingsFromUI(){return {rules:$('rules').value,mode:$('mode').value,
  platforms:[...document.querySelectorAll('[data-social]:checked')].map(e=>e.value),
  providers:[...document.querySelectorAll('[data-ai]:checked')].map(e=>e.value)};}
function buildAccounts(){
  const box=$('accounts');box.replaceChildren();
  for(const [label,keys,type]of [['XABARLAR',['instagram','facebook','telegram'],'social'],['AI NAVBATI',['chatgpt','claude','gemini'],'ai']]) {
    box.append(node('div',label,'account-group'));
    for(const key of keys) {
      const row=node('div',undefined,'account'),check=node('input');check.type='checkbox';check.value=key;check.setAttribute('data-'+type,'');
      check.checked=(type==='social'?engine.settings.platforms:engine.settings.providers).includes(key);
      check.setAttribute('aria-label',A.sources[key].name+'ni ishlatish');
      const n=node('div',undefined,'name');n.append(node('strong',A.sources[key].name));const s=node('small','Saytni ochib login qiling');s.id='status-'+key;n.append(s);
      row.append(check,n,button('Ochish',()=>engine.openAccount(key)));box.append(row);
    }
  }
}
const labels={pending:'AI navbatida',generating:'AI javob yozmoqda',ready:'Ko‘rib chiqing',sending:'Yuborilmoqda',sent:'Yuborish tasdiqlandi',drafted:'Chatdagi qoralama',uncertain:'Qo‘lda tekshirish kerak',skipped:'O‘tkazilgan',stale:'Suhbat o‘zgargan',cancelled:'Bekor qilingan'};
function renderQueue(){
  const jobs=Object.values(engine.state.jobs).sort((a,b)=>b.created-a.created).slice(0,60);
  const signature=JSON.stringify(jobs.map(j=>[j.id,j.status,j.reply,j.note]))+engine.running+engine.busy;
  if(signature===renderedQueue)return;renderedQueue=signature;
  // Keep user edits while statuses elsewhere update.
  const edits=new Map([...document.querySelectorAll('.reply')].map(e=>[e.dataset.id,e.value]));
  const box=$('queue');box.className=jobs.length?'':'empty';box.replaceChildren();
  $('count').textContent=Object.values(engine.state.jobs).filter(j=>!terminalStates.has(j.status)).length;
  if(!jobs.length){box.textContent='Yangi xabar kelganda javob shu yerda paydo bo‘ladi.';return;}
  for(const job of jobs){
    const card=node('article',undefined,'job'),meta=node('div',undefined,'meta');
    meta.append(node('strong',A.sources[job.platform].name),node('span',labels[job.status]||job.status,'badge '+(job.status==='sent'?'good':['uncertain','drafted'].includes(job.status)?'warn':'')));
    card.append(meta,node('h3',job.title),node('div',job.incoming,'incoming'));
    let edit;
    if(job.reply){edit=node('textarea',undefined,'reply');edit.dataset.id=job.id;edit.value=edits.get(job.id)??job.reply;edit.maxLength=3000;edit.setAttribute('aria-label','Tayyor javob');edit.disabled=job.status!=='ready'||engine.running||engine.busy;card.append(edit);}
    if(job.note)card.append(node('p',job.note,'job-note'));
    const actions=node('div',undefined,'job-actions');
    if(job.status==='ready'){
      const send=button('Yuborish',()=>engine.manualAction(job.id,edit.value),'primary');
      const draft=button('Chatga qo‘yish',()=>engine.manualAction(job.id,edit.value,true));
      send.disabled=draft.disabled=engine.running||engine.busy;actions.append(send,draft);
      if(engine.running)card.append(node('p','Qo‘lda ko‘rib chiqish uchun To‘xtatish tugmasini bosing.','hint'));
    }
    actions.append(button('Chatni ochish',()=>engine.openChat(job)));
    if(['uncertain','drafted'].includes(job.status)){
      const r=button('Chatni tekshirdim',()=>engine.resolve(job.id));r.disabled=engine.running||engine.busy;actions.append(r);
    } else if(['pending','ready'].includes(job.status)){
      const skip=button('O‘tkazish',()=>engine.skip(job.id));skip.disabled=engine.running||engine.busy;actions.append(skip);
    }
    card.append(actions);box.append(card);
  }
}
function renderPreviews(){
  const box=$('previews');box.replaceChildren();box.className=previews.length?'':'empty';
  if(!previews.length){box.textContent='Chatni oching va tekshirish tugmasini bosing.';return;}
  for(const snap of previews){
    const card=node('article',undefined,'preview');card.append(node('h3',A.sources[snap.platform]?.name+' · '+(snap.title||'Chat')));
    if(snap.error)card.append(node('p',snap.error,'job-note'));
    else {
      for(const r of snap.rows.slice(-4)){
        const bubble=node('div',undefined,'bubble '+(r.direction==='outgoing'?'out':''));
        bubble.append(node('small',{incoming:'Suhbatdosh',outgoing:'Siz',unknown:'Yo‘nalishi noaniq'}[r.direction]),node('span',r.text));card.append(bubble);
      }
      if(snap.draft)card.append(node('p','Chatda qoralama bor. Avval uni ko‘rib chiqing.','hint'));
      if(snap.sendable&&!snap.draft){const b=button('Shu xabarga javob tayyorlash',()=>engine.addManual(snap));b.disabled=engine.running||engine.busy;card.append(b);}
      else card.append(node('p','Javob talab qiladigan kiruvchi matn tanilmadi.','hint'));
    }
    box.append(card);
  }
}
function render(){
  if(!engine?.state)return;
  $('activity').textContent=engine.activity;$('dot').classList.toggle('on',engine.running);
  $('start').disabled=engine.running||engine.busy||!locked;
  $('stop').disabled=!engine.running;
  for(const id of ['save','inspect','rules','mode'])$(id).disabled=engine.running||engine.busy||!locked;
  document.querySelectorAll('[data-social],[data-ai]').forEach(e=>e.disabled=engine.running||engine.busy||!locked);
  for(const [p,value]of Object.entries(engine.status)){const e=$('status-'+p);if(e)e.textContent=value;}
  renderQueue();
  const log=$('logs');log.replaceChildren();
  for(const l of engine.state.logs.slice(0,30)){const e=node('div',undefined,'log '+l.kind);e.append(node('time',new Date(l.time).toLocaleTimeString()),node('span',l.message));log.append(e);}
}
$('save').addEventListener('click',async()=>{try{notice();await engine.configure(settingsFromUI());}catch(e){notice(e.message);}});
$('start').addEventListener('click',async()=>{try{notice();await engine.configure(settingsFromUI());await engine.start();}catch(e){notice(e.message);}});
$('stop').addEventListener('click',()=>engine.stop().catch(e=>notice(e.message)));
$('inspect').addEventListener('click',async()=>{try{notice();await engine.configure(settingsFromUI());previews=await engine.inspect();renderPreviews();}catch(e){notice(e.message);}});
$('export').addEventListener('click',async()=>{
  const pages=await engine.diagnose().catch(e=>[{error:e.message}]);
  const report={version:chrome.runtime.getManifest?.().version,time:new Date().toISOString(),running:engine.running,
    settings:{platforms:engine.settings.platforms,providers:engine.settings.providers,mode:engine.settings.mode},statuses:engine.status,
    logs:engine.state.logs,counts:Object.values(engine.state.jobs).reduce((o,j)=>(o[j.status]=(o[j.status]||0)+1,o),{}),pages};
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
  const a=node('a');a.href=url;a.download='AI_Yordamchi_holat.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('beforeunload',e=>{if(engine?.running||engine?.busy){e.preventDefault();e.returnValue='';}});
// Only one dashboard may own automation. A second tab is read-only.
await navigator.locks.request('aiy-controller',{ifAvailable:true},async lock=>{
  locked=!!lock;
  if(!lock){
    notice('Boshqaruv boshqa oynada ochiq. O‘sha oynadan foydalaning.');
    document.querySelectorAll('button,input,textarea,select').forEach(e=>e.disabled=true);
    return;
  }
  engine=new Controller(render);await engine.init();buildAccounts();
  $('rules').value=engine.settings.rules;$('mode').value=engine.settings.mode;render();
  await new Promise(()=>{});
});
