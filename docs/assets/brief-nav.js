(function(){
  var prevA=[document.getElementById('navPrev'),document.getElementById('navPrevBottom')];
  var nextA=[document.getElementById('navNext'),document.getElementById('navNextBottom')];
  var toast=document.getElementById('toast'),hint=document.getElementById('swipeHint');
  function href(a){return a&&a.getAttribute('href')?a.getAttribute('href'):null;}
  function setNext(url){nextA.forEach(function(a){if(!a)return;if(url){a.setAttribute('href',url);a.removeAttribute('aria-disabled');}});}
  function say(m){if(!toast)return;toast.textContent=m;toast.classList.add('show');clearTimeout(say.t);say.t=setTimeout(function(){toast.classList.remove('show');},1400);}
  try{fetch('./nav.json?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(j){if(!j)return;if(j.next&&j.next.url)setNext(j.next.url);if(j.prev&&j.prev.url){prevA.forEach(function(a){if(a){a.setAttribute('href',j.prev.url);a.removeAttribute('aria-disabled');}});}else{prevA.forEach(function(a){if(a){a.removeAttribute('href');a.setAttribute('aria-disabled','true');}});}}).catch(function(){});}catch(e){}
  function go(dir){var a=dir<0?prevA[0]:nextA[0];var u=href(a);if(u){location.href=u;}else{say(dir<0?'이전 거래일이 없습니다':'다음 거래일이 아직 없습니다');}}
  function blocked(t){while(t&&t!==document.body){if(t.tagName==='A'||t.tagName==='BUTTON'||t.tagName==='SVG'||t.tagName==='svg'||(t.classList&&(t.classList.contains('tw')||t.classList.contains('chart'))))return true;t=t.parentNode;}return false;}
  var sx=0,sy=0,st=0,on=false;
  function begin(e){var p=e.touches?e.touches[0]:e;if(!p||blocked(e.target)){on=false;return;}on=true;sx=p.clientX;sy=p.clientY;st=Date.now();}
  function end(e){if(!on)return;on=false;var p=e.changedTouches?e.changedTouches[0]:e;if(!p)return;var dx=p.clientX-sx,dy=p.clientY-sy,dt=Date.now()-st;if(dt>900||Math.abs(dx)<90||Math.abs(dx)<Math.abs(dy)*1.4)return;var sel=window.getSelection?String(window.getSelection()):'';if(sel&&sel.trim())return;go(dx<0?1:-1);}
  document.addEventListener('touchstart',begin,{passive:true});document.addEventListener('touchend',end,{passive:true});
  if(window.PointerEvent){document.addEventListener('pointerdown',function(e){if(e.pointerType==='mouse')begin(e);},{passive:true});document.addEventListener('pointerup',function(e){if(e.pointerType==='mouse')end(e);},{passive:true});}
  document.addEventListener('keydown',function(e){if(e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;if(e.key==='ArrowLeft')go(-1);else if(e.key==='ArrowRight')go(1);});
  try{if(hint&&('ontouchstart' in window)&&!sessionStorage.getItem('gfb_hint')){hint.classList.add('show');sessionStorage.setItem('gfb_hint','1');setTimeout(function(){hint.classList.remove('show');},4000);}}catch(e){}
  // 홈 화면 앱 — 사이트 루트 서비스워커(캐시 없음, 설치 가능 조건용) 등록
  try{var ixs=(document.getElementById('navRow')||{getAttribute:function(){return '';}}).getAttribute('data-index')||'';var base=(ixs&&ixs.indexOf('/i/')>0)?ixs.slice(0,ixs.indexOf('/i/')+1):'';if(base&&'serviceWorker' in navigator)navigator.serviceWorker.register(base+'sw.js',{scope:base}).catch(function(){});}catch(e){}
  // 날짜 선택 — 토큰 경로의 dates.json(게시 때마다 갱신)을 읽어 드롭다운 채움. 못 읽으면 숨김.
  var row=document.getElementById('navRow'),pick=document.getElementById('datePick');
  var ix=row?row.getAttribute('data-index'):'';
  // (§22 D-22p) 안전망 — nav.json 이 어긋나 이전/다음이 비어 있으면 dates.json(최신 먼저, 같은 날짜 am→pm)에서 이웃 날짜를 찾아 채운다
  function fillFromIndex(list){var cd=row.getAttribute('data-date')||'';if(!cd)return;var nxt=null,prv=null;for(var i=0;i<list.length;i++){var d=list[i];if(d.date>cd){if(!nxt||d.date<nxt.date||(d.date===nxt.date&&d.edition==='am'))nxt=d;}else if(d.date<cd){if(!prv||d.date>prv.date||(d.date===prv.date&&d.edition==='am'))prv=d;}}
    if(nxt&&!href(nextA[0]))setNext(nxt.url);if(prv&&!href(prevA[0]))prevA.forEach(function(a){if(a){a.setAttribute('href',prv.url);a.removeAttribute('aria-disabled');}});}
  if(pick&&ix){try{fetch(ix+'?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(j){if(!j||!j.dates||!j.dates.length){pick.style.display='none';return;}var cur=row.getAttribute('data-date')+'|'+row.getAttribute('data-edition');pick.innerHTML='';j.dates.forEach(function(d){var o=document.createElement('option');o.value=d.url;o.textContent=d.date.slice(5)+'('+d.weekday+')'+(d.edition==='pm'?' 오후 잠정':'');if(d.date+'|'+d.edition===cur)o.selected=true;pick.appendChild(o);});setTimeout(function(){fillFromIndex(j.dates);},600);}).catch(function(){pick.style.display='none';});}catch(e){pick.style.display='none';}
    pick.addEventListener('change',function(){if(pick.value)location.href=pick.value;});}
  else if(pick&&row){pick.innerHTML='';var o=document.createElement('option');o.textContent=(row.getAttribute('data-date')||'').slice(5)+(row.getAttribute('data-edition')==='pm'?' 오후 잠정':'');pick.appendChild(o);pick.disabled=true;}
})();