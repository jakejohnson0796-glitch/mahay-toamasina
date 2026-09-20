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

  function option(select, value, label, selected) {
    const node = document.createElement("option");
    node.value = String(value ?? "");
    node.textContent = label;
    node.selected = Boolean(selected);
    select.appendChild(node);
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
      option(select, item.id, item.nom, String(item.id) === valeur);
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
    if (!mention || !niveau || !parcours) return;

    let generation = 0;

    function resetParcours() {
      parcours.replaceChildren();
      option(parcours, "", "— choisissez d'abord un niveau —", true);
      parcours.disabled = true;
      if (infoTronc) infoTronc.hidden = true;
    }

    async function charger() {
      const ticket = ++generation;
      resetParcours();
      if (!mention.value || !niveau.value) return;

      const rows = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;

      parcours.replaceChildren();
      if (!rows.length) {
        option(parcours, "", "— aucun parcours specifique —", true);
        if (infoTronc) infoTronc.hidden = false;
      } else {
        option(parcours, "", "— choisissez un parcours —", true);
        rows.forEach(function (row) {
          option(parcours, row.id, row.nom, false);
        });
      }
      parcours.disabled = false;
    }

    mention.addEventListener("change", function () {
      niveau.disabled = !mention.value;
      if (!mention.value) niveau.value = "";
      charger();
    });
    niveau.addEventListener("change", charger);

    if (mention.value) {
      niveau.disabled = false;
      if (niveau.value) charger();
    } else {
      resetParcours();
    }
  }

  initialiserRecherche();
  initialiserCreation();
})();
