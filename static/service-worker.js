const CACHE_NAME = "resync-shell-v1";
const SHELL_FILES = ["/", "/login/", "/signup/"];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => cachedResponse || fetch(event.request).catch(() => caches.match("/")))
    );
});
