/* Recherche Cercles : une seule cascade nationale reutilisee pour
   recherche et creation.
   Hierarchie : Domaine -> Mention -> Niveau -> Parcours.
   Les donnees sont rendues cote serveur pour le premier affichage puis
   filtrees/rechargees progressivement. */
(function () {
  "use strict";

  async function chargerJSON(url) {
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) return [];
      return await response.json();
    } catch (_error) {
      return [];
    }
  }

  function option(select, value, label, selected, nonTraduisible) {
    const node = document.createElement("option");
    node.value = String(value ?? "");
    node.textContent = label;
    node.selected = Boolean(selected);
    if (nonTraduisible) node.setAttribute("data-no-translate", "");
    select.appendChild(node);
    return node;
  }

  async function chargerParcoursNationaux(mentionId, niveau) {
    if (!mentionId || !niveau) return [];
    return await chargerJSON(
      "/api/academique/mentions/" + encodeURIComponent(mentionId)
      + "/parcours-nationaux?niveau=" + encodeURIComponent(niveau)
    );
  }

  function remplirParcours(select, parcours, valeurCourante, allowTronc, aucuneOption) {
    select.replaceChildren();
    option(select, "", aucuneOption, !valeurCourante);
    const valeur = String(valeurCourante || "");

    if (allowTronc) {
      option(select, "tronc_commun", "Tronc commun", valeur === "tronc_commun");
    }

    parcours.forEach(function (item) {
      option(select, item.id, item.nom, String(item.id) === valeur, true);
    });

    if (valeur && Array.from(select.options).every(function (o) { return o.value !== valeur; })) {
      select.value = "";
    }
    select.disabled = false;
  }

  function initialiserRecherche() {
    const formulaire = document.getElementById("formulaire-recherche-cercles");
    const domaine = document.getElementById("recherche_domaine_id");
    const mention = document.getElementById("recherche_mention_id");
    const niveau = document.getElementById("recherche_niveau");
    const parcours = document.getElementById("recherche_filiere_id");
    if (!formulaire || !domaine || !mention || !niveau || !parcours) return;

    const domaineInitial = domaine.value;
    const mentionInitiale = mention.value;
    const niveauInitial = niveau.value;
    const parcoursInitial = parcours.value;
    let generation = 0;

    function filtrerMentionsLocalement() {
      const domaineId = domaine.value;
      const selection = mention.value;
      Array.from(mention.options).forEach(function (node) {
        if (!node.value) {
          node.hidden = false;
          return;
        }
        node.hidden = Boolean(domaineId && node.dataset.domaineId !== domaineId);
      });
      if (
        selection
        && !Array.from(mention.options).some(function (node) {
          return node.value === selection && !node.hidden;
        })
      ) {
        mention.value = "";
      }
    }

    async function actualiserParcours(valeurCourante) {
      const ticket = ++generation;
      parcours.disabled = true;
      const rows = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;
      remplirParcours(parcours, rows, valeurCourante, true, "Tous les parcours");
    }

    domaine.addEventListener("change", function () {
      mention.value = "";
      niveau.value = "";
      parcours.replaceChildren();
      option(parcours, "", "Tous les parcours", true);
      parcours.disabled = true;
      filtrerMentionsLocalement();
    });

    mention.addEventListener("change", function () {
      niveau.value = "";
      parcours.replaceChildren();
      option(parcours, "", "Tous les parcours", true);
      parcours.disabled = true;
    });

    niveau.addEventListener("change", function () {
      const ticketValue = parcours.value;
      actualiserParcours(ticketValue);
    });

    filtrerMentionsLocalement();

    // Retour visuel immediat : la recherche est une navigation serveur, donc
    // le navigateur peut sembler bloque pendant la reponse Render. Le libelle
    // change tout de suite et empeche les doubles soumissions.
    formulaire.addEventListener("submit", function () {
      const bouton = formulaire.querySelector('button[type="submit"]');
      if (!bouton) return;
      bouton.disabled = true;
      bouton.dataset.libelleInitial = bouton.textContent;
      bouton.textContent = "Recherche…";
      bouton.setAttribute("aria-busy", "true");
    });

    // Restauration deterministe apres rendu serveur :
    // le serveur peut avoir derive Domaine depuis Mention.
    if (!domaine.value && domaineInitial) domaine.value = domaineInitial;
    if (!mention.value && mentionInitiale) mention.value = mentionInitiale;
    if (!niveau.value && niveauInitial) niveau.value = niveauInitial;
    if (mention.value && niveau.value) {
      actualiserParcours(parcoursInitial);
    }
  }

  function initialiserCreation() {
    const mention = document.getElementById("creation_mention_id");
    const niveau = document.getElementById("creation_niveau");
    const parcours = document.getElementById("creation_filiere_id");
    const infoTronc = document.getElementById("creation-info-tronc-commun");
    const formulaire = document.querySelector("[data-formulaire-creation-cercle]");
    if (!mention || !niveau || !parcours || !formulaire) return;

    const mentionTroncProfil = String(formulaire.dataset.troncMentionId || "");
    const niveauTroncProfil = String(formulaire.dataset.troncNiveau || "");
    let generation = 0;

    function peutChoisirTroncCommun() {
      return Boolean(
        mentionTroncProfil
        && niveauTroncProfil
        && mention.value === mentionTroncProfil
        && niveau.value === niveauTroncProfil
      );
    }

    function afficherInfo(message) {
      if (!infoTronc) return;
      infoTronc.textContent = message || "";
      infoTronc.hidden = !message;
      infoTronc.setAttribute("data-etat", message ? "info" : "");
    }

    function resetParcours() {
      parcours.replaceChildren();
      option(parcours, "", "— choisis d'abord un niveau —", true);
      parcours.disabled = true;
      afficherInfo("");
    }

    async function charger() {
      const ticket = ++generation;
      resetParcours();
      if (!mention.value || !niveau.value) return;

      const rows = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;

      const troncAutorise = peutChoisirTroncCommun();
      parcours.replaceChildren();

      if (troncAutorise) {
        option(parcours, "", "Tronc commun — sans parcours spécifique", true);
      } else {
        const placeholder = option(
          parcours,
          "",
          rows.length ? "— choisis un parcours —" : "Aucun parcours disponible pour ce niveau",
          true
        );
        placeholder.disabled = true;
      }

      rows.forEach(function (row) {
        option(parcours, row.id, row.nom, false, true);
      });

      if (!rows.length && !troncAutorise) {
        parcours.disabled = true;
        afficherInfo(
          "Le référentiel ne propose aucun parcours pour cette mention et ce niveau. Le tronc commun n'est disponible que si ton profil académique correspond exactement à cette mention et ce niveau. Vérifie ton profil avant de créer ce cercle."
        );
        return;
      }

      parcours.disabled = false;
      if (!rows.length && troncAutorise) {
        afficherInfo(
          "Aucun parcours spécifique n'est proposé ici. Ton profil permet de demander un cercle de tronc commun ; il sera vérifié avant validation."
        );
      } else if (troncAutorise) {
        afficherInfo(
          "Tu peux choisir un parcours parmi les offres nationales, ou garder « Tronc commun » si c'est bien le cadre de tes études."
        );
      } else {
        afficherInfo("Choisis un parcours proposé à ce niveau. Le cercle sera soumis à validation.");
      }
    }

    mention.addEventListener("change", function () {
      niveau.disabled = !mention.value;
      niveau.value = "";
      charger();
    });

    niveau.addEventListener("change", charger);

    formulaire.addEventListener("submit", function (event) {
      const aChoisiUnContexteNational = Boolean(mention.value || niveau.value || parcours.value);
      if (!aChoisiUnContexteNational) return; // groupe libre
      if (!mention.value || !niveau.value) {
        event.preventDefault();
        afficherInfo("Pour un cercle national, sélectionne une mention et un niveau. Pour un groupe libre, efface ces choix.");
        return;
      }
      if (!parcours.value && !peutChoisirTroncCommun()) {
        event.preventDefault();
        afficherInfo("Tu dois choisir un parcours proposé à ce niveau. Le tronc commun ne correspond pas à ton profil actuel.");
      }
    });

    if (mention.value) {
      niveau.disabled = false;
      if (niveau.value) charger();
      else resetParcours();
    } else {
      resetParcours();
    }
  }

  initialiserRecherche();
  initialiserCreation();
})();
