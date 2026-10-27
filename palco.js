/* Palco · aba de animação PNGtuber da Ficha Tamaki
   - camadas PNG editáveis uma a uma (posição, tamanho, giro, pivô, papel, animação)
   - fala: Termux (Kokoro) -> app, voz do navegador ou arquivo de áudio
   - a boca/movimento reagem ao volume da voz */
(()=>{
'use strict';
const q=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const KEY='palco-cfg';
const CMD=()=>{const b=new URL('.',location.href).href;return 'cd ~ && curl -fsSL '+b+'instalar-voz.sh -o instalar-voz.sh && bash instalar-voz.sh '+b};
const DEF={url:'http://127.0.0.1:8765',motor:'termux',voice:'pf_dora',speed:1.05,pause:0.4,bg:'check',gain:4,thr:0.15,guides:1,cap:1,caph:24,capsz:3.2,text:'',layers:[],sel:null};
const ROLES=[['always','Sempre visível'],['open','Boca aberta (só falando)'],['closed','Boca fechada (só parada)'],['eyeopen','Olho aberto (some ao piscar)'],['eyeclosed','Olho fechado (só ao piscar)']];
const IDLE=[['none','Nenhuma'],['bob','Flutuar'],['sway','Balançar'],['breathe','Respirar'],['flicker','Cintilar (brilho)']];
const TALK=[['none','Nenhuma'],['hop','Pular'],['shake','Tremer'],['grow','Esticar'],['tilt','Inclinar']];
const BGS=[['check','Transparente (xadrez)'],['chroma','Verde chroma'],['app','Roxo do app']];
let cfg=JSON.parse(JSON.stringify(DEF)),urls={},root=null,stage=null,els={},raf=0,T=0,tm,ready;

/* ---------- armazenamento (imagens no IndexedDB, ajustes no localStorage) ---------- */
const idb=()=>new Promise((ok,no)=>{const r=indexedDB.open('palco',1);r.onupgradeneeded=()=>r.result.createObjectStore('img');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});
const idbPut=async(k,v)=>{const d=await idb();return new Promise((ok,no)=>{const t=d.transaction('img','readwrite');t.objectStore('img').put(v,k);t.oncomplete=ok;t.onerror=()=>no(t.error)})};
const idbGet=async k=>{const d=await idb();return new Promise((ok,no)=>{const r=d.transaction('img').objectStore('img').get(k);r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)})};
const idbDel=async k=>{const d=await idb();return new Promise(ok=>{const t=d.transaction('img','readwrite');t.objectStore('img').delete(k);t.oncomplete=ok;t.onerror=ok})};
function saveCfg(){clearTimeout(tm);tm=setTimeout(()=>{try{localStorage.setItem(KEY,JSON.stringify(cfg))}catch(e){}},400)}
const uid=()=>Math.random().toString(36).slice(2,9);
const layer=()=>cfg.layers.find(l=>l.id==cfg.sel);



/* ---------- áudio + análise de volume ---------- */
let capText='',capStart=0,capDur=1,ac,an,buf,cur=null,sp=false,fake=0,lvl=0,nextBlink=0,blinkEnd=0;
function ctx(){
  if(!ac){ac=new (window.AudioContext||window.webkitAudioContext)();an=ac.createAnalyser();an.fftSize=512;buf=new Uint8Array(an.fftSize);an.connect(ac.destination)}
  if(ac.state=='suspended')ac.resume();return ac}
document.addEventListener('pointerdown',()=>{try{ctx()}catch(e){}},{passive:true});
function pararAtual(){if(cur){const s=cur;cur=null;try{s.stop()}catch(e){}}if(window.speechSynthesis)speechSynthesis.cancel();sp=false}
function parar(){queue.length=0;capText='';pararAtual()}
function legenda(t,ms){capText=t||'';capStart=performance.now();capDur=Math.max(ms,500)}
function tocar(blob,txt){return new Promise(async(ok,no)=>{try{
  const c=ctx(),ab=await c.decodeAudioData(await blob.arrayBuffer());pararAtual();legenda(txt,ab.duration*1000);
  const s=c.createBufferSource();s.buffer=ab;s.connect(an);cur=s;s.onended=()=>{if(cur===s)cur=null;ok()};s.start()}catch(e){no(e)}})}
function navegador(t){return new Promise(ok=>{
  if(!window.speechSynthesis)return ok();
  const u=new SpeechSynthesisUtterance(t);u.lang='pt-BR';
  const v=speechSynthesis.getVoices().find(v=>/pt[-_]BR/i.test(v.lang));if(v)u.voice=v;
  u.rate=cfg.speed||1;u.onstart=()=>{sp=true;legenda(t,t.length*70/(cfg.speed||1))};u.onend=u.onerror=()=>{sp=false;ok()};speechSynthesis.speak(u)})}
const queue=[];let busy=false;
function falar(t){t=(t||'').trim();if(!t)return;queue.push(t);pump()}
async function pump(){if(busy)return;busy=true;
  while(queue.length){const t=queue.shift();try{await dizer(t)}catch(e){aviso('erro: '+(e.message||e))}}
  busy=false}
async function dizer(t){
  if(cfg.motor=='termux'){
    try{
      const r=await fetch(cfg.url+'/tts',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({text:t,voice:cfg.voice,speed:cfg.speed,pause:cfg.pause})});
      if(!r.ok)throw new Error('servidor '+r.status);
      return await tocar(await r.blob(),t);
    }catch(e){aviso('Termux sem voz ('+(e.message||'sem conexão')+'). Usando a voz do navegador.')}
  }
  await navegador(t)
}
function aviso(t){const el=root&&q('#pk-msg',root);if(el)el.textContent=t}

