// 美術館ウォッチの Service Worker（render.py が 2026-09-25T0846+0900 を生成日時に置き換えて docs/sw.js に書き出す）
// - ページ（HTML）はネット優先。つながらないときは、前に見たページか、トップページを出す
// - CSS・画像・アイコンは、キャッシュを先に使い、裏で新しいものに入れ替える
// - 巡回のたびに版が変わり、古いキャッシュは消える
const CACHE = "museum-watch-2026-09-25T0846+0900";
const SHELL = ["./", "index.html", "style.css", "manifest.webmanifest", "marble-light.jpg", "marble-dark.jpg",
  "icons/icon-192.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith("museum-watch-") && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return; // 外部（フォント・計測・同期など）は触らない
  const isPage = req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  if (isPage) {
    e.respondWith(fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    }).catch(async () => (await caches.match(req, { ignoreSearch: true })) || caches.match("index.html")));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => {
    const net = fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    }).catch(() => hit);
    return hit || net;
  }));
});
