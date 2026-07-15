/* VISTA — Service Worker (PWA)
 * v4 (jul-2026): PASS-THROUGH. Deja de cachear por completo.
 *
 * Por qué: en móvil (iPhone/Android/PWA instalada) la app se congelaba con pantalla
 * oscura, se recuperaba al refrescar y volvía a congelarse. La laptop (cliente fresco)
 * nunca fallaba. La única diferencia: los teléfonos tenían atrapado un SW viejo que
 * servía HTML/JS obsoleto desde su caché. Un SW solo puede servir contenido viejo si
 * llama a `respondWith()` con una respuesta cacheada.
 *
 * Estrategia nueva (a prueba de balas):
 *   - NO se registra ningún handler `fetch` que llame a `respondWith()` → el navegador
 *     maneja TODAS las peticiones normalmente. El SW es incapaz de servir algo obsoleto.
 *   - `activate` BORRA todas las cachés (incluida la vieja `vista-pwa-v3`) y toma control.
 *   - `skipWaiting` + `clients.claim` fuerzan el reemplazo del SW viejo en la próxima
 *     apertura, incluso en la app instalada. El listener `controllerchange` de index.html
 *     recarga una vez para entregar el control limpio.
 *
 * La PWA sigue siendo instalable (hay SW + manifest); simplemente ya no cachea.
 * Se pierde el modo offline — aceptable: esta app siempre requiere red (API).
 */
const VERSION = 'vista-pwa-v4-passthrough';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Sin handler `fetch`: el navegador resuelve todo por red/caché-HTTP estándar.
// Intencionalmente NO interceptamos nada para no poder servir contenido obsoleto.
