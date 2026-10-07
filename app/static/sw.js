// Gasy Mahay — service worker léger pour les réseaux instables.
// Les pages et données utilisateur restent toujours dynamiques et ne sont
// jamais mises en cache. Seuls les assets statiques sont mis en cache.
const CACHE_NOM = "mahay-static-v2";
const FICHIERS_STATIQUES = [
  "/static/manifest.json",
  "/static/style.css",
  "/static/ux.css",
  "/static/refonte.css",
  "/static/csp-utilities.css",
  "/static/responsive.css",
  "/static/sidebar.css",
  "/static/activite.css",
  "/static/student-hub.css",
  "/static/js/navigation.js",
  "/static/js/theme.js",
  "/static/js/pwa.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NOM)
      .then((cache) => cache.addAll(FICHIERS_STATIQUES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((cles) =>
        Promise.all(
          cles
            .filter((cle) => cle.startsWith("mahay-static-") && cle !== CACHE_NOM)
            .map((cle) => caches.delete(cle))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const requete = event.request;
  const url = new URL(requete.url);

  if (
    requete.method !== "GET" ||
    url.origin !== self.location.origin ||
    !url.pathname.startsWith("/static/")
  ) {
    return;
  }

  event.respondWith(
    caches.match(requete).then((enCache) => {
      const miseAJour = fetch(requete)
        .then((reponse) => {
          if (reponse.ok) {
            const copie = reponse.clone();
            caches.open(CACHE_NOM).then((cache) => cache.put(requete, copie));
          }
          return reponse;
        })
        .catch(() => enCache);

      // Cache-first pour que le site reste fluide même sur un réseau
      // dégradé ; le réseau met à jour l'asset en arrière-plan quand possible.
      return enCache || miseAJour;
    })
  );
});
