/* VISTA — Service Worker (PWA)
 * v3 (jul-2026): endurecido contra el congelamiento en móvil.
 *
 * Causa del bug anterior: se cacheaba `index.html` y se servía "stale" en móvil,
 * apuntando a chunks JS con hash que ya no existían tras un deploy → import() de
 * la ruta fallaba → app congelada. Refrescar traía el index fresco (funcionaba),
 * el SW re-servía el viejo (volvía a fallar).
 *
 * Estrategia nueva:
 *   - /api  → siempre red (nunca se toca).
 *   - dev server de Vite (/@, /src/, /node_modules/, /.vite/) → passthrough.
 *   - Navegaciones (HTML) → NETWORK-FIRST. Se cachea el index SOLO tras éxito, y el
 *     fallback offline usa esa copia (consistente con los chunks cacheados del mismo
 *     deploy). Nunca se sirve HTML viejo estando online.
 *   - Assets con hash en el nombre (immutables) → cache-first (instantáneo y seguro).
 *   - Resto same-origin → network-first con fallback a caché.
 */
const CACHE = 'vista-pwa-v3';   // bump de versión → `activate` purga TODAS las caché viejas
const APP_SHELL = ['/manifest.webmanifest', '/pwa-icon.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function esRutaDev(url) {
  return (
    url.pathname.startsWith('/@') ||
    url.pathname.startsWith('/src/') ||
    url.pathname.startsWith('/node_modules/') ||
    url.pathname.includes('/.vite/')
  );
}

// Assets con hash inmutable (…-a1b2c3d4.js) o bajo /assets/ → seguros para cache-first.
function esAssetInmutable(url) {
  return (
    url.pathname.startsWith('/assets/') ||
    /\.[0-9a-f]{8,}\.(js|mjs|css|woff2?|ttf|png|jpe?g|svg|webp|gif)$/i.test(url.pathname)
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // orígenes externos: sin tocar
  if (url.pathname.startsWith('/api')) return;      // API/auth: siempre a la red
  if (esRutaDev(url)) return;                        // dev server de Vite: passthrough

  // Navegaciones (app shell): NETWORK-FIRST. Solo se cachea el index tras un 200,
  // y el fallback a caché es exclusivamente para offline.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.status === 200) {
            const copia = res.clone();
            caches.open(CACHE).then((c) => c.put('/index.html', copia)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Assets inmutables (hash) → cache-first (rápido y seguro; el nombre cambia por deploy).
  if (esAssetInmutable(url)) {
    event.respondWith(
      caches.match(req).then((cacheada) =>
        cacheada || fetch(req).then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copia = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
          }
          return res;
        })
      )
    );
    return;
  }

  // Resto same-origin → network-first con fallback a caché.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
