/* Gasy Mahay — interactions connexion / inscription. */
(function () {
  "use strict";

  function formaterTelephoneLocal(chiffres) {
    return [chiffres.slice(0, 2), chiffres.slice(2, 4), chiffres.slice(4, 7), chiffres.slice(7, 9)]
      .filter(Boolean)
      .join(" ");
  }

  function initialiserTelephone() {
    document.querySelectorAll("[data-telephone-local]").forEach(function (champLocal) {
      const champCache = document.getElementById(champLocal.dataset.telephoneLocal);
      const formulaire = champLocal.form;
      if (!champCache || !formulaire) return;

      champLocal.addEventListener("input", function () {
        const chiffres = champLocal.value.replace(/\D/g, "").slice(0, 9);
        champLocal.value = formaterTelephoneLocal(chiffres);
      });

      formulaire.addEventListener("submit", function (evenement) {
        const chiffres = champLocal.value.replace(/\D/g, "");
        if (chiffres.length !== 9) {
          evenement.preventDefault();
          champLocal.setCustomValidity("Entrez exactement 9 chiffres après +261.");
          champLocal.reportValidity();
          return;
        }
        champLocal.setCustomValidity("");
        champCache.value = "0" + chiffres;
      });
    });
  }

  function initialiserMotDePasse() {
    document.querySelectorAll("[data-password-target]").forEach(function (bouton) {
      const champ = document.getElementById(bouton.dataset.passwordTarget);
      if (!champ) return;

      bouton.addEventListener("click", function () {
        const visible = champ.type === "text";
        champ.type = visible ? "password" : "text";
        bouton.textContent = visible ? "Voir" : "Masquer";
        bouton.setAttribute("aria-pressed", String(!visible));
        bouton.setAttribute(
          "aria-label",
          visible ? "Afficher le mot de passe" : "Masquer le mot de passe"
        );
      });
    });
  }

  function scoreMotDePasse(valeur) {
    let score = 0;
    if (valeur.length >= 8) score += 1;
    if (valeur.length >= 12) score += 1;
    if (/[A-Z]/.test(valeur) && /[a-z]/.test(valeur)) score += 1;
    if (/\d/.test(valeur) && /[^A-Za-z0-9]/.test(valeur)) score += 1;
    return Math.min(score, 4);
  }

  function initialiserForceMotDePasse() {
    const champ = document.querySelector("[data-password-strength]");
    const meter = document.querySelector("[data-password-meter]");
    const label = document.querySelector("[data-password-label]");
    if (!champ || !meter || !label) return;

    const libelles = {
      0: "Commencez à saisir votre mot de passe.",
      1: "Faible — ajoutez au moins 8 caractères.",
      2: "Correct — ajoutez encore un peu de variété.",
      3: "Solide — votre mot de passe est plus robuste.",
      4: "Très solide."
    };

    function actualiser() {
      const score = scoreMotDePasse(champ.value);
      meter.dataset.score = String(score);
      label.textContent = libelles[score];
    }

    champ.addEventListener("input", actualiser);
    actualiser();
  }

  function initialiserRoleEtProgression() {
    const roleSelect = document.getElementById("role");
    const blocAcademique = document.getElementById("bloc-academique");
    const progress = document.querySelector("[data-auth-progress]");
    if (!roleSelect || !blocAcademique || !progress) return;

    const champsAcademiquesRequis = [
      document.getElementById("universite_id"),
      document.getElementById("composante_id"),
      document.getElementById("mention_id"),
      document.getElementById("niveau")
    ].filter(Boolean);

    const champsCompte = [
      document.getElementById("nom"),
      document.getElementById("telephone_local"),
      document.getElementById("mot_de_passe")
    ].filter(Boolean);

    const etapes = Array.from(progress.querySelectorAll("[data-step]"));

    function setEtapeActive(numero) {
      etapes.forEach(function (etape) {
        const valeur = Number(etape.dataset.step);
        etape.classList.toggle("is-active", valeur === numero);
        etape.classList.toggle("is-complete", valeur < numero);
      });
    }

    function compteComplet() {
      return champsCompte.every(function (champ) {
        return champ.value.trim().length > 0;
      });
    }

    function academiqueComplete() {
      return champsAcademiquesRequis.every(function (champ) {
        return champ.value.trim().length > 0;
      });
    }

    function actualiser() {
      const estEtudiant = roleSelect.value === "etudiant";
      blocAcademique.hidden = !estEtudiant;
      champsAcademiquesRequis.forEach(function (champ) {
        champ.required = estEtudiant;
      });

      if (!compteComplet()) {
        setEtapeActive(1);
      } else if (estEtudiant && !academiqueComplete()) {
        setEtapeActive(2);
      } else {
        setEtapeActive(3);
      }
    }

    roleSelect.addEventListener("change", actualiser);
    champsCompte.forEach(function (champ) {
      champ.addEventListener("input", actualiser);
      champ.addEventListener("change", actualiser);
    });
    champsAcademiquesRequis.forEach(function (champ) {
      champ.addEventListener("change", actualiser);
    });

    actualiser();
  }

  function initialiser() {
    initialiserTelephone();
    initialiserMotDePasse();
    initialiserForceMotDePasse();
    initialiserRoleEtProgression();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser);
  } else {
    initialiser();
  }
})();
