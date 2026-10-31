/* NEXUS — service worker (3.5).
   Guarda só o "casco" público (ícones, página offline). NUNCA guarda /api, /ws, /uploads nem respostas com
   dados seus: sem rede, você vê uma tela "NEXUS fora do ar" em vez de uma página quebrada. */
const VERSAO = 'nexus-pwa-v2';
const CASCO = ['/offline', '/icons/icon-192.png', '/icons/icon-512.png', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCO)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws') || url.pathname.startsWith('/uploads')) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/offline')));
    return;
  }
  if (CASCO.includes(url.pathname)) {
    e.respondWith(caches.match(req).then((r) => r || fetch(req)));
  }
});

/* Toque na notificação: foca o app aberto ou abre o painel. */
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((ws) => {
    for (const w of ws) { if ('focus' in w) return w.focus(); }
    return self.clients.openWindow('/');
  }));
});

/* Web Push (3.6): aviso do NEXUS com o app fechado. O conteúdo chega criptografado e é mostrado como veio (já curto). */
self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(String(d.title || 'NEXUS').slice(0, 60), {
    body: String(d.body || '').slice(0, 160), icon: '/icons/icon-192.png', badge: '/icons/icon-192.png', tag: d.tag || 'nexus',
  }));
});
