const SOURCEFLOW_STATIC_CACHE = "sourceflow-static-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SOURCEFLOW_STATIC_CACHE));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/admin/")) {
    return;
  }
  if (event.request.method !== "GET" || !url.pathname.startsWith("/static/")) {
    return;
  }
  event.respondWith(_staticAssetResponse(event.request));
});

async function _staticAssetResponse(request) {
  const cache = await caches.open(SOURCEFLOW_STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}
