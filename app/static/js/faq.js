// FAQ publique : accordéon accessible, fermeture au clavier et mise en évidence de la réponse ouverte.
(function () {
  "use strict";

  const boutons = Array.from(document.querySelectorAll(".faq-question-bouton"));

  function basculer(bouton, forceOuvert) {
    const panneau = document.getElementById(bouton.getAttribute("aria-controls"));
    if (!panneau) return;

    const actuellementOuvert = bouton.getAttribute("aria-expanded") === "true";
    const ouvrir = typeof forceOuvert === "boolean" ? forceOuvert : !actuellementOuvert;

    bouton.setAttribute("aria-expanded", String(ouvrir));
    panneau.hidden = !ouvrir;
  }

  boutons.forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      basculer(bouton);
    });

    bouton.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        basculer(bouton);
      }
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    const ouvert = boutons.find(function (bouton) {
      return bouton.getAttribute("aria-expanded") === "true";
    });
    if (ouvert) {
      basculer(ouvert, false);
      ouvert.focus();
    }
  });
})();
