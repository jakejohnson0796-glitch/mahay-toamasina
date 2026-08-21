// Accordeon de la FAQ publique (/faq). Plusieurs questions peuvent rester
// ouvertes en meme temps (pas de fermeture automatique des autres) — voir
// aria-expanded sur chaque bouton, coherent avec le pattern deja utilise
// pour les panneaux du mega-menu (aria-controls + hidden sur le panneau).
(function () {
  const boutons = Array.from(document.querySelectorAll(".faq-question-bouton"));
  boutons.forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      const ouvert = bouton.getAttribute("aria-expanded") === "true";
      const panneau = document.getElementById(bouton.getAttribute("aria-controls"));
      bouton.setAttribute("aria-expanded", ouvert ? "false" : "true");
      if (panneau) panneau.hidden = ouvert;
    });
  });
})();
