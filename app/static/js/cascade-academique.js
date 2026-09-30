/* Cascade academique partagee : un seul chargement reseau par universite,
   puis filtrage local Composante -> Mention -> Niveau -> Parcours. */
(function () {
  "use strict";

  async function chargerJSON(url) {
    try {
      const reponse = await fetch(url, {
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });
      if (!reponse.ok) return null;
      return await reponse.json();
    } catch (_erreur) {
      return null;
    }
  }

  function ajouterOption(select, value, label, selected) {
    const option = document.createElement("option");
    option.value = String(value ?? "");
    option.textContent = label;
    option.selected = Boolean(selected);
    select.appendChild(option);
  }

  function resetSelect(select, placeholder) {
    select.innerHTML = "";
    ajouterOption(select, "", placeholder, false);
    select.disabled = true;
  }

  function initialiser(formulaire) {
    const universite = document.getElementById(formulaire.dataset.universiteId || "universite_id");
    const composante = document.getElementById(formulaire.dataset.composanteId || "composante_id");
    const mention = document.getElementById(formulaire.dataset.mentionId || "mention_id");
    const niveau = document.getElementById(formulaire.dataset.niveauId || "niveau");
    const filiere = document.getElementById(formulaire.dataset.filiereId || "filiere_id");
    const infoTronc = document.getElementById(formulaire.dataset.infoTroncId || "info-tronc-commun");

    if (!universite || !composante || !mention || !niveau || !filiere) return;

    let catalogue = null;
    let chargement = 0;
    const courant = {
      composante: formulaire.dataset.currentComposante || "",
      mention: formulaire.dataset.currentMention || "",
      niveau: formulaire.dataset.currentNiveau || "",
      filiere: formulaire.dataset.currentFiliere || "",
    };

    function resetComposantes() {
      resetSelect(composante, "— choisissez votre université —");
    }

    function resetMentions() {
      resetSelect(mention, "— choisissez d'abord votre composante —");
    }

    function resetNiveau() {
      niveau.value = "";
      niveau.disabled = true;
      courant.niveau = "";
    }

    function resetFilieres(message) {
      resetSelect(filiere, message || "— choisissez d'abord votre niveau —");
      if (infoTronc) infoTronc.hidden = true;
      courant.filiere = "";
    }

    function trouverComposante(id) {
      if (!catalogue || !Array.isArray(catalogue.composantes)) return null;
      return catalogue.composantes.find(function (row) {
        return String(row.id) === String(id);
      }) || null;
    }

    function trouverMention(id) {
      const c = trouverComposante(composante.value);
      if (!c) return null;
      return (c.mentions || []).find(function (row) {
        return String(row.id) === String(id);
      }) || null;
    }

    function remplirComposantes(valeur) {
      resetComposantes();
      if (!catalogue || !Array.isArray(catalogue.composantes)) {
        ajouterOption(composante, "", "— aucune composante disponible pour l'instant —", false);
        return;
      }
      ajouterOption(composante, "", "— choisissez votre composante —", false);
      catalogue.composantes.forEach(function (row) {
        ajouterOption(composante, row.id, row.nom, String(row.id) === String(valeur || ""));
      });
      composante.disabled = catalogue.composantes.length === 0;
    }

    function remplirMentions(composanteId, valeur) {
      resetMentions();
      const c = trouverComposante(composanteId);
      const rows = c ? (c.mentions || []) : [];
      ajouterOption(mention, "", "— choisissez votre mention —", false);
      rows.forEach(function (row) {
        ajouterOption(mention, row.id, row.nom, String(row.id) === String(valeur || ""));
      });
      mention.disabled = rows.length === 0;
      if (!rows.length) {
        mention.innerHTML = "";
        ajouterOption(mention, "", "— aucune mention disponible pour l'instant —", false);
      }
    }

    function remplirFilieres() {
      resetFilieres();
      const m = trouverMention(mention.value);
      const rows = m ? (m.filieres || []) : [];
      const niveauChoisi = niveau.value;
      const visibles = rows.filter(function (row) {
        return !row.niveau || String(row.niveau) === String(niveauChoisi);
      });

      if (!visibles.length) {
        if (infoTronc) infoTronc.hidden = false;
        filiere.disabled = false;
        return;
      }

      visibles.forEach(function (row) {
        const label = (
          niveauChoisi === "L3" &&
          String(row.nom || "").toLowerCase().includes("entreprises agro-industrielles") &&
          String(row.nom || "").toLowerCase().includes("commerce international")
        ) ? "Commerce International — Entreprises agro-industrielles" : row.nom;
        ajouterOption(filiere, row.id, label, String(row.id) === String(courant.filiere || ""));
      });
      filiere.disabled = false;
    }

    async function chargerCatalogue(valeurUniversite) {
      const token = ++chargement;
      catalogue = null;
      resetComposantes();
      resetMentions();
      resetNiveau();
      resetFilieres();
      if (!valeurUniversite) return;

      const rows = await chargerJSON(
        "/api/academique/universites/" + encodeURIComponent(valeurUniversite) + "/cascade"
      );
      if (token !== chargement) return;
      if (!rows || !Array.isArray(rows.composantes)) {
        ajouterOption(composante, "", "— chargement impossible, réessayez —", false);
        if (infoTronc) infoTronc.hidden = true;
        return;
      }

      catalogue = rows;
      remplirComposantes(courant.composante);
      const composanteSelectionnee = trouverComposante(composante.value);
      if (composanteSelectionnee) {
        remplirMentions(composante.value, courant.mention);
        if (mention.value) {
          niveau.disabled = false;
          niveau.value = courant.niveau || "";
          if (niveau.value) remplirFilieres();
        }
      }
    }

    universite.addEventListener("change", function () {
      courant.composante = "";
      courant.mention = "";
      courant.niveau = "";
      courant.filiere = "";
      chargerCatalogue(universite.value);
    });

    composante.addEventListener("change", function () {
      courant.mention = "";
      courant.niveau = "";
      courant.filiere = "";
      resetMentions();
      resetNiveau();
      resetFilieres();
      remplirMentions(composante.value, "");
    });

    mention.addEventListener("change", function () {
      courant.mention = mention.value;
      courant.niveau = "";
      courant.filiere = "";
      resetNiveau();
      resetFilieres();
      if (mention.value) {
        niveau.disabled = false;
        niveau.focus();
      }
    });

    niveau.addEventListener("change", function () {
      courant.niveau = niveau.value;
      courant.filiere = "";
      remplirFilieres();
    });

    // Compatibilite : un profil peut arriver avec des valeurs precedentes.
    if (universite.value) {
      chargerCatalogue(universite.value);
    }
  }

  function demarrer() {
    document.querySelectorAll("[data-cascade-academique]").forEach(initialiser);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", demarrer, { once: true });
  } else {
    demarrer();
  }
})();
