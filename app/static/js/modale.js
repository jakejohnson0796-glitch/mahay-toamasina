/*
Modale de confirmation reutilisable, remplace window.confirm() (popup
native du navigateur, hors de toute identite visuelle -- chrome gere
par l'OS, aucun style possible) sur les actions destructives du site.

Deux fonctions exposees sur window :

- mahayConfirm(message, options) -> Promise<boolean>
  options.titre (defaut "Confirmer"), options.libelleConfirmer (defaut
  "Confirmer"), options.danger (defaut true -- bouton .bouton-danger ;
  passer false pour .bouton-primaire sur une confirmation non
  destructive).

- mahayConfirmSubmit(evenement, message, options) : raccourci pour un
  attribut onsubmit="return mahayConfirmSubmit(event, '...')", remplace
  directement onsubmit="return confirm('...')" sur un <form>. Utilise
  form.submit() (methode native) plutot que form.requestSubmit() pour
  la resoumission confirmee : submit() ne redeclenche PAS l'evenement
  "submit" (contrairement a requestSubmit()), donc pas de boucle avec
  le onsubmit lui-meme sur ce meme formulaire.
*/
(function () {
  var fond = document.getElementById("mahay-modale-fond");
  if (!fond) return; // page sans le shell : ne devrait pas arriver, base.html le pose partout

  var titreEl = document.getElementById("mahay-modale-titre");
  var messageEl = document.getElementById("mahay-modale-message");
  var boutonAnnuler = document.getElementById("mahay-modale-annuler");
  var boutonConfirmer = document.getElementById("mahay-modale-confirmer");

  function mahayConfirm(message, options) {
    options = options || {};
    return new Promise(function (resoudre) {
      var declencheur = document.activeElement;

      titreEl.textContent = options.titre || "Confirmer";
      messageEl.textContent = message;
      boutonConfirmer.textContent = options.libelleConfirmer || "Confirmer";
      boutonConfirmer.className = "bouton " + (options.danger === false ? "bouton-primaire" : "bouton-danger");

      function nettoyer() {
        fond.hidden = true;
        boutonConfirmer.removeEventListener("click", surConfirmer);
        boutonAnnuler.removeEventListener("click", surAnnuler);
        fond.removeEventListener("mousedown", surClicFond);
        document.removeEventListener("keydown", surTouche);
        if (declencheur && typeof declencheur.focus === "function") declencheur.focus();
      }
      function surConfirmer() { nettoyer(); resoudre(true); }
      function surAnnuler() { nettoyer(); resoudre(false); }
      function surClicFond(evenement) {
        if (evenement.target === fond) surAnnuler();
      }
      function surTouche(evenement) {
        if (evenement.key === "Escape") { surAnnuler(); return; }
        if (evenement.key !== "Tab") return;
        // Piege a focus minimal : seuls les deux boutons sont
        // atteignables au clavier tant que la modale est ouverte.
        var elements = [boutonAnnuler, boutonConfirmer];
        var index = elements.indexOf(document.activeElement);
        evenement.preventDefault();
        var suivant = evenement.shiftKey
          ? (index <= 0 ? elements.length - 1 : index - 1)
          : (index === elements.length - 1 ? 0 : index + 1);
        elements[suivant].focus();
      }

      boutonConfirmer.addEventListener("click", surConfirmer);
      boutonAnnuler.addEventListener("click", surAnnuler);
      fond.addEventListener("mousedown", surClicFond);
      document.addEventListener("keydown", surTouche);

      fond.hidden = false;
      boutonAnnuler.focus();
    });
  }

  window.mahayConfirm = mahayConfirm;

  window.mahayConfirmSubmit = function (evenement, message, options) {
    evenement.preventDefault();
    var formulaire = evenement.target;
    mahayConfirm(message, options).then(function (ok) {
      if (ok) formulaire.submit();
    });
    return false;
  };
})();
