/* MITARIDALA — retour contextuel avec une destination de secours sûre. */
(function () {
  "use strict";

  function initialiserRetourGlobal() {
    var lien = document.querySelector("[data-navigation-retour]");
    if (!lien) return;

    lien.addEventListener("click", function (evenement) {
      // Ne pas intercepter les clics ouvrant un nouvel onglet ni les clics annulés.
      if (
        evenement.defaultPrevented ||
        evenement.button !== 0 ||
        evenement.metaKey ||
        evenement.ctrlKey ||
        evenement.shiftKey ||
        evenement.altKey
      ) {
        return;
      }

      var secours = lien.getAttribute("href") || "/";
      var pageActuelle = new URL(window.location.href);
      var urlSecours;
      try {
        urlSecours = new URL(secours, pageActuelle);
      } catch (erreur) {
        evenement.preventDefault();
        return;
      }
      // Le repli doit rester sur l'origine du site, même pour un chemin mal formé.
      if (urlSecours.origin !== pageActuelle.origin) {
        evenement.preventDefault();
        return;
      }

      if (!document.referrer || window.history.length < 2) return;

      try {
        var originePrecedente = new URL(document.referrer, pageActuelle);
        var urlPrecedente = originePrecedente.pathname + originePrecedente.search + originePrecedente.hash;
        var urlActuelle = pageActuelle.pathname + pageActuelle.search + pageActuelle.hash;

        // Le retour historique n'est utilisé que si la page précédente est du même site.
        // Sinon, le lien garde sa destination de secours et ne renvoie jamais vers un tiers.
        if (originePrecedente.origin === pageActuelle.origin && urlPrecedente !== urlActuelle) {
          evenement.preventDefault();
          window.history.back();
        }
      } catch (erreur) {
        // En cas d'URL non exploitable, la navigation native vers le href reste active.
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiserRetourGlobal, { once: true });
  } else {
    initialiserRetourGlobal();
  }
})();
