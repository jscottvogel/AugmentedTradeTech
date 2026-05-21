importScripts('https://storage.googleapis.com/workbox-cdn/releases/6.4.1/workbox-sw.js');

if (workbox) {
  console.log('[PWA SW] Workbox is loaded');
  
  // Force immediate activation
  self.addEventListener('install', () => self.skipWaiting());
  self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

  // Precache static assets compiled by next-pwa
  workbox.precaching.precacheAndRoute(self.__WB_MANIFEST || []);

  // 1. App Shell / Page Navigation Caching
  // Fallback to cache if navigation fails
  workbox.routing.registerRoute(
    ({ request }) => request.mode === 'navigate',
    new workbox.strategies.NetworkFirst({
      cacheName: 'app-shell-cache',
      plugins: [
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
      ],
    })
  );

  // 2. API GET Requests Caching (NetworkFirst with 5s timeout)
  workbox.routing.registerRoute(
    ({ url, request }) => {
      if (request.method !== 'GET') return false;
      // Intercept our api and portal paths
      return (
        url.pathname.includes('/me') ||
        url.pathname.includes('/jobs') ||
        url.pathname.includes('/invoices') ||
        url.pathname.includes('/portal') ||
        url.pathname.includes('/dispatch')
      );
    },
    new workbox.strategies.NetworkFirst({
      cacheName: 'api-get-cache',
      networkTimeoutSeconds: 5,
      plugins: [
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
      ],
    })
  );

  // 3. Images Caching (CacheFirst, 30-day expiry)
  workbox.routing.registerRoute(
    ({ request, url }) => {
      if (request.method !== 'GET') return false;
      return (
        request.destination === 'image' ||
        url.pathname.includes('/photos') ||
        url.host.includes('s3') ||
        url.host.includes('cloudfront') ||
        url.pathname.endsWith('.png') ||
        url.pathname.endsWith('.jpg') ||
        url.pathname.endsWith('.jpeg') ||
        url.pathname.endsWith('.svg') ||
        url.pathname.endsWith('.webp')
      );
    },
    new workbox.strategies.CacheFirst({
      cacheName: 'images-cache',
      plugins: [
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        }),
      ],
    })
  );

  // 4. AI Responses Caching (CacheFirst - explicitly cached or read from cache)
  workbox.routing.registerRoute(
    ({ url, request }) => {
      if (request.method !== 'GET') return false;
      return (
        url.pathname.includes('/ai/') ||
        (url.pathname.includes('/workflow/') && url.pathname.includes('/ai'))
      );
    },
    new workbox.strategies.CacheFirst({
      cacheName: 'ai-cache',
      plugins: [
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
      ],
    })
  );

} else {
  console.log('[PWA SW] Workbox failed to load');
}
