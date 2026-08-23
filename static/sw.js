/* PallBot Service Worker — cache app shell untuk mode offline / feel aplikasi */
const CACHE = 'pallbot-v3';
const ASSETS = [
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;

  // API & halaman admin: jangan di-cache (auth + data dinamis)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin')) return;

  // aset statis: cache first
  if (ASSETS.includes(url.pathname)) {
    e.respondWith(
      caches.match(url.pathname).then((r) =>
        r || fetch(url.pathname).then((res) => {
          const cp = res.clone();
          caches.open(CACHE).then((c) => c.put(url.pathname, cp));
          return res;
        })
      )
    );
    return;
  }

  // halaman publik: network first, fallback ke cache (offline)
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const cp = res.clone();
        caches.open(CACHE).then((c) => c.put(url.pathname, cp));
        return res;
      })
      .catch(() =>
        caches.match(url.pathname).then((r) => r || caches.match('/'))
      )
  );
});
