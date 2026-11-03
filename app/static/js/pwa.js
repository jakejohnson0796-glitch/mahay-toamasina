// MITARIDALA — enregistrement du service worker PWA.
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function (erreur) {
      // La PWA reste facultative : une indisponibilité du service worker
      // ne doit jamais empêcher l'application principale de fonctionner.
      console.warn("[MITARIDALA] Service worker indisponible.", erreur);
    });
  });
})();
 
// Sauvegarde locale des quiz classiques pour reprendre après une coupure réseau.
(function recuperationBrouillonQuiz() {
  "use strict";
  var prefixe = "mitaridala:quiz-draft:v1:";
  var dureeMax = 7 * 24 * 60 * 60 * 1000;
  var stockage;
  try { stockage = window.localStorage; } catch (_) { return; }

  function effacerTentative(id) {
    try {
      for (var i = stockage.length - 1; i >= 0; i -= 1) {
        var cle = stockage.key(i);
        if (cle && cle.indexOf(prefixe) === 0 && cle.endsWith(":" + id)) stockage.removeItem(cle);
      }
    } catch (_) {}
  }

  var resultat = window.location.pathname.match(/^\/quiz\/(\d+)\/resultat\/?$/);
  if (resultat) { effacerTentative(resultat[1]); return; }

  var form = document.querySelector("form[data-quiz-form]");
  if (!form || form.dataset.quizAdaptatif === "1" || form.dataset.quizModeExamen === "1") return;
  var proprietaire = (form.dataset.quizOwner || "").trim();
  var tentative = (form.dataset.quizTentativeId || "").trim();
  if (!/^\d+$/.test(proprietaire) || !/^\d+$/.test(tentative)) return;

  var cle = prefixe + proprietaire + ":" + tentative;
  var statut = document.querySelector("[data-quiz-draft-status]");
  var boutonEffacer = document.querySelector("[data-quiz-draft-clear]");
  function annoncer(texte) { if (statut) statut.textContent = texte; }
  function lire() {
    var reponses = {}, confiances = {};
    form.querySelectorAll('input[type="radio"]:checked').forEach(function (input) {
      if (/^question_\d+$/.test(input.name) && /^\d+$/.test(input.value)) reponses[input.name] = input.value;
      if (/^confiance_\d+$/.test(input.name) && ["faible", "moyenne", "forte"].indexOf(input.value) !== -1) confiances[input.name] = input.value;
    });
    return { reponses: reponses, confiances: confiances };
  }
  function sauver() {
    var donnees = lire();
    if (!Object.keys(donnees.reponses).length && !Object.keys(donnees.confiances).length) {
      try { stockage.removeItem(cle); } catch (_) {}
      if (boutonEffacer) boutonEffacer.hidden = true;
      return false;
    }
    try {
      stockage.setItem(cle, JSON.stringify({
        version: 1, proprietaire: proprietaire, tentative: tentative,
        enregistreLe: Date.now(), reponses: donnees.reponses, confiances: donnees.confiances
      }));
      if (boutonEffacer) boutonEffacer.hidden = false;
      return true;
    } catch (_) {
      annoncer("Le navigateur ne peut pas enregistrer ce brouillon sur cet appareil.");
      return false;
    }
  }
  function appliquer(valeurs, confiance) {
    Object.keys(valeurs || {}).forEach(function (nom) {
      var valeur = String(valeurs[nom]);
      var nomValide = confiance ? /^confiance_\d+$/.test(nom) : /^question_\d+$/.test(nom);
      var valeurValide = confiance ? ["faible", "moyenne", "forte"].indexOf(valeur) !== -1 : /^\d+$/.test(valeur);
      if (!nomValide || !valeurValide) return;
      form.querySelectorAll('input[type="radio"]').forEach(function (input) {
        if (input.name === nom && input.value === valeur) input.checked = true;
      });
    });
  }

  try {
    var brouillon = JSON.parse(stockage.getItem(cle) || "null");
    if (brouillon && brouillon.version === 1 &&
        brouillon.proprietaire === proprietaire && String(brouillon.tentative) === tentative &&
        Number.isFinite(brouillon.enregistreLe) && Date.now() - brouillon.enregistreLe <= dureeMax) {
      appliquer(brouillon.reponses, false);
      appliquer(brouillon.confiances, true);
      annoncer("Brouillon retrouvé : tes réponses ont été rétablies sur cet appareil.");
      if (boutonEffacer) boutonEffacer.hidden = false;
    } else {
      stockage.removeItem(cle);
      annoncer("Tes réponses se sauvegardent sur cet appareil.");
    }
  } catch (_) {
    try { stockage.removeItem(cle); } catch (__) {}
    annoncer("Tes réponses se sauvegardent sur cet appareil.");
  }

  form.addEventListener("change", function (event) {
    if (event.target && event.target.matches('input[type="radio"]')) {
      if (sauver()) annoncer("Brouillon enregistré sur cet appareil.");
    }
  });
  form.addEventListener("submit", function (event) {
    sauver();
    if (navigator.onLine === false) {
      event.preventDefault();
      annoncer("Connexion indisponible : tes réponses sont conservées sur cet appareil. Reconnecte-toi puis valide le quiz.");
    }
  });
  window.addEventListener("online", function () {
    try {
      if (stockage.getItem(cle)) annoncer("Connexion rétablie : tes réponses sont prêtes. Valide le quiz pour les envoyer.");
    } catch (_) {}
  });
  if (boutonEffacer) boutonEffacer.addEventListener("click", function () {
    try { stockage.removeItem(cle); } catch (_) {}
    form.querySelectorAll('input[type="radio"]:checked').forEach(function (input) { input.checked = false; });
    boutonEffacer.hidden = true;
    annoncer("Brouillon effacé de cet appareil.");
  });
})();
