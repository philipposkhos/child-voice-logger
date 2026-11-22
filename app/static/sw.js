// Child Voice Logger — Service Worker
// 缓存頁面與录音，讓 PWA 支援離線瀏覽與聆聽。

const CACHE_NAME = 'child-voice-logger-v1';
const APP_PAGES = ['/', '/trash'];

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        // 安裝時缓存頁面；尚未登入（401）時跳過，之後在線時會再次快取
        await Promise.allSettled(
            APP_PAGES.map(async (url) => {
                try {
                    const response = await fetch(url, { credentials: 'include' });
                    if (response.ok) {
                        await cache.put(url, response.clone());
                    }
                } catch (err) {
                    // 尚無法請求，不阻止安裝
                }
            })
        );
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)));
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    // 只處理 GET，其餘（上傳/刪除等）直接透傳
    if (request.method !== 'GET') return;

    event.respondWith((async () => {
        const cache = await caches.open(CACHE_NAME);

        // 頁面：網路優先，讓清單最新；離線時回退缓存頁面
        if (request.mode === 'navigate') {
            try {
                const response = await fetch(request);
                if (response.ok) {
                    await cache.put(request, response.clone());
                    return response;
                }
            } catch (err) {
                // 離線，走缓存
            }
            const cached = await caches.match(request, { ignoreSearch: true });
            return cached || new Response('<!DOCTYPE html><title>Offline</title>Offline', {
                status: 504,
                statusText: 'Offline',
            });
        }

        // 录音：缓存優先，離線也能繼續聆聽
        const cached = await caches.match(request, { ignoreSearch: true });
        if (cached) return cached;
        try {
            const response = await fetch(request, { credentials: 'include' });
            if (response.ok) {
                await cache.put(request, response.clone());
            }
            return response;
        } catch (err) {
            return new Response('', { status: 504, statusText: 'Offline' });
        }
    })());
});
