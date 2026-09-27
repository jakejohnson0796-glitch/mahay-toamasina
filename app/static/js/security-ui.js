/* Gestion des anciens handlers inline, migres vers data-* pour CSP strict. */
(function () {
  document.addEventListener("change", function (evenement) {
    var element = evenement.target;
    if (element.matches("[data-submit-on-change]")) {
      var formulaire = element.form;
      if (formulaire) formulaire.requestSubmit ? formulaire.requestSubmit() : formulaire.submit();
    }

    var targetId = element.getAttribute("data-reattribuer-target");
    if (targetId && element.value) {
      var cible = document.getElementById(targetId);
      if (cible) {
        cible.value = "reattribuer:" + element.value;
        if ("checked" in cible) cible.checked = true;
      }
    }
  });

  document.addEventListener("click", function (evenement) {
    var toggle = evenement.target.closest("[data-toggle-target]");
    if (toggle) {
      var cible = document.getElementById(toggle.getAttribute("data-toggle-target"));
      if (cible) cible.hidden = !cible.hidden;
    }
  });
})();
