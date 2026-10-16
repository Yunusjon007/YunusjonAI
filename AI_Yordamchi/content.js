(() => {
  // Versioned so an updated extension replaces a copy left behind by the old one.
  if(globalThis.__AIY_CONTENT__===2) return;
  globalThis.__AIY_CONTENT__=2;
  const A=globalThis.AIY;
  const cancelled=new Set();
  const all=(sel,root=document)=>Array.from(root.querySelectorAll(sel));
  const visible=el=>!!el && !!el.getClientRects().length && getComputedStyle(el).visibility!=='hidden';
  const text=el=>A.norm(el?.innerText ?? el?.textContent ?? '');
  const first=(selectors,root=document)=>{
    for(const s of selectors) {const e=all(s,root).find(visible); if(e) return e;}
    return null;
  };
  const label=el=>A.norm(el.getAttribute('aria-label')||el.getAttribute('title')||el.innerText||'');
  function uniqueEditor(selectors) {
    for(const s of selectors) {
      const es=all(s).filter(visible);
      if(es.length===1) return es[0];
      if(es.length>1) throw Error('Bir nechta yozish katagi bor. Boshqa chat/popupni yoping.');
    }
    return null;
  }
  function editor(p) {
    if(p==='telegram') return uniqueEditor(['#MiddleColumn #editable-message-text',
      '#column-center .input-message-input[contenteditable="true"]']);
    if(p==='instagram') return uniqueEditor(['[data-lexical-editor="true"][contenteditable="true"][role="textbox"]',
      '[contenteditable="true"][role="textbox"]']);
    if(p==='facebook') return uniqueEditor(['[contenteditable="true"][role="textbox"][data-lexical-editor="true"]',
      '[contenteditable="true"][role="textbox"]']);
    return null;
  }
  function scopeFor(p,ed) {
    if(p==='instagram') return first(['[data-pagelet="IGDMessagesList"]']);
    if(p==='telegram') return first(['#MiddleColumn .messages-container','#MiddleColumn .MessageList',
      '#column-center .bubbles-inner','#MiddleColumn']);
    const grids=all('[role="grid"], [role="log"]').filter(visible).filter(e=>
      e.querySelector('[role="row"]') && !e.querySelector('a[href*="/messages/t/"]'));
    if(grids.length===1) return grids[0];
    const mains=all('[role="main"]').filter(e=>visible(e)&&(!ed||e.contains(ed)));
    return mains.length===1?mains[0]:null;
  }
  function clean(el,p) {
    const c=el.cloneNode(true);
    c.querySelectorAll('[contenteditable="true"], script, style, button, [role="button"], time, .MessageMeta, .Reactions, .reactions, .time, .message-time').forEach(n=>n.remove());
    return A.norm(c.textContent);
  }
  function direction(el,root,p) {
    if(p==='telegram') {
      if(el.matches('.own,.is-out,.is-outgoing') || el.closest('.own,.is-out')) return 'outgoing';
      if(el.matches('.Message,.bubble') && !el.matches('.is-service,.service')) return 'incoming';
    }
    let node=el;
    for(let i=0;i<6&&node&&node!==root;i++,node=node.parentElement) {
      const d=(node.getAttribute('data-message-direction')||node.getAttribute('data-direction')||'').toLowerCase();
      if(['outgoing','out','sent'].includes(d)) return 'outgoing';
      if(['incoming','in','received'].includes(d)) return 'incoming';
      const l=node.getAttribute('aria-label')||'';
      if(/^(you sent|вы отправили|siz yubordingiz)\b/i.test(l)) return 'outgoing';
    }
    return A.geometryDirection(el.getBoundingClientRect(),root.getBoundingClientRect());
  }
  function messageID(el,root) {
    for(let n=el;n&&n!==root;n=n.parentElement) {
      for(const name of ['data-message-id','data-mid','data-msg-id']) {
        const val=n.getAttribute(name); if(val) return `${name}:${val}`;
      }
      const id=n.getAttribute('id');
      if(id && (/^(mid[._-]|message[-_]|msg[-_])/i.test(id)||/^\d+$/.test(id))) return id;
    }
    return '';
  }
  function rowsFor(root,p) {
    if(p==='telegram') {
      return all('.Message:not(.is-service), .bubble:not(.service)',root).filter(visible)
        .filter(el=>!el.parentElement?.closest('.Message,.bubble')).map(el=>{
          const body=el.querySelector('.text-content, .translatable-message, .message');
          return {el:body||el,wrapper:el,unsupported:!body};
        });
    }
    // Prefer semantic message containers. Nested rows are reduced to leaf rows.
    let wrappers=all('[data-message-id],[data-mid],[role="row"]',root).filter(visible)
      .filter(e=>!e.querySelector('[contenteditable="true"]')&&!e.closest('[contenteditable="true"]'));
    wrappers=wrappers.filter(e=>!wrappers.some(other=>other!==e&&e.contains(other)));
    if(wrappers.length) return wrappers.map(wrapper=>{
      const bits=all('div[dir="auto"],span[dir="auto"]',wrapper)
        .filter(e=>visible(e)&&!e.closest('button,[role="button"],time'));
      const leaf=bits.filter(e=>!bits.some(other=>other!==e&&e.contains(other)));
      const el=leaf.find(e=>text(e)&&!/^\d{1,2}:\d{2}/.test(text(e)))||wrapper;
      return {el,wrapper,unsupported:!text(el)||!!wrapper.querySelector('video,audio')};
    });
    // Instagram's alternative DOM uses leaf dir=auto text nodes, not rows.
    const bits=all('div[dir="auto"],span[dir="auto"]',root).filter(e=>visible(e)&&
      !e.closest('[contenteditable="true"],button,[role="button"],time')&&text(e));
    return bits.filter(e=>!bits.some(other=>other!==e&&e.contains(other)))
      .filter(e=>!/^\d{1,2}:\d{2}(\s*[AP]M)?$/i.test(text(e)))
      .map(el=>({el,wrapper:el,unsupported:false}));
  }
  async function snapshot() {
    const p=A.platform(location.href), key=A.thread(location.href);
    if(!key) throw Error('Shaxsiy chat ochilmagan. Direct / Messenger / Telegram chatini oching.');
    if(p==='telegram') {
      // Telegram swaps chats in place; never read the previous chat under the new address.
      const peer=decodeURIComponent(location.hash.slice(1));
      const shown=all('#MiddleColumn .MiddleHeader [data-peer-id], #column-center .chat-info [data-peer-id]')
        .filter(visible).map(e=>e.getAttribute('data-peer-id'));
      if(/^\d+$/.test(peer) && shown.length && !shown.includes(peer))
        throw Error('Chat hali yuklanmagan. Keyingi tekshiruvda qayta ko‘riladi.');
    }
    const ed=editor(p); if(!ed) throw Error('Xabar yozish katagi topilmadi. Loginni va chatni tekshiring.');
    const root=scopeFor(p,ed); if(!root) throw Error('Bu sahifadagi suhbat paneli tanilmadi. Avtomatik yuborish to‘xtatildi.');
    const raw=rowsFor(root,p);
    const rows=raw.map(({el,wrapper,unsupported})=>({
      id:messageID(wrapper,root),text:clean(el,p),direction:direction(p==='telegram'?wrapper:el,root,p),
      unsupported:unsupported || !!wrapper.querySelector('video,audio') || all('img',wrapper).some(im=>{const r=im.getBoundingClientRect();return r.width>90&&r.height>70;})
    })).filter(r=>r.text||r.unsupported).slice(-12);
    if(!rows.length) throw Error('O‘qiladigan matnli xabar topilmadi.');
    // A later media block prevents answering an earlier text as if it were latest.
    const lastRaw=raw.at(-1);
    const laterMedia=lastRaw && all('img,video,audio',root).filter(visible).some(e=>{
      const b=e.getBoundingClientRect(),last=lastRaw.wrapper.getBoundingClientRect();
      return b.width>90 && b.height>70 && b.top>last.bottom+3;
    });
    if(laterMedia) rows.push({id:'',text:'[Media xabar]',direction:'unknown',unsupported:true});
    const latest=rows.at(-1);
    const signature=await A.digest(JSON.stringify({key,rows}));
    const event=await A.digest(JSON.stringify({key,last:latest.id||rows.slice(-8)}));
    const h=first(['header h1','header h2','[role="main"] h2','#MiddleColumn .chat-title']);
    return {platform:p,key,url:location.href,title:text(h)||document.title,rows,latest,
      signature,event,readable:true,sendable:latest.direction==='incoming'&&!latest.unsupported&&!!latest.text,
      draft:!!editorValue(ed)};
  }
  function discover() {
    const p=A.platform(location.href), found=new Map();
    for(const a of all('a[href]')) {
      if(!visible(a)) continue;
      const url=a.href,key=A.thread(url);
      if(key&&A.platform(url)===p) found.set(key,{url,key,title:text(a).slice(0,70)});
    }
    if(p==='telegram') {
      for(const e of all('[data-peer-id],a.chatlist-chat')) {
        const id=e.getAttribute('data-peer-id');
        if(!visible(e)||!id||!/^[-\d]+$/.test(id)) continue;
        // Only Web K explicitly exposes peer ids in the chat list.
        if(location.pathname.startsWith('/k/')) {
          const url=location.origin+'/k/#'+id;found.set(A.thread(url),{url,key:A.thread(url),title:text(e).slice(0,70)});
        }
      }
    }
    return {platform:p,threads:[...found.values()]};
  }
  function editorValue(ed) {return A.norm('value' in ed?ed.value:ed.innerText);}
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  function selectAll(ed) {
    ed.focus();
    const sel=getSelection(),range=document.createRange();range.selectNodeContents(ed);
    sel.removeAllRanges();sel.addRange(range);
  }
  async function fill(ed,value) {
    ed.focus();
    if(ed instanceof HTMLTextAreaElement || ed instanceof HTMLInputElement) {
      const proto=ed instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(ed,value);
      ed.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));
    } else {
      selectAll(ed);
      document.execCommand('insertText',false,value);
      // Editors such as Lexical apply input on the next tick.
      await pause(80);
      if(value && !editorValue(ed)) {
        // Some editors ignore insertText but accept pasted text.
        selectAll(ed);const data=new DataTransfer();data.setData('text/plain',value);
        ed.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));
        await pause(80);
      }
    }
    if(A.flat(editorValue(ed))!==A.flat(value)) throw Error('Yozilgan matn tasdiqlanmadi. Chatni tekshiring.');
  }
  async function openThread(req) {
    const target=A.thread(req.url);
    if(!target) throw Error('Shaxsiy chat ochilmagan. Direct / Messenger / Telegram chatini oching.');
    if(A.thread(location.href)===target) return {opened:true};
    // Telegram can ignore address changes made from outside the app, so open
    // the chat the way a person does: through its chat list entry.
    const peer=decodeURIComponent(new URL(req.url).hash.slice(1));
    const item=all('a[href]').find(a=>visible(a)&&A.thread(a.href)===target)||
      all('[data-peer-id]').find(e=>visible(e)&&e.getAttribute('data-peer-id')===peer&&e.closest('#LeftColumn,#column-left'));
    if(!item) return {opened:false};
    for(const type of ['mousedown','mouseup'])
      item.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,button:0,view:window}));
    item.click();
    for(let i=0;i<20;i++) {await pause(150);if(A.thread(location.href)===target) return {opened:true};}
    return {opened:false};
  }
  function sendButton(ed,p,ai=false) {
    const candidates=[];
    const selectors=ai? {
      chatgpt:['[data-testid="send-button"]','#composer-submit-button'],
      claude:['button[aria-label="Send message"]','button[data-testid="send-button"]'],
      gemini:['button.send-button','button[aria-label="Send message"]']
    }[p]:p==='telegram'?['#MiddleColumn button.Button.send','#MiddleColumn .send-message-button',
      '#column-center .btn-send']:[];
    for(const s of selectors||[]) candidates.push(...all(s).filter(visible));
    let scope=ed.closest('form');
    if(!scope) {scope=ed;for(let i=0;i<5&&scope.parentElement;i++)scope=scope.parentElement;}
    const names=/^(send|send message|send now|отправить|отправить сообщение|yuborish|xabar yuborish|jo‘natish)$/i;
    for(const e of all('button,[role="button"]',scope)) {
      const l=label(e),child=all('[aria-label]',e).map(n=>n.getAttribute('aria-label'));
      if(visible(e)&&(names.test(l)||child.some(s=>names.test(s)))) candidates.push(e);
    }
    const unique=[...new Set(candidates)].filter(e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true');
    return unique.length===1?unique[0]:null;
  }
  async function waitButton(ed,p,ai=false) {
    // Send buttons usually enable only after the editor has processed the text.
    for(let i=0;i<10;i++) {const b=sendButton(ed,p,ai);if(b) return b;await pause(300);}
    return null;
  }
  function pressEnter(ed) {
    ed.focus();
    for(const type of ['keydown','keyup'])
      ed.dispatchEvent(new KeyboardEvent(type,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}));
  }
  async function socialSend(req) {
    if(cancelled.has(req.jobId))return {status:'cancelled'};
    // The latest message decides; read receipts or older rows may shift the rest.
    const changed=s=>s.key!==req.key||(req.event?s.event!==req.event:s.signature!==req.signature);
    const before=await snapshot();
    if(changed(before)) throw Error('Suhbat o‘zgargan. Javob yangilanishi kerak.');
    if(!before.sendable) throw Error('Oxirgi xabar kiruvchi matn sifatida tanilmadi.');
    const ed=editor(before.platform);
    if(editorValue(ed)) throw Error('Chatda qoralama bor. Uni o‘zgartirmadim.');
    if(!req.text||req.text.length>3000) throw Error('Javob 1–3000 belgidan iborat bo‘lsin.');
    if(cancelled.has(req.jobId))return {status:'cancelled'};
    const reply=A.flat(req.text),typed=()=>A.flat(editorValue(ed))===reply;
    const clear=async()=>{if(typed())await fill(ed,'');};
    // Persisted sending state is owned by the dashboard before this side effect.
    await fill(ed,req.text);
    if(req.draftOnly) return {status:'drafted'};
    await pause(250);
    if(cancelled.has(req.jobId)){await clear();return {status:'cancelled'};}
    const now=await snapshot();
    if(changed(now)) {await clear();throw Error('Yangi xabar keldi. Yuborish bekor qilindi.');}
    const button=await waitButton(ed,before.platform);
    if(cancelled.has(req.jobId)){await clear();return {status:'cancelled'};}
    // Without a recognizable button, Enter is how these chats send.
    if(button) button.click(); else pressEnter(ed);
    // Line breaks inside a sent bubble may vanish from its text, so compare without whitespace.
    // Wide bubbles have no reliable side, so any new non-incoming copy counts.
    const bare=v=>A.flat(v).replace(/\s/g,''),sent=r=>r.direction!=='incoming'&&bare(r.text)===bare(reply);
    const copies=rows=>rows.filter(sent).length;
    for(let i=0;i<12;i++) {
      await pause(750);
      try {
        const after=await snapshot();
        if(after.key!==req.key) return {status:'uncertain'};
        if(copies(after.rows)>copies(before.rows) || (after.event!==before.event&&sent(after.latest))) return {status:'sent'};
      } catch {}
    }
    if(typed()) return {status:'drafted',note:'Yuborish tasdiqlanmadi. Javob chatga qo‘yildi; qo‘lda yuboring.'};
    return {status:'uncertain',note:'Yuborish tasdiqlanmadi. Chatni tekshiring; qayta yuborilmaydi.'};
  }
  const aiConfig={
    chatgpt:{editor:['#prompt-textarea'],answer:['[data-message-author-role="assistant"]'],
      busy:['button[data-testid="stop-button"]','[data-is-streaming="true"]']},
    claude:{editor:['[contenteditable="true"].ProseMirror'],answer:['.font-claude-response'],
      busy:['[data-is-streaming="true"]','button[aria-label="Stop response"]']},
    gemini:{editor:['rich-textarea [contenteditable="true"]'],answer:['model-response .markdown','model-response message-content'],
      busy:['button.stop-button','button[aria-label="Stop response"]','button[aria-label="Stop generating"]']}
  };
  function aiState() {
    const p=A.platform(location.href),cfg=aiConfig[p];if(!cfg) throw Error('AI sahifasi emas.');
    const ed=first(cfg.editor),responses=[];
    for(const s of cfg.answer) { const es=all(s).filter(visible);if(es.length){responses.push(...es);break;} }
    const last=responses.at(-1);
    let busy=cfg.busy.some(s=>all(s).some(visible));
    busy ||= all('button').some(e=>visible(e)&&/^(stop generating|stop response|остановить генерацию|остановить ответ)$/i.test(label(e)));
    let container=last?.closest('article,model-response,[data-is-streaming]')||last?.parentElement?.parentElement;
    const complete=!!container && (container.getAttribute('data-is-streaming')==='false'||
      all('button,[role="button"]',container).some(e=>visible(e)&&
        /copy|копировать|nusxa|good response|bad response|thumb/i.test(label(e))));
    const alerts=all('[role="alert"]').filter(visible).map(text).join(' ');
    const limited=/usage limit|reached.{0,20}limit|too many requests|лимит.{0,25}(исчерпан|достигнут)/i.test(alerts);
    return {provider:p,ready:!!ed,answers:responses.length,text:text(last),busy,complete,limited};
  }
  async function submitted(p) {
    for(let i=0;i<20;i++) {
      await pause(250);
      const s=aiState(),ed=first(aiConfig[p].editor);
      if(s.busy||s.answers||!ed||!editorValue(ed)) return true;
    }
    return false;
  }
  async function aiSubmit(req) {
    const p=A.platform(location.href),state=aiState();
    if(!state.ready) throw Error('AI akkauntiga kiring.');
    if(state.answers) throw Error('Yangi AI suhbati ochilmadi.');
    const ed=first(aiConfig[p].editor);
    if(editorValue(ed)) throw Error('AI yozish katagi band.');
    await fill(ed,req.text);await pause(300);
    const button=await waitButton(ed,p,true);
    if(button) button.click(); else pressEnter(ed);
    if(await submitted(p)) return {submitted:true};
    if(button) {pressEnter(first(aiConfig[p].editor)||ed);if(await submitted(p)) return {submitted:true};}
    throw Error('AI so‘rovi yuborilmadi. Sahifani tekshiring.');
  }
  chrome.runtime.onMessage.addListener((req,sender,respond)=>{
    if(sender.id!==chrome.runtime.id||!req?.aiy) return;
    const methods={cancel:()=>{cancelled.add(req.jobId);return {cancelled:true};},ping:()=>({platform:A.platform(location.href)}),snapshot,discover,
      openThread:()=>openThread(req),
      socialSend:()=>socialSend(req),aiState,aiSubmit:()=>aiSubmit(req)};
    if(!methods[req.type]) return;
    Promise.resolve().then(methods[req.type]).then(data=>respond({ok:true,data}))
      .catch(e=>respond({ok:false,error:e.message}));
    return true;
  });
})();
