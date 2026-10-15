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
      if (!response.ok) return { ok: false, data: [] };
      const data = await response.json();
      if (!Array.isArray(data)) return { ok: false, data: [] };
      return { ok: true, data: data };
    } catch (_error) {
      return { ok: false, data: [] };
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
    if (!mentionId || !niveau) return { ok: true, data: [] };
    return await chargerJSON(
      "/api/academique/mentions/" + encodeURIComponent(mentionId)
      + "/parcours-nationaux?niveau=" + encodeURIComponent(niveau)
    );
  }

  function effacerEtatParcours(select) {
    const etat = document.getElementById(select.id + "-etat");
    if (etat) etat.remove();
    select.removeAttribute("aria-invalid");
    select.removeAttribute("aria-busy");
  }

  function afficherEtatParcours(select, message, recommencer, erreur) {
    let etat = document.getElementById(select.id + "-etat");
    if (!etat) {
      etat = document.createElement("div");
      etat.id = select.id + "-etat";
      etat.tabIndex = -1;
      select.insertAdjacentElement("afterend", etat);
    }
    etat.className = erreur ? "erreur" : "stat-label";
    etat.setAttribute("role", erreur ? "alert" : "status");
    etat.setAttribute("aria-live", "polite");
    etat.replaceChildren();

    const texte = document.createElement("span");
    texte.textContent = message;
    etat.appendChild(texte);

    if (typeof recommencer === "function") {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "bouton bouton-secondaire";
      bouton.textContent = "Réessayer";
      bouton.addEventListener("click", recommencer);
      etat.appendChild(document.createTextNode(" "));
      etat.appendChild(bouton);
    }

    if (erreur) select.setAttribute("aria-invalid", "true");
    else select.removeAttribute("aria-invalid");
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
      effacerEtatParcours(parcours);
      if (!mention.value || !niveau.value) {
        parcours.replaceChildren();
        option(parcours, "", "Tous les parcours", true);
        parcours.disabled = true;
        return;
      }

      parcours.disabled = true;
      parcours.setAttribute("aria-busy", "true");
      afficherEtatParcours(parcours, "Chargement des parcours…", null, false);
      const resultat = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;
      parcours.removeAttribute("aria-busy");
      effacerEtatParcours(parcours);

      if (!resultat.ok) {
        parcours.replaceChildren();
        option(parcours, "", "— parcours indisponibles —", true);
        parcours.disabled = false;
        afficherEtatParcours(
          parcours,
          "Impossible de charger les parcours du référentiel. Réessaie avant de filtrer par parcours.",
          function () { actualiserParcours(""); },
          true
        );
        return;
      }

      remplirParcours(parcours, resultat.data, valeurCourante, true, "Tous les parcours");
    }

    domaine.addEventListener("change", function () {
      mention.value = "";
      niveau.value = "";
      effacerEtatParcours(parcours);
      parcours.replaceChildren();
      option(parcours, "", "Tous les parcours", true);
      parcours.disabled = true;
      filtrerMentionsLocalement();
    });

    mention.addEventListener("change", function () {
      niveau.value = "";
      effacerEtatParcours(parcours);
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

    const formulaire = parcours.closest("form");
    let generation = 0;
    if (formulaire) {
      formulaire.dataset.parcoursState = "idle";
      formulaire.addEventListener("submit", function (event) {
        const etat = formulaire.dataset.parcoursState;
        if (etat === "loading" || etat === "error") {
          event.preventDefault();
          const message = document.getElementById(parcours.id + "-etat");
          if (message) message.focus();
        }
      });
    }

    function resetParcours() {
      effacerEtatParcours(parcours);
      parcours.replaceChildren();
      option(parcours, "", "— choisissez d'abord un niveau —", true);
      parcours.disabled = true;
      if (infoTronc) infoTronc.hidden = true;
      if (formulaire) formulaire.dataset.parcoursState = "idle";
    }

    async function charger() {
      const ticket = ++generation;
      resetParcours();
      if (!mention.value || !niveau.value) return;

      if (formulaire) formulaire.dataset.parcoursState = "loading";
      parcours.setAttribute("aria-busy", "true");
      afficherEtatParcours(parcours, "Chargement des parcours…", null, false);
      const resultat = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;
      parcours.removeAttribute("aria-busy");

      if (!resultat.ok) {
        parcours.replaceChildren();
        option(parcours, "", "— parcours indisponibles —", true);
        parcours.disabled = true;
        if (infoTronc) infoTronc.hidden = true;
        if (formulaire) formulaire.dataset.parcoursState = "error";
        afficherEtatParcours(
          parcours,
          "Le référentiel des parcours est momentanément indisponible. Réessaie avant de créer le cercle.",
          function () { charger(); },
          true
        );
        return;
      }

      effacerEtatParcours(parcours);
      if (formulaire) formulaire.dataset.parcoursState = "ready";
      const rows = resultat.data;
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
