// Gasy Mahay — enregistrement du service worker PWA.
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function (erreur) {
      // La PWA reste facultative : une indisponibilité du service worker
      // ne doit jamais empêcher l'application principale de fonctionner.
      console.warn("[Gasy Mahay] Service worker indisponible.", erreur);
    });
  });
})();
