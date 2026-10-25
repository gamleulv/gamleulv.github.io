/* Service worker for Søvndagbok: gjør at appen åpnes uten nett.
   Henter alltid nyeste versjon når nett finnes (nett først), ellers lagret kopi.
   Lagrer aldri pasientdata – kun selve programfilene. */
const CACHE = 'sovndagbok-app-v1';
const FILES = ['./Sovndagbok.html','./manifest.webmanifest','./app-icon-180.png','./app-icon-192.png','./app-icon-512.png','./app-icon-maskable-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('sovndagbok-app-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  const scopePath = new URL(self.registration.scope).pathname;
  if (!new URL(req.url).pathname.startsWith(scopePath)) return;
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok && FILES.some(f => new URL(f, self.registration.scope).href === new URL(req.url).href.split('?')[0])) {
        const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req, {ignoreSearch: true}).then(r => r || (req.mode === 'navigate' ? caches.match('./Sovndagbok.html') : undefined)))
  );
});
