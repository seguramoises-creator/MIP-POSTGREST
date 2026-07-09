/* VISTA — Service Worker (PWA)
 * Aditivo: da instalabilidad + offline básico del "app shell".
 * NO interfiere con:
 *   - /api  → siempre a la red (auth/datos, nunca se cachean)
 *   - dev server de Vite (/@vite, /src/, /node_modules/, /.vite/) → passthrough
 * Estrategia: navegaciones = network-first; assets = stale-while-revalidate.
 */
const CACHE = 'vista-pwa-v1';
const APP_SHELL = ['/', '/index.html', '/manifest.webmanifest', '/pwa-icon.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

function esRutaDev(url) {
  return (
    url.pathname.startsWith('/@') ||
    url.pathname.startsWith('/src/') ||
    url.pathname.startsWith('/node_modules/') ||
    url.pathname.includes('/.vite/')
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // orígenes externos: sin tocar
  if (url.pathname.startsWith('/api')) return;      // API/auth: siempre a la red
  if (esRutaDev(url)) return;                        // dev server de Vite: passthrough

  // Navegaciones (app shell): network-first con fallback a caché (offline).
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put('/index.html', copia)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('/index.html').then((r) => r || caches.match('/')))
    );
    return;
  }

  // Assets estáticos same-origin: stale-while-revalidate.
  event.respondWith(
    caches.match(req).then((cacheada) => {
      const red = fetch(req)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copia = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
          }
          return res;
        })
        .catch(() => cacheada);
      return cacheada || red;
    })
  );
});
