/*
Bascule clair/sombre. Le theme initial est pose tres tot dans <head>
pour eviter le flash du mauvais theme. Ce fichier gere l'interaction,
l'etat accessible du bouton et la memorisation locale.
*/
(function () {
  "use strict";

  var CLE_STOCKAGE = "mahay-theme";
  var bouton = document.getElementById("bouton-theme");
  if (!bouton) return;

  var label = bouton.querySelector("[data-theme-label]");

  function lireTheme() {
    return document.documentElement.getAttribute("data-theme") === "sombre" ? "sombre" : "clair";
  }

  function synchroniserUI() {
    var theme = lireTheme();
    var sombre = theme === "sombre";
    bouton.setAttribute("aria-pressed", String(sombre));
    bouton.setAttribute("aria-label", sombre ? "Passer au thème clair" : "Passer au thème sombre");
    bouton.title = sombre ? "Passer au thème clair" : "Passer au thème sombre";
    if (label) label.textContent = sombre ? "Sombre" : "Clair";
  }

  bouton.addEventListener("click", function () {
    var suivant = lireTheme() === "sombre" ? "clair" : "sombre";
    document.documentElement.setAttribute("data-theme", suivant);
    synchroniserUI();

    try {
      localStorage.setItem(CLE_STOCKAGE, suivant);
    } catch (erreur) {
      /* Le theme reste actif pour la page courante si le stockage est indisponible. */
    }
  });

  synchroniserUI();
})();
