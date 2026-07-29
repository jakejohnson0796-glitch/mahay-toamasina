// Service worker minimal : met en cache le CSS/JS statique pour que
// l'app se recharge un peu plus vite. Ne met PAS en cache les pages
// dynamiques (documents, etc.) pour eviter d'afficher des donnees perimees.
const CACHE_NOM = "mahay-static-v1";
const FICHIERS_STATIQUES = ["/static/style.css", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NOM).then((cache) => cache.addAll(FICHIERS_STATIQUES))
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.url.includes("/static/")) {
    event.respondWith(
      caches.match(event.request).then((reponse) => reponse || fetch(event.request))
    );
  }
});
