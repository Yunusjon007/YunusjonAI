(() => {
  if(globalThis.__AIY_CONTENT__) return;
  globalThis.__AIY_CONTENT__=true;
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
  function fill(ed,value) {
    ed.focus();
    if(ed instanceof HTMLTextAreaElement || ed instanceof HTMLInputElement) {
      const proto=ed instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(ed,value);
      ed.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));
    } else {
      const sel=getSelection(),range=document.createRange();range.selectNodeContents(ed);
      sel.removeAllRanges();sel.addRange(range);
      if(!document.execCommand('insertText',false,value)) throw Error('Matnni yozish amalga oshmadi.');
    }
    if(editorValue(ed)!==A.norm(value)) throw Error('Yozilgan matn tasdiqlanmadi. Chatni tekshiring.');
  }
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
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
  async function socialSend(req) {
    if(cancelled.has(req.jobId))return {status:'cancelled'};
    let before=await snapshot();
    if(before.signature!==req.signature||before.key!==req.key) throw Error('Suhbat o‘zgargan. Javob yangilanishi kerak.');
    if(!before.sendable) throw Error('Oxirgi xabar kiruvchi matn sifatida tanilmadi.');
    const ed=editor(before.platform);
    if(editorValue(ed)) throw Error('Chatda qoralama bor. Uni o‘zgartirmadim.');
    if(!req.text||req.text.length>3000) throw Error('Javob 1–3000 belgidan iborat bo‘lsin.');
    if(cancelled.has(req.jobId))return {status:'cancelled'};
    // Persisted sending state is owned by the dashboard before this side effect.
    fill(ed,req.text);
    if(req.draftOnly) return {status:'drafted'};
    await pause(250);
    if(cancelled.has(req.jobId)){
      if(editorValue(ed)===A.norm(req.text))fill(ed,'');
      return {status:'cancelled'};
    }
    const now=await snapshot();
    if(now.signature!==req.signature || now.key!==req.key) {
      if(editorValue(ed)===A.norm(req.text)) fill(ed,'');
      throw Error('Yangi xabar keldi. Yuborish bekor qilindi.');
    }
    const button=sendButton(ed,before.platform);
    if(!button) return {status:'drafted',note:'Yuborish tugmasi tanilmadi. Javob chatga qo‘yildi; qo‘lda yuboring.'};
    if(cancelled.has(req.jobId)){
      if(editorValue(ed)===A.norm(req.text))fill(ed,'');
      return {status:'cancelled'};
    }
    button.click();
    for(let i=0;i<12;i++) {
      await pause(750);
      try {
        const after=await snapshot();
        if(after.key!==req.key) return {status:'uncertain'};
        if(after.rows.some(r=>r.direction==='outgoing'&&A.norm(r.text)===A.norm(req.text)&&
          !before.rows.some(o=>o.id===r.id&&o.text===r.text&&o.direction===r.direction))) return {status:'sent'};
      } catch {}
    }
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
  async function aiSubmit(req) {
    const p=A.platform(location.href),state=aiState();
    if(!state.ready) throw Error('AI akkauntiga kiring.');
    if(state.answers) throw Error('Yangi AI suhbati ochilmadi.');
    const ed=first(aiConfig[p].editor);
    if(editorValue(ed)) throw Error('AI yozish katagi band.');
    fill(ed,req.text);await pause(300);
    const button=sendButton(ed,p,true);if(!button) throw Error('AI yuborish tugmasi tanilmadi.');
    button.click();return {submitted:true};
  }
  chrome.runtime.onMessage.addListener((req,sender,respond)=>{
    if(sender.id!==chrome.runtime.id||!req?.aiy) return;
    const methods={cancel:()=>{cancelled.add(req.jobId);return {cancelled:true};},ping:()=>({platform:A.platform(location.href)}),snapshot,discover,
      socialSend:()=>socialSend(req),aiState,aiSubmit:()=>aiSubmit(req)};
    if(!methods[req.type]) return;
    Promise.resolve().then(methods[req.type]).then(data=>respond({ok:true,data}))
      .catch(e=>respond({ok:false,error:e.message}));
    return true;
  });
})();
