// Formulaire de feedback (/feedback) : selection des etoiles (component
// etoiles.html), compteur de caracteres du commentaire, et protection
// anti-double-clic sur l'envoi. Meme style IIFE vanilla que navigation.js
// (pas de framework JS ajoute au projet).
(function () {
  // --- Selection des etoiles ---
  const conteneur = document.querySelector("[data-etoiles-saisie]");
  if (conteneur) {
    const champCache = conteneur.querySelector("[data-etoiles-valeur]");
    const boutons = Array.from(conteneur.querySelectorAll(".etoile-bouton"));
    const libelle = conteneur.querySelector("[data-etoiles-libelle]");
    const textes = {
      1: "1 etoile — Tres insatisfait",
      2: "2 etoiles — Insatisfait",
      3: "3 etoiles — Moyen",
      4: "4 etoiles — Satisfait",
      5: "5 etoiles — Tres satisfait",
    };

    function appliquerNote(valeur, depuisSurvol) {
      boutons.forEach(function (bouton) {
        const valeurBouton = parseInt(bouton.dataset.etoileValeur, 10);
        const actif = valeurBouton <= valeur;
        bouton.classList.toggle("etoile-bouton-active", actif);
        bouton.setAttribute("aria-checked", (!depuisSurvol && valeurBouton === parseInt(champCache.value, 10)) ? "true" : "false");
      });
      if (libelle && valeur > 0) {
        libelle.textContent = textes[valeur] || "";
      }
    }

    boutons.forEach(function (bouton) {
      const valeur = parseInt(bouton.dataset.etoileValeur, 10);

      bouton.addEventListener("click", function () {
        champCache.value = String(valeur);
        appliquerNote(valeur, false);
      });

      // Survol/focus clavier : previsualise sans valider le choix final,
      // pour que l'utilisateur voie ce qu'il s'apprete a selectionner.
      bouton.addEventListener("mouseenter", function () {
        appliquerNote(valeur, true);
      });
      bouton.addEventListener("focus", function () {
        appliquerNote(valeur, true);
      });
    });

    conteneur.addEventListener("mouseleave", function () {
      appliquerNote(parseInt(champCache.value, 10) || 0, false);
    });

    // Navigation clavier gauche/droite entre les etoiles (accessibilite —
    // Partie 15/18 du brief : navigation clavier sur les composants
    // interactifs).
    conteneur.addEventListener("keydown", function (evenement) {
      if (evenement.key !== "ArrowRight" && evenement.key !== "ArrowLeft") return;
      const actuel = parseInt(champCache.value, 10) || 0;
      const suivant = evenement.key === "ArrowRight"
        ? Math.min(5, actuel + 1)
        : Math.max(1, actuel - 1);
      champCache.value = String(suivant);
      appliquerNote(suivant, false);
      const boutonCible = boutons[suivant - 1];
      if (boutonCible) boutonCible.focus();
      evenement.preventDefault();
    });
  }

  // --- Compteur de caracteres du commentaire ---
  const commentaire = document.getElementById("commentaire");
  const compteur = document.getElementById("compteur-commentaire");
  if (commentaire && compteur) {
    const max = parseInt(commentaire.getAttribute("maxlength"), 10) || 1000;
    function mettreAJourCompteur() {
      const restant = max - commentaire.value.length;
      compteur.textContent = commentaire.value.length + " / " + max;
      compteur.classList.toggle("compteur-limite", restant <= 20);
    }
    commentaire.addEventListener("input", mettreAJourCompteur);
    mettreAJourCompteur();
  }

  // --- Anti-double-clic + etat loading du bouton d'envoi ---
  const formulaireFeedback = document.getElementById("formulaire-feedback");
  if (formulaireFeedback) {
    formulaireFeedback.addEventListener("submit", function (evenement) {
      const champCache = formulaireFeedback.querySelector("[data-etoiles-valeur]");
      if (!champCache || !champCache.value || champCache.value === "0") {
        evenement.preventDefault();
        const libelle = formulaireFeedback.querySelector("[data-etoiles-libelle]");
        if (libelle) libelle.textContent = "Choisissez une note avant d'envoyer.";
        return;
      }

      const bouton = formulaireFeedback.querySelector("[data-bouton-envoi]");
      if (bouton) {
        // Le second clic (double-clic accidentel) trouve le bouton deja
        // disabled et ne redeclenche donc pas une seconde soumission.
        if (bouton.disabled) {
          evenement.preventDefault();
          return;
        }
        bouton.disabled = true;
        bouton.textContent = "Envoi en cours...";
      }
    });
  }
})();
