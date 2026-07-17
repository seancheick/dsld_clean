#!/usr/bin/env node
/*
 * Builds the installable PWA into dist/ from the artifact fragment (index.html).
 * The fragment stays the single source of truth; this wraps it in a full HTML
 * document, adds the manifest + service-worker registration, and stamps the
 * service-worker cache name with a content hash so deploys roll cleanly.
 *
 * Usage: node build-pwa.js [--cdn-font]   (icons are copied from ./icons)
 *   --cdn-font  strip the embedded Fraunces data-URI and load it from Google
 *               Fonts instead — smaller output for hosted deploys (artifacts
 *               can't use font CDNs, so the default build keeps it inline).
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const cdnFont = process.argv.includes('--cdn-font');
const root = __dirname;
const dist = path.join(root, 'dist');
let frag = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
if (cdnFont) {
  frag = frag.replace(/@font-face\{[\s\S]*?\}\n/, '');
}
const fontLinks = cdnFont ? `<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&display=swap">
` : '';
const hash = crypto.createHash('sha256').update(frag).digest('hex').slice(0, 10);

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });

const head = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Perks Ledger</title>
<meta name="description" content="Every credit, perk, and discount across your cards & memberships — tracked in one place.">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#F6F4EE">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#121613">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Perks">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
${fontLinks}</head>
<body>
`;

const swRegister = `
<script>
if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(()=>{}));
}
</script>
</body>
</html>
`;

fs.writeFileSync(path.join(dist, 'index.html'), head + frag + swRegister);

fs.writeFileSync(path.join(dist, 'manifest.webmanifest'), JSON.stringify({
  name: 'Perks Ledger',
  short_name: 'Perks',
  description: 'Every credit, perk, and discount across your cards & memberships — tracked in one place.',
  start_url: './index.html',
  scope: './',
  display: 'standalone',
  background_color: '#F6F4EE',
  theme_color: '#136147',
  icons: [
    { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
    { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
  ]
}, null, 2));

fs.writeFileSync(path.join(dist, 'sw.js'), `/* Perks Ledger service worker — cache-first with background refresh */
const CACHE = 'perks-ledger-${hash}';
const ASSETS = ['index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(cached => {
      const fresh = fetch(e.request).then(res => {
        if (res && res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        return res;
      }).catch(() => cached);
      if (cached) return cached;
      if (e.request.mode === 'navigate') {
        return fresh.catch(() => caches.match('index.html')).then(r => r || caches.match('index.html'));
      }
      return fresh;
    })
  );
});
`);

for (const f of ['icon-192.png', 'icon-512.png', 'apple-touch-icon.png']) {
  fs.copyFileSync(path.join(root, 'icons', f), path.join(dist, f));
}
console.log('built dist/ (cache perks-ledger-' + hash + ')');
