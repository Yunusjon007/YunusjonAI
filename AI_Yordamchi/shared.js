(() => {
  if (globalThis.AIY?.version === 4) return;
  const norm = value => String(value ?? '').replace(/\u00a0/g,' ').replace(/[ \t]+/g,' ').trim();
  // Rich editors render each line as its own paragraph, so line breaks never
  // round-trip exactly. Compare typed and rendered text word by word instead.
  const flat = value => norm(value).replace(/\s+/g,' ').trim();
  function platform(url) {
    try {
      const h=new URL(url).hostname;
      return {'www.instagram.com':'instagram','www.facebook.com':'facebook',
        'www.messenger.com':'facebook','web.telegram.org':'telegram',
        'chatgpt.com':'chatgpt','claude.ai':'claude','gemini.google.com':'gemini'}[h] || '';
    } catch { return ''; }
  }
  function thread(url) {
    try {
      const u=new URL(url), p=platform(url);
      const regex=p==='instagram'? /^\/direct\/t\/([^/]+)/:
        p==='facebook'? /\/(?:messages\/)?t\/([^/]+)/:null;
      if(regex) { const m=u.pathname.match(regex); return m ? `${p}:${m[1]}` : ''; }
      // Negative peer ids are groups and channels; only private chats are answered.
      if(p==='telegram' && /^\/(a|k)\//.test(u.pathname) && u.hash.length>1 && !u.hash.startsWith('#-'))
        return `telegram:${u.pathname}:${u.hash}`;
    } catch {}
    return '';
  }
  function messagesPage(url) {
    try {
      const u=new URL(url),p=platform(url);
      if(p==='instagram') return u.pathname.startsWith('/direct/');
      if(p==='facebook') return u.hostname==='www.messenger.com'||u.pathname.startsWith('/messages');
      return p==='telegram' && /^\/(a|k)\//.test(u.pathname);
    } catch { return false; }
  }
  async function digest(value) {
    const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
    return Array.from(new Uint8Array(b),n=>n.toString(16).padStart(2,'0')).join('');
  }
  function geometryDirection(box,scope) {
    if(!scope.width || box.width>scope.width*.84 || box.width<2) return 'unknown';
    const left=box.left-scope.left, right=scope.right-box.right;
    if(left<0 || right<0 || Math.abs(left-right)<Math.max(35,scope.width*.12)) return 'unknown';
    return left<right ? 'incoming':'outgoing';
  }
  const sources={
    instagram:{name:'Instagram',url:'https://www.instagram.com/direct/inbox/'},
    facebook:{name:'Facebook',url:'https://www.facebook.com/messages/'},
    telegram:{name:'Telegram',url:'https://web.telegram.org/a/'},
    chatgpt:{name:'ChatGPT',url:'https://chatgpt.com/'},
    claude:{name:'Claude',url:'https://claude.ai/new'},
    gemini:{name:'Gemini',url:'https://gemini.google.com/app'}
  };
  const defaults={mode:'review',platforms:['instagram','facebook','telegram'],
    providers:['chatgpt','claude','gemini'],interval:30,maxThreads:20,
    rules:'Mijoz yozgan tilda qisqa, muloyim javob bering. Faqat tasdiqlangan ma’lumotlardan foydalaning. Narx, manzil yoki xizmat noma’lum bo‘lsa aniqlashtiring. O‘zingizni avtomatik yordamchi deb tanishtirishni yashirmang.\n\nBiznes ma’lumotlari: [shu yerga yozing]'};
  globalThis.AIY={version:4,norm,flat,platform,thread,messagesPage,digest,geometryDirection,sources,defaults};
})();