/* ---------- Termux -> app (eventos) ---------- */
let es=null,esUrl='',online=false;
function badge(){const el=root&&q('#pk-badge',root);if(el)el.textContent=online?'Termux: conectado':'Termux: desconectado'}
function conectar(){
  if(es&&esUrl==cfg.url)return;if(es)es.close();esUrl=cfg.url;online=false;badge();
  try{es=new EventSource(cfg.url+'/events')}catch(e){return}
  es.onopen=()=>{online=true;badge()};es.onerror=()=>{online=false;badge()};
  es.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.cmd=='stop')parar();else if(d.text)falar(d.text)}catch(_){}}
}
async function testar(){
  aviso('testando…');
  try{const r=await fetch(cfg.url+'/ping'),d=await r.json();
    const vs=[d.kokoro&&'Kokoro',...(d.piper||[]).map(n=>n+' (treinada)')].filter(Boolean);aviso(vs.length?'Servidor ok, vozes prontas: '+vs.join(', ')+'.':'Servidor ok, mas sem voz: vai usar a voz do navegador.')}
  catch(e){aviso('Não achei o servidor. Ele está rodando no Termux?')}}

/* ---------- camadas ---------- */
async function addFiles(files){
  for(const f of files){
    if(!/^image\//.test(f.type))continue;
    const id=uid(),img=uid();
    await idbPut(img,f);urls[img]=URL.createObjectURL(f);
    cfg.layers.push({id,img,name:f.name.replace(/\.[^.]+$/,''),x:50,y:50,w:50,r:0,px:.5,py:.5,vis:1,flip:0,role:'always',idle:'none',ia:3,is:1,talk:'none',ta:5});
    cfg.sel=id}
  saveCfg();build();drawList();drawPanel()}
function build(){
  if(!stage)return;stage.innerHTML='';els={};
  cfg.layers.forEach((L,i)=>{
    const e=document.createElement('img');e.src=urls[L.img]||'';e.alt=L.name;e.draggable=false;e.dataset.id=L.id;
    e.style.cssText='position:absolute;left:0;top:0;transform-origin:0 0;user-select:none;-webkit-user-drag:none;z-index:'+i;
    stage.appendChild(e);els[L.id]=e});
  const c=document.createElement('div');c.id='pk-cap';c.appendChild(document.createElement('span'));stage.appendChild(c);
  const d=document.createElement('div');d.id='pk-pv';stage.appendChild(d)}
function select(id){cfg.sel=id;drawList();drawPanel();saveCfg()}
async function removeLayer(L){
  cfg.layers=cfg.layers.filter(x=>x!=L);
  if(!cfg.layers.some(x=>x.img==L.img)){await idbDel(L.img);if(urls[L.img]){URL.revokeObjectURL(urls[L.img]);delete urls[L.img]}}
  cfg.sel=cfg.layers.length?cfg.layers[cfg.layers.length-1].id:null;
  saveCfg();build();drawList();drawPanel()}
function move(L,d){const i=cfg.layers.indexOf(L),j=i+d;if(j<0||j>=cfg.layers.length)return;
  [cfg.layers[i],cfg.layers[j]]=[cfg.layers[j],cfg.layers[i]];saveCfg();build();drawList()}

/* ---------- animação (roda a ~60 quadros/s enquanto a aba está aberta) ---------- */
function tick(now){
  raf=requestAnimationFrame(tick);if(!stage)return;
  const t=now/1000,W=stage.clientWidth,H=stage.clientHeight;
  let alvo=0;
  if(cur&&an){an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const d=(buf[i]-128)/128;s+=d*d}alvo=Math.min(1,Math.sqrt(s/buf.length)*cfg.gain)}
  else if(sp)alvo=.45+.4*Math.abs(Math.sin(t*13));
  else if(now<fake)alvo=.5+.5*Math.sin(t*9);
  lvl+=(alvo-lvl)*.45;
  const falando=lvl>cfg.thr;
  if(now>nextBlink){blinkEnd=now+140;nextBlink=now+2500+Math.random()*3000}
  const pisca=now<blinkEnd;
  const cp=q('#pk-cap',stage);
  if(cp){cp.style.display=cfg.cap?'flex':'none';cp.style.height=cfg.caph+'%';cp.style.fontSize=(W*cfg.capsz/100)+'px';
    let txt='',ph=false;
    if(capText){const el=now-capStart;if(el>capDur+2500)capText='';else txt=capText.slice(0,Math.floor(capText.length*Math.min(1,el/capDur)))}
    if(!capText&&cfg.guides){txt='A fala da Tamaki aparece aqui.';ph=true}
    if(cp.dataset.t!==txt){cp.dataset.t=txt;cp.firstChild.textContent=txt}
    cp.style.opacity=ph?.45:1}
  cfg.layers.forEach(L=>{
    const e=els[L.id];if(!e)return;
    let show=!!L.vis;
    if(show){if(L.role=='open')show=falando;else if(L.role=='closed')show=!falando;else if(L.role=='eyeopen')show=!pisca;else if(L.role=='eyeclosed')show=pisca}
    e.style.display=show?'':'none';if(!show)return;
    let dx=0,dy=0,dr=0,ds=1,op=1;const k=L.is*2;
    if(L.idle=='bob')dy+=Math.sin(t*k)*L.ia*.5;
    else if(L.idle=='sway')dr+=Math.sin(t*k)*L.ia;
    else if(L.idle=='breathe')ds+=Math.sin(t*k)*L.ia/100;
    else if(L.idle=='flicker')op=1-(L.ia/10)*(.5+.5*Math.sin(t*k*3+Math.sin(t*k*7)));
    if(L.talk=='hop')dy-=lvl*L.ta;
    else if(L.talk=='shake')dx+=(Math.random()-.5)*lvl*L.ta;
    else if(L.talk=='grow')ds+=lvl*L.ta/100;
    else if(L.talk=='tilt')dr+=Math.sin(t*12)*lvl*L.ta;
    e.style.width=L.w+'%';e.style.opacity=op;
    e.style.transform=`translate(${(L.x+dx)/100*W}px,${(L.y+dy)/100*H}px) rotate(${L.r+dr}deg) scale(${(L.flip?-1:1)*ds},${ds}) translate(${-L.px*100}%,${-L.py*100}%)`;
    e.classList.toggle('pk-sel',!!cfg.guides&&L.id==cfg.sel);
    if(L.id==cfg.sel){const p=q('#pk-pv',stage);if(p){p.style.display=cfg.guides?'block':'none';p.style.left=(L.x+dx)/100*W+'px';p.style.top=(L.y+dy)/100*H+'px'}}
  });
  if(!layer()){const p=q('#pk-pv',stage);if(p)p.style.display='none'}
}

