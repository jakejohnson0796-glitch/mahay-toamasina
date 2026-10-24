/* MITARIDALA — interactions connexion / inscription. */
(function () {
  "use strict";

  function formaterTelephoneLocal(chiffres) {
    // Affiche le format local a 10 chiffres (034 12 345 67) lorsqu'un 0
    // est saisi, tout en conservant le format international historique
    // a 9 chiffres (34 12 345 67) pour les comptes existants.
    if (chiffres.startsWith("0")) {
      return [chiffres.slice(0, 3), chiffres.slice(3, 5), chiffres.slice(5, 8), chiffres.slice(8, 10)]
        .filter(Boolean)
        .join(" ");
    }
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
        const chiffres = champLocal.value.replace(/\D/g, "").slice(0, 10);
        champLocal.value = formaterTelephoneLocal(chiffres);
      });

      formulaire.addEventListener("submit", function (evenement) {
        const chiffres = champLocal.value.replace(/\D/g, "");
        // Compatibilite : un utilisateur peut saisir son ancien format
        // international de 9 chiffres (34xxxxxxxx) ou le nouveau format
        // local de 10 chiffres incluant le 0 (034xxxxxxxx). Dans les deux
        // cas, on envoie toujours au backend la forme canonique locale.
        if (chiffres.length === 9) {
          champLocal.setCustomValidity("");
          champCache.value = "0" + chiffres;
          return;
        }
        if (chiffres.length === 10 && chiffres.startsWith("0")) {
          champLocal.setCustomValidity("");
          champCache.value = chiffres;
          return;
        }
        evenement.preventDefault();
        champLocal.setCustomValidity("Entrez le numéro complet : 034 12 345 67 ou 34 12 345 67.");
        champLocal.reportValidity();
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
    const cycleSelect = document.getElementById("cycle_education");
    const blocUniversite = document.getElementById("bloc-universite");
    const blocScolaire = document.getElementById("bloc-scolaire");
    const progress = document.querySelector("[data-auth-progress]");
    if (!roleSelect || !blocAcademique || !progress) return;

    const champsUniversitaires = [
      document.getElementById("universite_id"),
      document.getElementById("composante_id"),
      document.getElementById("mention_id"),
      document.getElementById("niveau")
    ].filter(Boolean);

    const champsScolaires = [
      document.getElementById("niveau_scolaire_id"),
      document.getElementById("option_scolaire_id"),
      document.getElementById("etablissement_scolaire_id")
    ].filter(Boolean);

    const niveauScolaire = document.getElementById("niveau_scolaire_id");
    const optionScolaire = document.getElementById("option_scolaire_id");
    const etablissementScolaire = document.getElementById("etablissement_scolaire_id");
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

    function estProfilAvecParcours() {
      return roleSelect.value === "etudiant" || roleSelect.value === "professeur";
    }

    function cycleValide() {
      return Boolean(cycleSelect && ["college", "lycee", "universite"].includes(cycleSelect.value));
    }

    function academiqueComplete() {
      if (!estProfilAvecParcours()) return true;
      if (!cycleValide()) return false;

      if (cycleSelect.value === "universite") {
        return champsUniversitaires.every(function (champ) {
          return champ.value.trim().length > 0 && !champ.disabled;
        });
      }

      // Un élève doit préciser sa classe. Un professeur peut déclarer
      // enseigner au collège/lycée sans devoir choisir une seule classe ;
      // le niveau reste facultatif et sert alors de spécialité indicative.
      if (roleSelect.value === "professeur" && (!niveauScolaire || !niveauScolaire.value)) {
        return !optionScolaire || !optionScolaire.value;
      }
      return Boolean(niveauScolaire && niveauScolaire.value && !niveauScolaire.disabled);
    }

    function actualiser() {
      const profilActif = estProfilAvecParcours();
      const estUniversitaire = profilActif && cycleSelect && cycleSelect.value === "universite";
      const estScolaire = profilActif && cycleSelect && ["college", "lycee"].includes(cycleSelect.value);

      blocAcademique.hidden = !profilActif;
      if (cycleSelect) {
        cycleSelect.disabled = !profilActif;
        cycleSelect.required = profilActif;
      }
      if (blocUniversite) blocUniversite.hidden = !estUniversitaire;
      if (blocScolaire) blocScolaire.hidden = !estScolaire;

      champsUniversitaires.forEach(function (champ) {
        champ.required = Boolean(estUniversitaire);
      });
      if (niveauScolaire) {
        niveauScolaire.required = Boolean(estScolaire && roleSelect.value !== "professeur");
      }
      const labelNiveau = document.querySelector('label[for="niveau_scolaire_id"]');
      if (labelNiveau) {
        labelNiveau.textContent = roleSelect.value === "professeur"
          ? "Niveau enseigné (facultatif)"
          : "Classe (obligatoire)";
      }
      if (optionScolaire) optionScolaire.required = false;
      if (etablissementScolaire) etablissementScolaire.required = false;

      if (!compteComplet()) {
        setEtapeActive(1);
      } else if (profilActif && !academiqueComplete()) {
        setEtapeActive(2);
      } else {
        setEtapeActive(3);
      }
    }

    roleSelect.addEventListener("change", actualiser);
    if (cycleSelect) cycleSelect.addEventListener("change", actualiser);
    champsCompte.forEach(function (champ) {
      champ.addEventListener("input", actualiser);
      champ.addEventListener("change", actualiser);
    });
    champsUniversitaires.concat(champsScolaires).forEach(function (champ) {
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
