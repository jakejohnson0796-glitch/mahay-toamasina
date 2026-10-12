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
        option(parcours, "", "Référentiel indisponible — réessaie", true);
        parcours.disabled = true;
        parcours.dataset.erreurChargement = "true";
        return;
      }
      delete parcours.dataset.erreurChargement;
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
    const formulaire = document.getElementById("creer-cercle");
    const mention = document.getElementById("creation_mention_id");
    const niveau = document.getElementById("creation_niveau");
    const parcours = document.getElementById("creation_filiere_id");
    const infoTronc = document.getElementById("creation-info-tronc-commun");
    const raison = document.getElementById("raison");
    if (!formulaire || !mention || !niveau || !parcours) return;

    let generation = 0;

    function actualiserObligations() {
      const demandeNationale = Boolean(mention.value);
      niveau.required = demandeNationale;
      if (raison) raison.required = demandeNationale;
    }

    function libelleParcours(item) {
      if (!item.niveau_a_confirmer) return item.nom;
      const langue = document.documentElement.getAttribute("lang") || "fr";
      const suffixe = langue === "mg"
        ? " — ambaratonga taloha, mila fanamarinana"
        : " — niveau historique à confirmer";
      return item.nom + suffixe;
    }

    function definirInfo(message, erreur) {
      if (!infoTronc) return;
      infoTronc.textContent = message;
      infoTronc.hidden = false;
      infoTronc.setAttribute("role", erreur ? "alert" : "status");
      infoTronc.dataset.etat = erreur ? "erreur" : "info";
    }

    function resetParcours() {
      parcours.replaceChildren();
      option(parcours, "", "— choisissez d'abord un niveau —", true);
      parcours.disabled = true;
      parcours.required = false;
      delete parcours.dataset.erreurChargement;
      if (infoTronc) infoTronc.hidden = true;
    }

    async function charger() {
      const ticket = ++generation;
      resetParcours();
      actualiserObligations();
      if (!mention.value || !niveau.value) return;

      const rows = await chargerParcoursNationaux(mention.value, niveau.value);
      if (ticket !== generation) return;

      if (rows === null) {
        parcours.replaceChildren();
        option(parcours, "", "Référentiel indisponible — réessaie", true);
        parcours.disabled = true;
        parcours.required = false;
        parcours.dataset.erreurChargement = "true";
        definirInfo(
          "Impossible de charger le référentiel académique. Réessaie avant d'envoyer cette demande ; aucun classement par défaut ne sera appliqué.",
          true
        );
        return;
      }

      delete parcours.dataset.erreurChargement;
      parcours.replaceChildren();
      option(parcours, "", "— choisis le parcours ou le tronc commun —", true);
      option(parcours, "tronc_commun", "Tronc commun (sans parcours spécifique)", false, true);
      rows.forEach(function (row) {
        option(parcours, row.id, libelleParcours(row), false, true);
      });

      if (rows.some(function (row) { return row.niveau_a_confirmer; })) {
        definirInfo(
          "Certains intitulés viennent de l'ancien référentiel et n'ont pas de niveau confirmé. Ils sont signalés ; choisis-les uniquement si c'est bien ton parcours.",
          false
        );
      } else if (rows.length) {
        definirInfo(
          "Choisis le parcours exact. « Tronc commun » n'est valable que si aucun parcours spécifique n'est offert pour cette mention et ce niveau dans ta composante.",
          false
        );
      } else {
        definirInfo(
          "Aucun parcours nommé n'est répertorié à ce niveau. Le tronc commun n'est possible que si cette mention et ce niveau sont réellement proposés dans ta composante.",
          false
        );
      }

      parcours.disabled = false;
      parcours.required = true;
    }

    mention.addEventListener("change", function () {
      // Une mention différente invalide systématiquement le niveau précédent.
      niveau.value = "";
      niveau.disabled = !mention.value;
      actualiserObligations();
      charger();
    });
    niveau.addEventListener("change", charger);

    formulaire.addEventListener("submit", function (event) {
      if (parcours.dataset.erreurChargement === "true") {
        event.preventDefault();
        definirInfo(
          "Le référentiel académique n'a pas pu être chargé. Réessaie ; le formulaire ne sera pas envoyé avec un choix par défaut.",
          true
        );
        parcours.focus();
        return;
      }
      actualiserObligations();
      if (mention.value && (!niveau.value || parcours.disabled || !parcours.value)) {
        event.preventDefault();
        definirInfo(
          "Pour un cercle national, choisis une mention, un niveau et une option de parcours/tronc commun.",
          true
        );
        (!niveau.value ? niveau : parcours).focus();
      }
    });

    niveau.disabled = !mention.value;
    actualiserObligations();
    if (mention.value && niveau.value) {
      charger();
    } else {
      resetParcours();
      actualiserObligations();
    }
  }

  initialiserRecherche();
  initialiserCreation();
})();
