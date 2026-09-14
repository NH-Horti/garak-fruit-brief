// 최소 서비스워커 — 설치 가능 조건용. 캐시하지 않는다(브리프는 항상 최신을 읽어야 함).
self.addEventListener('install',function(){self.skipWaiting();});
self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim());});
self.addEventListener('fetch',function(){});
