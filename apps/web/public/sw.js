const CACHE_NAME = "att-cache-v2";
const DATA_CACHE_NAME = "att-jobs-cache-v2";

const STATIC_ASSETS = [
  "/",
  "/app/home",
  "/login",
  "/favicon.ico",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png"
];

// Install service worker and pre-cache essential static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("[Service Worker] Pre-caching static app shell");
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate worker and clean up legacy caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME && key !== DATA_CACHE_NAME) {
            console.log("[Service Worker] Removing old cache", key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Intercept requests and apply caching strategies
self.addEventListener("fetch", (event) => {
  const { request } = event;
  
  // 1. ONLY intercept GET requests (ignore POST, PUT, DELETE, etc.)
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // 2. Bypass Next.js Server Components, prefetches, and internal route data requests
  if (
    request.headers.get("RSC") || 
    request.headers.get("Next-Router-State-Tree") ||
    request.headers.get("Next-Router-Prefetch") ||
    url.searchParams.has("_rsc")
  ) {
    return;
  }

  // 3. Page navigation and HTML requests: Network-First (Offline Fallback)
  if (request.mode === "navigate" || request.headers.get("accept")?.includes("text/html")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          console.log("[Service Worker] Offline: Loading page from cache", url.pathname);
          return caches.match(request);
        })
    );
    return;
  }

  // Strategy for Jobs and Stats API endpoints: Network-First (Offline Fallback)
  if (url.pathname.includes("/me/jobs") || url.pathname.includes("/me/stats") || url.pathname.includes("/me/profile")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // If response is valid, cache a clone of it
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(DATA_CACHE_NAME).then((cache) => {
              cache.put(request.url, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed (offline), try loading from data cache
          console.log("[Service Worker] Offline: Loading jobs/stats from cache");
          return caches.match(request.url).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Return empty list or JSON fallback if not cached
            return new Response(JSON.stringify({ offline: true, jobs: [] }), {
              headers: { "Content-Type": "application/json" }
            });
          });
        })
    );
    return;
  }

  // Strategy for other requests (static web app assets): Cache-First
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(request)
        .then((response) => {
          // Cache newly fetched static assets on the fly
          if (
            response &&
            response.status === 200 &&
            response.type === "basic" &&
            (url.pathname.startsWith("/_next/") || STATIC_ASSETS.includes(url.pathname))
          ) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch((err) => {
          console.error("[Service Worker] Fetch failed for:", request.url, err);
        });
    })
  );
});
