// Mude o número da versão quando atualizar os arquivos do app.
const V='tamaki-v7',CORE=['./','index.html','manifest.json','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);if((u.hostname==='127.0.0.1'||u.hostname==='localhost')&&u.origin!==location.origin)return; // servidor do Termux: não cachear
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(hit=>{
    const net=fetch(e.request).then(r=>{
      if(r&&(r.ok||r.type==='opaque')){const c=r.clone();caches.open(V).then(x=>x.put(e.request,c))}
      return r;
    }).catch(()=>hit||(e.request.mode==='navigate'?caches.match('index.html'):Response.error()));
    return hit||net;
  }));
});
