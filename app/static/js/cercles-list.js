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
      if (!response.ok) return null;
      const data = await response.json();
      return Array.isArray(data) ? data : null;
    } catch (_error) {
      // Ne jamais interpréter une erreur réseau comme une vraie liste vide :
      // une liste vide signifie "tronc commun", pas "chargement échoué".
      return null;
    }
  }

  function option(select, value, label, selected, nonTraduisible) {
    const node = document.createElement("option");
    node.value = String(value ?? "");
    node.textContent = label;
    node.selected = Boolean(selected);
    if (nonTraduisible) node.setAttribute("data-no-translate", "");
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
      if (rows === null) {
        parcours.replaceChildren();
        option(parcours, "", "Parcours indisponibles — recharge la page", true);
        parcours.disabled = false;
        return;
      }
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
    if (!mention || !niveau || !parcours) return;

    let generation = 0;

    function resetParcours() {
      parcours.replaceChildren();
      option(parcours, "", "— choisis d'abord une mention et un niveau —", true);
      parcours.disabled = true;
      parcours.required = false;
      parcours.dataset.parcoursCharge = "false";
      if (infoTronc) infoTronc.hidden = true;
    }

    async function charger() {
      const ticket = ++generation;
      resetParcours();
      if (!mention.value || !niveau.value) return;

      const rows = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;

      parcours.replaceChildren();
      if (rows === null) {
        option(parcours, "", "Erreur de chargement — réessaie", true);
        parcours.disabled = true;
        parcours.dataset.parcoursCharge = "false";
        if (infoTronc) infoTronc.hidden = true;
        return;
      }

      if (!rows.length) {
        option(parcours, "tronc_commun", "Tronc commun — aucun parcours spécifique", true);
        if (infoTronc) infoTronc.hidden = false;
        parcours.required = false;
      } else {
        option(parcours, "", "— choisis un parcours —", true);
        rows.forEach(function (row) {
          option(parcours, row.id, row.nom, false, true);
        });
        parcours.required = true;
      }
      parcours.disabled = false;
      parcours.dataset.parcoursCharge = "true";
    }

    mention.addEventListener("change", function () {
      niveau.disabled = !mention.value;
      niveau.required = Boolean(mention.value);
      if (!mention.value) niveau.value = "";
      charger();
    });
    niveau.addEventListener("change", charger);

    if (mention.value) {
      niveau.disabled = false;
      niveau.required = true;
      if (niveau.value) charger();
    } else {
      niveau.required = false;
      resetParcours();
    }

    const formulaireCreation = document.querySelector("[data-formulaire-creation-cercle]");
    if (formulaireCreation) {
      formulaireCreation.addEventListener("submit", function (event) {
        if (!mention.value) {
          // Groupe libre : aucun champ académique ne doit être envoyé.
          niveau.required = false;
          return;
        }
        if (!niveau.value) {
          event.preventDefault();
          niveau.focus();
          niveau.setCustomValidity("Choisis un niveau pour cette mention.");
          niveau.reportValidity();
          niveau.addEventListener("change", function () { niveau.setCustomValidity(""); }, { once: true });
          return;
        }
        if (parcours.dataset.parcoursCharge !== "true" || parcours.disabled) {
          event.preventDefault();
          if (infoTronc) {
            infoTronc.hidden = false;
            infoTronc.textContent = "Le référentiel des parcours n'a pas pu être chargé. Recharge la page avant d'envoyer ta demande.";
          }
          return;
        }
        if (parcours.required && !parcours.value) {
          event.preventDefault();
          parcours.setCustomValidity("Choisis un parcours proposé pour ce niveau.");
          parcours.reportValidity();
          parcours.addEventListener("change", function () { parcours.setCustomValidity(""); }, { once: true });
        }
      });
    }
  }

  initialiserRecherche();
  initialiserCreation();
})();
