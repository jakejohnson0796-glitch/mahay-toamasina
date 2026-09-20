/* Cascade academique partagee : Universite -> Composante -> Mention
   -> Niveau -> Parcours. Utilisee par l'inscription et l'actualisation
   du profil pour eviter deux implementations divergentes. */
(function () {
  async function chargerJSON(url) {
    try {
      const reponse = await fetch(url);
      if (!reponse.ok) return [];
      return await reponse.json();
    } catch (_erreur) {
      return [];
    }
  }

  function ajouterOption(select, value, label, selected) {
    const option = document.createElement("option");
    option.value = String(value ?? "");
    option.textContent = label;
    option.selected = Boolean(selected);
    select.appendChild(option);
  }

  function initialiser(formulaire) {
    const universite = document.getElementById(formulaire.dataset.universiteId || "universite_id");
    const composante = document.getElementById(formulaire.dataset.composanteId || "composante_id");
    const mention = document.getElementById(formulaire.dataset.mentionId || "mention_id");
    const niveau = document.getElementById(formulaire.dataset.niveauId || "niveau");
    const filiere = document.getElementById(formulaire.dataset.filiereId || "filiere_id");
    const infoTronc = document.getElementById(formulaire.dataset.infoTroncId || "info-tronc-commun");
    if (!universite || !composante || !mention || !niveau || !filiere) return;

    let sequence = 0;
    const courant = {
      universite: formulaire.dataset.currentUniversite || "",
      composante: formulaire.dataset.currentComposante || "",
      mention: formulaire.dataset.currentMention || "",
      niveau: formulaire.dataset.currentNiveau || "",
      filiere: formulaire.dataset.currentFiliere || "",
    };

    function resetComposantes() {
      composante.innerHTML = "";
      ajouterOption(composante, "", "— choisissez d'abord votre universite —", false);
      composante.disabled = true;
    }

    function resetMentions() {
      mention.innerHTML = "";
      ajouterOption(mention, "", "— choisissez d'abord votre composante —", false);
      mention.disabled = true;
    }

    function resetNiveau() {
      niveau.value = "";
      niveau.disabled = true;
    }

    function resetFilieres() {
      filiere.innerHTML = "";
      ajouterOption(filiere, "", "— choisissez d'abord votre niveau —", false);
      filiere.disabled = true;
      if (infoTronc) infoTronc.hidden = true;
    }

    async function chargerComposantes(valeur = "") {
      const idSequence = ++sequence;
      resetComposantes();
      resetMentions();
      resetNiveau();
      resetFilieres();
      if (!universite.value) return;

      const rows = await chargerJSON("/api/academique/universites/" + encodeURIComponent(universite.value) + "/composantes");
      if (idSequence !== sequence) return;
      ajouterOption(composante, "", "— choisissez votre composante —", false);
      rows.forEach(function (row) {
        ajouterOption(composante, row.id, row.nom, String(row.id) === String(valeur));
      });
      composante.disabled = rows.length === 0;
      if (!rows.length) {
        composante.innerHTML = "";
        ajouterOption(composante, "", "— aucune composante disponible pour l'instant —", false);
      }
      if (valeur && rows.some(function (row) { return String(row.id) === String(valeur); })) {
        await chargerMentions(valeur, courant.mention);
      }
    }

    async function chargerMentions(composanteId = "", valeur = "") {
      const idSequence = ++sequence;
      resetMentions();
      resetNiveau();
      resetFilieres();
      if (!composanteId) return;

      const rows = await chargerJSON("/api/academique/composantes/" + encodeURIComponent(composanteId) + "/mentions");
      if (idSequence !== sequence) return;
      ajouterOption(mention, "", "— choisissez votre mention —", false);
      rows.forEach(function (row) {
        ajouterOption(mention, row.id, row.nom, String(row.id) === String(valeur));
      });
      mention.disabled = rows.length === 0;
      if (!rows.length) {
        mention.innerHTML = "";
        ajouterOption(mention, "", "— aucune mention disponible pour l'instant —", false);
      }
      if (valeur && rows.some(function (row) { return String(row.id) === String(valeur); })) {
        niveau.disabled = false;
        niveau.value = courant.niveau || "";
        if (niveau.value) await chargerFilieres(composanteId, valeur);
      }
    }

    async function chargerFilieres(composanteId = "", mentionId = "") {
      const idSequence = ++sequence;
      filiere.innerHTML = "";
      ajouterOption(filiere, "", "— choisissez votre parcours —", false);
      filiere.disabled = true;
      if (infoTronc) infoTronc.hidden = true;
      if (!composanteId || !mentionId || !niveau.value) return;

      const url = "/api/academique/composantes/" + encodeURIComponent(composanteId)
        + "/mentions/" + encodeURIComponent(mentionId)
        + "/filieres?niveau=" + encodeURIComponent(niveau.value);
      const rows = await chargerJSON(url);
      if (idSequence !== sequence) return;
      if (!rows.length) {
        filiere.innerHTML = "";
        ajouterOption(filiere, "", "— aucun parcours specifique a ce niveau —", false);
        if (infoTronc) infoTronc.hidden = false;
      } else {
        rows.forEach(function (row) {
          ajouterOption(filiere, row.id, row.nom, String(row.id) === String(courant.filiere));
        });
        if (courant.filiere && !rows.some(function (row) { return String(row.id) === String(courant.filiere); })) {
          courant.filiere = "";
        }
      }
      filiere.disabled = false;
    }

    universite.addEventListener("change", function () {
      courant.composante = "";
      courant.mention = "";
      courant.niveau = "";
      courant.filiere = "";
      chargerComposantes("");
    });

    composante.addEventListener("change", function () {
      courant.mention = "";
      courant.niveau = "";
      courant.filiere = "";
      chargerMentions(composante.value, "");
    });

    mention.addEventListener("change", function () {
      courant.niveau = "";
      courant.filiere = "";
      resetNiveau();
      resetFilieres();
      if (mention.value) niveau.disabled = false;
    });

    niveau.addEventListener("change", function () {
      courant.filiere = "";
      chargerFilieres(composante.value, mention.value);
    });

    if (universite.value) {
      chargerComposantes(courant.composante);
    }
  }

  document.querySelectorAll("[data-cascade-academique]").forEach(initialiser);
})();
