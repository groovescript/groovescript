// Service worker: makes the editor work offline and installable.
//
// - The editor's own files (and the compiler bundle) are fetched
//   network-first, so a new deploy shows up on the next online load, and
//   the last copy is served when offline.
// - The pinned Pyodide / Verovio builds on jsDelivr never change at a given
//   version, so they are served cache-first.
// - On install the shell is cached, and the runtimes are pre-fetched in the
//   background (best effort): on a first visit the page's worker starts
//   before this service worker controls it, so its own downloads would not
//   land in the cache.
//
// This is a classic (non-module) worker for the widest browser support, so
// the runtime versions are repeated here; preview.test.js keeps them in
// sync with deps.js. Bump SHELL_CACHE when the shell list changes shape.

const PYODIDE_VERSION = '314.0.7';
const VEROVIO_VERSION = '6.3.0';

const SHELL_CACHE = 'gs-shell-v1';
const RUNTIME_CACHE = 'gs-runtime-v1';
const KEEP = new Set([SHELL_CACHE, RUNTIME_CACHE]);

const SHELL = [
  './',
  'index.html',
  'style.css',
  'manifest.webmanifest',
  'icon-192.png',
  'icon-512.png',
  'app.js',
  'assist.js',
  'deps.js',
  'diagnostics.js',
  'drumkit.js',
  'gs-mode.js',
  'midi-parse.js',
  'player.js',
  'preview.js',
  'textchange.js',
  'worker.js',
  'vendor/codemirror.bundle.js',
  'py/groovescript-py.zip',
];

const CDN = 'https://cdn.jsdelivr.net/npm/';
const RUNTIME = [
  `${CDN}pyodide@${PYODIDE_VERSION}/pyodide.mjs`,
  `${CDN}pyodide@${PYODIDE_VERSION}/pyodide.asm.mjs`,
  `${CDN}pyodide@${PYODIDE_VERSION}/pyodide.asm.wasm`,
  `${CDN}pyodide@${PYODIDE_VERSION}/python_stdlib.zip`,
  `${CDN}pyodide@${PYODIDE_VERSION}/pyodide-lock.json`,
  `${CDN}verovio@${VEROVIO_VERSION}/dist/verovio.mjs`,
  `${CDN}verovio@${VEROVIO_VERSION}/dist/verovio-module.mjs`,
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL_CACHE);
    await shell.addAll(SHELL);
    // Best effort: a failed runtime download must not block installing.
    const runtime = await caches.open(RUNTIME_CACHE);
    await Promise.allSettled(RUNTIME.map(async (url) => {
      if (await runtime.match(url)) return;
      const res = await fetch(url, { mode: 'cors' });
      if (res.ok) await runtime.put(url, res);
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (!KEEP.has(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET' || request.headers.has('range')) return;
  const url = new URL(request.url);
  if (url.href.startsWith(CDN)) {
    event.respondWith(cacheFirst(request));
  } else if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(request));
  }
});

async function cacheFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok && res.status === 200) cache.put(request, res.clone());
  return res;
}

async function networkFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const res = await fetch(request);
    if (res.ok && res.status === 200) cache.put(request, res.clone());
    return res;
  } catch (err) {
    // Offline: the cached copy, ignoring query strings (?local-deps, cache
    // busters); navigations fall back to the editor page itself.
    const hit = await cache.match(request, { ignoreSearch: true })
      || (request.mode === 'navigate' ? await cache.match('./') : null);
    if (hit) return hit;
    throw err;
  }
}