/* ---------- interface ---------- */
function css(){if(q('#pk-css'))return;const s=document.createElement('style');s.id='pk-css';s.textContent=`
.pk-st{position:relative;aspect-ratio:9/16;width:min(100%,calc(68vh*9/16));margin:12px auto 0;overflow:hidden;border:1px solid var(--ln);border-radius:10px;touch-action:none}
.pk-check{background:conic-gradient(#3a3560 25%,#2a2650 0 50%,#3a3560 0 75%,#2a2650 0) 0 0/24px 24px}
.pk-chroma{background:#00b140}.pk-app{background:#0d0b1e}
.pk-st img.pk-sel{outline:1px dashed var(--te)}
#pk-pv{position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:2px solid var(--ac);background:#0008;pointer-events:none;z-index:999;display:none}
.pk-f{display:block;margin:10px 0}.pk-f span{display:flex;justify-content:space-between;font-weight:800;font-size:14px;color:var(--mu)}
.pk-f input[type=range]{padding:0}
.pk-l{display:flex;gap:6px;margin:6px 0}.pk-l .n{flex:1;text-align:left;background:none;border:1px solid var(--ln);border-radius:6px;padding:8px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pk-l .n.on{border-color:var(--ac);color:var(--ac)}.pk-l .x{width:38px}
details summary{cursor:pointer;font-weight:800;color:var(--mu);margin-top:12px}
.pk-file{cursor:pointer;display:inline-block}
#pk-cap{position:absolute;left:3%;right:3%;bottom:3%;box-sizing:border-box;padding:2.5% 3.5%;background:#06050f;color:#fff;border:4px double #fff;border-radius:4px;z-index:900;overflow:hidden;pointer-events:none;align-items:flex-start;font-family:'Press Start 2P',ui-monospace,monospace;line-height:1.8;white-space:pre-wrap}`;document.head.appendChild(s)}
const opt=(a,v)=>a.map(([k,n])=>`<option value="${k}"${k==v?' selected':''}>${n}</option>`).join('');
const rg=(k,l,min,max,st,v,at='k')=>`<label class="pk-f"><span>${l}<b data-v="${k}">${v}</b></span><input type="range" data-${at}="${k}" min="${min}" max="${max}" step="${st}" value="${v}"></label>`;
const sel=(k,l,a,v,at='k')=>`<label class="pk-f"><span>${l}</span><select data-${at}="${k}">${opt(a,v)}</select></label>`;
function html(){return `
<div class="c"><div class="ab" style="justify-content:space-between"><b>Palco</b><span id="pk-badge" class="m"></span></div>
<div id="pk-st" class="pk-st pk-${cfg.bg}"></div>
<div class="ab" style="margin-top:10px"><label>Fundo <select data-c="bg" style="width:auto">${opt(BGS,cfg.bg)}</select></label>
<label><input type="checkbox" data-c="guides" ${cfg.guides?'checked':''}> Guias</label><button class="g" data-a="test">Testar movimento</button></div></div>
<div class="c"><b>Fala</b>
<textarea id="pk-tx" data-c="text" placeholder="O que a Tamaki vai falar. Uma frase por linha." style="margin:10px 0">${esc(cfg.text)}</textarea>
<div class="ab"><button class="b" data-a="speak">Falar</button><button class="g" data-a="stop">Parar</button>
<label class="g pk-file">Tocar áudio…<input type="file" accept="audio/*" hidden data-a="audio"></label></div>
<p id="pk-msg" class="m"></p>
<details><summary>Instalar ou reinstalar a voz no Termux</summary>
<p class="m">1) Toque em Copiar. 2) Abra o Termux, segure o dedo na tela e escolha Colar. 3) Aperte Enter e espere terminar.</p>
<textarea id="pk-cmd" readonly rows="4" style="margin:8px 0">${esc(CMD())}</textarea>
<div class="ab"><button class="b" data-a="cmd">Copiar comando</button></div>
<p class="m">Depois de instalado, para atualizar basta digitar <code>voz --atualizar</code> no Termux.</p></details>
<details><summary>Treinar a voz própria da Tamaki (Piper)</summary>
<p class="m">Grave as frases no <a href="gravador.html">Gravador de voz</a>, treine no notebook (Colab ou Kaggle, grátis) e depois rode <code>voz --importar</code> no Termux. Para usar aqui, escreva <code>piper</code> no campo Voz.</p></details>
<details><summary>Voz e conexão com o Termux</summary>
${sel('motor','Motor de voz',[['termux','Termux (Kokoro ou voz treinada)'],['browser','Voz do navegador']],cfg.motor,'c')}
<label class="pk-f"><span>Endereço do servidor</span><input data-c="url" value="${esc(cfg.url)}" inputmode="url"></label>
<label class="pk-f"><span>Voz (piper = Tamaki treinada, ou id do Kokoro, ex.: pf_dora)</span><input data-c="voice" value="${esc(cfg.voice)}"></label>
${rg('speed','Velocidade',.6,1.5,.05,cfg.speed,'c')}${rg('pause','Pausa entre frases (s)',0,1.5,.05,cfg.pause,'c')}
<button class="g" data-a="ping">Testar conexão</button>
<p class="m">No Termux, <code>falar "oi gente"</code> manda o texto para cá e a Tamaki fala.</p></details></div>
<div class="c"><b>Camadas</b><p class="m">Toque na peça no palco para selecionar e arraste para mover. A de baixo da lista fica atrás.</p>
<div id="pk-list"></div><div class="ab" style="margin-top:10px"><label class="b pk-file">+ PNG<input type="file" accept="image/*" multiple hidden data-a="add"></label></div></div>
<div class="c" id="pk-panel"></div>
<div class="c"><b>Caixa de diálogo</b><label><input type="checkbox" data-c="cap" ${cfg.cap?'checked':''}> Mostrar legenda</label>${rg('caph','Altura da caixa (%)',8,45,1,cfg.caph,'c')}${rg('capsz','Tamanho da letra',1.5,6,.1,cfg.capsz,'c')}<p class="m">A legenda aparece letra por letra junto com a voz.</p></div>
<div class="c"><b>Sensibilidade da voz</b>${rg('thr','Limiar da boca',0.02,0.6,.01,cfg.thr,'c')}${rg('gain','Ganho do volume',1,12,.5,cfg.gain,'c')}
<div class="ab" style="margin-top:10px"><button class="g" data-a="export">Exportar palco</button><label class="g pk-file">Importar palco<input type="file" accept=".json,application/json" hidden data-a="import"></label></div>
<p class="m">As imagens ficam guardadas neste aparelho. Exporte para ter cópia de segurança.</p></div>`}
function drawList(){const el=root&&q('#pk-list',root);if(!el)return;
  el.innerHTML=cfg.layers.length?[...cfg.layers].reverse().map(L=>`<div class="pk-l"><button class="n${L.id==cfg.sel?' on':''}" data-a="sel" data-id="${L.id}">${esc(L.name)}</button><button class="x" data-a="vis" data-id="${L.id}" aria-label="Mostrar ou ocultar">${L.vis?'●':'○'}</button><button class="x" data-a="up" data-id="${L.id}" aria-label="Subir">▲</button><button class="x" data-a="down" data-id="${L.id}" aria-label="Descer">▼</button></div>`).join(''):'<p class="m">Nenhuma peça ainda. Adicione os PNGs da Tamaki (corpo, cabeça, olhos, boca…).</p>'}
