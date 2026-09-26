'use strict';
// Only explicitly marked application text is translated. Photo, album and path
// strings stay raw. Structured messages retain their parameters across switches.
const I18n=(()=>{
  const languages=[
    {code:'zh-CN',native:'简体中文',name:'拾光图库',short:'拾光'},
    {code:'en',native:'English',name:'Lightkeeper'},
    {code:'ja',native:'日本語',name:'ひかり帖'},
    {code:'ko',native:'한국어',name:'빛담'},
    {code:'fr',native:'Français',name:'Éclats'},
    {code:'de',native:'Deutsch',name:'Lichtmomente'},
    {code:'es',native:'Español',name:'Instantes'},
    {code:'pt',native:'Português',name:'Lume'},
    {code:'ru',native:'Русский',name:'Светопись'}
  ];
  let locale='zh-CN';
  try{const saved=localStorage.getItem('shiguang.language');if(languages.some(l=>l.code===saved))locale=saved}catch{}
  const bindings=new Map(),missing=new Set();
  class Value{constructor(render){this.render=render}toString(){return String(this.render())}[Symbol.toPrimitive](){return this.toString()}}
  const patterns=Object.keys(GALLERY_LOCALES.en).filter(k=>/\{\d+\}/.test(k)).map(key=>{
    const escaped=key.split(/(\{\d+\})/).map(x=>/^\{\d+\}$/.test(x)?'([\\s\\S]*?)':x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('');
    return {key,re:new RegExp('^'+escaped+'$')};
  });
  function message(key,...args){
    if(key instanceof Value)return key;
    key=String(key??'');
    if(!args.length&&!Object.hasOwn(GALLERY_LOCALES.en,key)&&/[\u3400-\u9fff]/.test(key)){
      const found=patterns.find(p=>p.re.test(key));
      if(found){const values=found.re.exec(key).slice(1).map(v=>Object.hasOwn(GALLERY_LOCALES.en,v)?message(v):v);return message(found.key,...values)}
    }
    return new Value(()=>{
      let template=locale==='zh-CN'?key:GALLERY_LOCALES[locale]?.[key]??GALLERY_LOCALES.en[key];
      if(template===undefined){template=key;if(/[\u3400-\u9fff]/.test(key))missing.add(key)}
      return template.replace(/\{(\d+)\}/g,(_,i)=>String(args[Number(i)]??'{'+i+'}'));
    });
  }
  function bind(node,property,value){
    if(!node)return value;
    let entries=bindings.get(node);
    if(value instanceof Value){if(!entries){entries=new Map();bindings.set(node,entries)}entries.set(property,value)}
    else if(entries){entries.delete(property);if(!entries.size)bindings.delete(node)}
    write(node,property,value);return value;
  }
  function write(node,property,value){
    const str=String(value??'');
    if(property==='text'){if(node.nodeType===3){if(node.nodeValue!==str)node.nodeValue=str}else if(node.textContent!==str)node.textContent=str}
    else if(node.getAttribute(property)!==str)node.setAttribute(property,str);
  }
  function concat(...values){return new Value(()=>values.map(v=>String(v??'')).join(''))}
  function date(value,mode='date'){
    return new Value(()=>{
      const parts=String(value||'').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
      if(!parts)return value;
      const d=new Date(+parts[1],+parts[2]-1,+parts[3],+(parts[4]||0),+(parts[5]||0));
      const options=mode==='date'?{year:'numeric',month:'long',day:'numeric'}:mode==='shorttime'?{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}:mode==='datetime'?{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}:{year:'numeric',month:'2-digit',day:'2-digit'};
      return new Intl.DateTimeFormat(locale==='pt'?'pt-PT':locale,options).format(d);
    });
  }
  function refresh(){
    document.documentElement.lang=locale;
    document.documentElement.dataset.language=locale;
    for(const [node,entries] of bindings){if(!node.isConnected){bindings.delete(node);continue}for(const [property,value] of entries)write(node,property,value)}
    const brand=languages.find(l=>l.code===locale);
    document.title=brand.name+' · v 1.0.3';
    document.getElementById('brandName').textContent=brand.short||brand.name;
    document.getElementById('brandTagline').textContent=String(message('照片图库'));
    document.getElementById('languageSelect').value=locale;
    document.documentElement.style.setProperty('--film-target-label',JSON.stringify(String(message('定位'))));
    document.documentElement.style.setProperty('--returned-photo-label',JSON.stringify(String(message('刚刚浏览'))));
  }
  function setLocale(code){if(!languages.some(l=>l.code===code))throw error(message('不支持此界面语言'));locale=code;try{localStorage.setItem('shiguang.language',code)}catch{}refresh()}
  function error(value){const localized=message(value),e=new Error(String(localized));e.localized=localized;return e}
  function errorText(e){return e?.localized||message(e?.message??e)}
  function metadata(key,value){
    // Camera and lens names are unmodified user/EXIF strings; enums and units are UI.
    if(['相机型号','镜头'].includes(key)&&value!=='未记录')return value;
    return message(value);
  }
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),nodes=[];let node;
  while(node=walker.nextNode())if(!node.parentElement.closest('script,style,[data-brand]')&&/[\u3400-\u9fff]/.test(node.nodeValue))nodes.push(node);
  for(const n of nodes){const raw=n.nodeValue,key=raw.trim();bind(n,'text',concat(raw.slice(0,raw.indexOf(key)),message(key),raw.slice(raw.indexOf(key)+key.length)))}
  for(const n of document.querySelectorAll('[title],[aria-label],[placeholder]'))for(const attr of ['title','aria-label','placeholder']){const value=n.getAttribute(attr);if(value&&/[\u3400-\u9fff]/.test(value))bind(n,attr,message(value))}
  const select=document.getElementById('languageSelect');
  for(const lang of languages){const option=document.createElement('option');option.value=lang.code;option.textContent=lang.native+' — '+lang.name;select.append(option)}
  const open=()=>{select.value=locale;document.getElementById('languageError').textContent='';document.getElementById('languageDialog').showModal();select.focus()};
  for(const dialog of document.querySelectorAll('dialog:not(#languageDialog):not(#viewer)')){
    const button=document.createElement('button');button.type='button';button.className='dialog-language';button.textContent='🌐';bind(button,'aria-label',message('语言 / Language'));bind(button,'title',message('语言 / Language'));button.onclick=open;dialog.prepend(button);
  }
  document.getElementById('languageButton').onclick=document.getElementById('viewerLanguageButton').onclick=open;
  select.onchange=async()=>{
    select.disabled=true;const previous=locale;
    try{const response=await fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json','X-Gallery-Request':'1'},body:JSON.stringify({language:select.value})});const result=await response.json();if(!response.ok)throw error(result.error);setLocale(result.language);document.getElementById('languageError').textContent=''}
    catch(e){select.value=previous;bind(document.getElementById('languageError'),'text',concat(message('无法保存语言设置，请重试。'),' ',errorText(e)))}
    finally{select.disabled=false}
  };
  window.addEventListener('storage',e=>{if(e.key==='shiguang.language'&&languages.some(l=>l.code===e.newValue)){locale=e.newValue;refresh()}});
  refresh();
  const ready=fetch('/api/preferences',{signal:AbortSignal.timeout(8000)}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(r=>setLocale(r.language)).catch(()=>refresh());
  // Prune detached bindings without observing or rewriting user-generated content.
  setInterval(()=>{for(const node of bindings.keys())if(!node.isConnected)bindings.delete(node)},10000);
  return {root:o=>o?.mode==='computer'?message('本机照片 · {0}',o.roots.join(', ')):o?.root,languages,missing,ready,message,text:(n,v)=>bind(n,'text',v),attr:bind,concat,date,error,errorText,metadata,setLocale,refresh,number:n=>new Value(()=>new Intl.NumberFormat(locale).format(Number(n||0))),get locale(){return locale}};
})();
const T=(key,...args)=>I18n.message(key,...args);