function drawPanel(){const el=root&&q('#pk-panel',root);if(!el)return;const L=layer();
  if(!L){el.innerHTML='<p class="m">Selecione uma peça para editar.</p>';return}
  el.innerHTML=`<b>Editar: ${esc(L.name)}</b>
<label class="pk-f"><span>Nome</span><input data-k="name" value="${esc(L.name)}"></label>
${rg('x','Posição horizontal (%)',-20,120,.1,L.x)}${rg('y','Posição vertical (%)',-20,120,.1,L.y)}
${rg('w','Tamanho (% da largura)',2,200,.5,L.w)}${rg('r','Rotação (graus)',-180,180,1,L.r)}
${rg('px','Pivô horizontal',0,1,.01,L.px)}${rg('py','Pivô vertical',0,1,.01,L.py)}
<p class="m">Pivô é o ponto fixo da peça (bolinha laranja). Cabeça balança em volta do pescoço, por exemplo.</p>
<label><input type="checkbox" data-k="flip" ${L.flip?'checked':''}> Espelhar</label>
${sel('role','Papel da peça',ROLES,L.role)}
<b>Parada</b>${sel('idle','Animação',IDLE,L.idle)}${rg('ia','Intensidade',0,10,.1,L.ia)}${rg('is','Velocidade',.2,4,.1,L.is)}
<b>Falando</b>${sel('talk','Animação',TALK,L.talk)}${rg('ta','Intensidade',0,20,.5,L.ta)}
<div class="ab" style="margin-top:10px"><button class="g" data-a="dup">Duplicar</button><button class="g" data-a="del">Excluir peça</button></div>`}
function setLabel(k,v){const b=root&&q(`b[data-v="${k}"]`,root);if(b)b.textContent=v}

function bind(){
  root.onclick=async e=>{
    const b=e.target.closest('button[data-a]');if(!b)return;const a=b.dataset.a,L=cfg.layers.find(l=>l.id==b.dataset.id)||layer();
    if(a=='sel')select(b.dataset.id);
    else if(a=='vis'&&L){L.vis=L.vis?0:1;saveCfg();drawList()}
    else if(a=='up'&&L)move(L,1);else if(a=='down'&&L)move(L,-1);
    else if(a=='dup'&&L){const n=Object.assign({},L,{id:uid(),name:L.name+' 2',x:L.x+3,y:L.y+3});cfg.layers.splice(cfg.layers.indexOf(L)+1,0,n);cfg.sel=n.id;saveCfg();build();drawList();drawPanel()}
    else if(a=='del'&&L){if(!b.dataset.s){b.dataset.s=1;b.textContent='Toque de novo para excluir';return}await removeLayer(L)}
    else if(a=='speak'){ctx();falar(q('#pk-tx',root).value)}
    else if(a=='stop')parar();
    else if(a=='test')fake=performance.now()+4000;
    else if(a=='ping')testar();
    else if(a=='cmd'){const t=q('#pk-cmd',root);t.focus();t.select();t.setSelectionRange(0,t.value.length);let ok=false;try{await navigator.clipboard.writeText(t.value);ok=true}catch(x){try{ok=document.execCommand('copy')}catch(y){}}aviso(ok?'Comando copiado. Cole no Termux.':'Não consegui copiar sozinho. O texto está selecionado: use Copiar no teclado.')}
    else if(a=='export')exportar();
  };
  const h=async e=>{
    const t=e.target,d=t.dataset;
    if(t.type=='file'){if(e.type!='change')return;const f=t.files;
      if(d.a=='add')await addFiles(f);
      else if(d.a=='audio'&&f[0]){ctx();aviso('tocando '+f[0].name);try{await tocar(f[0])}catch(x){aviso('não consegui tocar esse arquivo')}}
      else if(d.a=='import'&&f[0])await importar(f[0]);
      t.value='';return}
    if(d.c){const k=d.c;let v=t.type=='checkbox'?(t.checked?1:0):(t.type=='range'?parseFloat(t.value):t.value);
      cfg[k]=v;setLabel(k,v);
      if(k=='bg')stage.className='pk-st pk-'+v;
      if(k=='url'){clearTimeout(h.u);h.u=setTimeout(conectar,600)}
      saveCfg()}
    else if(d.k){const L=layer();if(!L)return;const k=d.k;
      L[k]=t.type=='checkbox'?(t.checked?1:0):(t.type=='range'?parseFloat(t.value):t.value);
      setLabel(k,L[k]);
      if(k=='name'){const n=q(`.n[data-id="${L.id}"]`,root);if(n)n.textContent=L.name}
      saveCfg()}
  };
  root.oninput=h;root.onchange=h;
  let drag=null;
  stage.onpointerdown=e=>{
    const im=e.target.closest('img[data-id]');if(im&&im.dataset.id!=cfg.sel)select(im.dataset.id);
    const L=layer();if(!L)return;
    drag={x:e.clientX,y:e.clientY,lx:L.x,ly:L.y};stage.setPointerCapture(e.pointerId)};
  stage.onpointermove=e=>{if(!drag)return;const L=layer();if(!L)return;
    L.x=+(drag.lx+(e.clientX-drag.x)/stage.clientWidth*100).toFixed(1);
    L.y=+(drag.ly+(e.clientY-drag.y)/stage.clientHeight*100).toFixed(1);
    ['x','y'].forEach(k=>{const i=q(`input[data-k="${k}"]`,root);if(i)i.value=L[k];setLabel(k,L[k])})};
  stage.onpointerup=stage.onpointercancel=()=>{if(drag){drag=null;saveCfg()}};
}

/* ---------- backup ---------- */
const toData=b=>new Promise(ok=>{const r=new FileReader();r.onload=()=>ok(r.result);r.readAsDataURL(b)});
async function exportar(){
  const imgs={};for(const L of cfg.layers)if(!imgs[L.img]){const b=await idbGet(L.img);if(b)imgs[L.img]=await toData(b)}
  const j=JSON.stringify({palco:1,cfg:Object.assign({},cfg,{url:undefined,motor:undefined}),imgs});
  const u=URL.createObjectURL(new Blob([j],{type:'application/json'})),a=document.createElement('a');
  a.href=u;a.download='palco-tamaki.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),4000);aviso('palco exportado')}
async function importar(f){
  try{const o=JSON.parse(await f.text());if(!o.palco||!Array.isArray(o.cfg.layers))throw 0;
    for(const k in o.imgs){const b=await (await fetch(o.imgs[k])).blob();await idbPut(k,b);urls[k]=URL.createObjectURL(b)}
    const keep={url:cfg.url,motor:cfg.motor};cfg=Object.assign({},DEF,o.cfg,keep);
    saveCfg();root.innerHTML=html();stage=q('#pk-st',root);build();bind();drawList();drawPanel();badge();aviso('palco importado')}
  catch(e){aviso('arquivo inválido')}}

/* ---------- montagem (chamada pela aba) ---------- */
async function mount(el){
  const tok=++T;
  try{
    await ready;if(tok!==T)return;
    css();root=el;el.innerHTML=html();stage=q('#pk-st',el);
    build();bind();drawList();drawPanel();badge();
    cancelAnimationFrame(raf);raf=requestAnimationFrame(tick)
  }catch(e){el.innerHTML='<div class="c"><b>Erro no Palco</b><p class="m">'+esc(e&&e.message||e)+'</p></div>'}}
function unmount(){T++;cancelAnimationFrame(raf);raf=0;root=null;stage=null;els={}}
ready=(async()=>{
  try{const s=localStorage.getItem(KEY);if(s)cfg=Object.assign({},DEF,JSON.parse(s))}catch(e){}
  for(const L of cfg.layers){try{const b=await idbGet(L.img);if(b&&!urls[L.img])urls[L.img]=URL.createObjectURL(b)}catch(e){}}
  try{conectar()}catch(e){}
})();
window.Palco={mount,unmount,falar,parar};
})();
