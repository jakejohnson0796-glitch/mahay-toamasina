/* Parcours scolaire des cercles : sélecteurs vérifiés et formulaire partagé. */
(function () {
  "use strict";

  async function getJSON(url) {
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) return null;
      const data = await response.json();
      return Array.isArray(data) ? data : null;
    } catch (_error) {
      return null;
    }
  }

  function addOption(select, value, label) {
    const node = document.createElement("option");
    node.value = value == null ? "" : String(value);
    node.textContent = label;
    select.appendChild(node);
  }

  function reset(select, label, disabled) {
    if (!select) return;
    select.replaceChildren();
    addOption(select, "", label);
    select.disabled = Boolean(disabled);
  }

  async function initCreation() {
    const scope = document.getElementById("creation_portee_academique");
    const universityBlock = document.getElementById("creation-bloc-universitaire");
    const schoolBlock = document.getElementById("creation-bloc-scolaire");
    const cycle = document.getElementById("creation_cycle_scolaire");
    const level = document.getElementById("creation_niveau_scolaire_id");
    const option = document.getElementById("creation_option_scolaire_id");
    const establishment = document.getElementById("creation_etablissement_scolaire_id");
    const reason = document.getElementById("raison");
    const reasonLabel = document.getElementById("creation-label-raison");
    const uniMention = document.getElementById("creation_mention_id");
    const uniLevel = document.getElementById("creation_niveau");
    const uniFiliere = document.getElementById("creation_filiere_id");

    if (!scope || !universityBlock || !schoolBlock || !cycle || !level || !option || !establishment) {
      return;
    }

    let levelRequest = 0;
    let optionRequest = 0;
    let establishmentLoaded = false;

    function isSchool() {
      return scope.value === "scolaire";
    }

    function applyScope() {
      const school = isSchool();
      universityBlock.hidden = school;
      schoolBlock.hidden = !school;

      [uniMention, uniLevel, uniFiliere].filter(Boolean).forEach(function (field) {
        field.disabled = school || (field === uniLevel && !uniMention.value) || (field === uniFiliere && (!uniMention.value || !uniLevel.value));
      });

      cycle.disabled = !school;
      cycle.required = school;
      level.required = school;
      if (reason) {
        reason.required = !school && Boolean(uniMention && uniMention.value && uniLevel && uniLevel.value);
      }
      if (reasonLabel) {
        reasonLabel.textContent = school
          ? "Raison (facultative)"
          : "Raison (obligatoire pour toute demande de cercle national universitaire)";
      }

      if (!school) {
        levelRequest++;
        optionRequest++;
        reset(level, "Choisissez d’abord le cycle scolaire", true);
        reset(option, "Choisissez d’abord la classe", true);
        reset(establishment, "Cercle national, sans établissement particulier", true);
      } else {
        loadEstablishments();
        if (cycle.value) loadLevels();
      }
    }

    async function loadLevels() {
      const ticket = ++levelRequest;
      const active = isSchool() && ["college", "lycee"].includes(cycle.value);
      reset(level, active ? "Chargement des classes…" : "Choisissez d’abord le cycle", true);
      reset(option, "Choisissez d’abord la classe", true);
      if (!active) return;

      const rows = await getJSON("/api/scolaire/niveaux?cycle=" + encodeURIComponent(cycle.value));
      if (ticket !== levelRequest) return;
      reset(level, "— Choisissez la classe —", false);
      if (!rows || !rows.length) {
        reset(level, "Aucune classe vérifiée disponible", true);
        return;
      }
      rows.forEach(function (row) { addOption(level, row.id, row.libelle); });
      level.disabled = false;
    }

    async function loadOptions() {
      const ticket = ++optionRequest;
      reset(option, level.value ? "Chargement des séries/options…" : "Choisissez d’abord la classe", true);
      if (!isSchool() || !level.value || level.disabled) return;
      const rows = await getJSON("/api/scolaire/niveaux/" + encodeURIComponent(level.value) + "/options");
      if (ticket !== optionRequest) return;
      reset(option, "— Aucune série/option précisée —", false);
      if (!rows || !rows.length) return;
      rows.forEach(function (row) { addOption(option, row.id, row.libelle); });
      option.disabled = false;
    }

    async function loadEstablishments() {
      if (establishmentLoaded) {
        establishment.disabled = !isSchool();
        return;
      }
      establishmentLoaded = true;
      reset(establishment, "Chargement des établissements vérifiés…", true);
      const rows = await getJSON("/api/scolaire/etablissements?limite=50");
      reset(establishment, "Cercle national, sans établissement particulier", false);
      if (rows) {
        rows.forEach(function (row) {
          const place = [row.commune, row.region].filter(Boolean).join(" · ");
          addOption(establishment, row.id, row.nom + (place ? " — " + place : ""));
        });
      }
      establishment.disabled = !isSchool();
    }

    scope.addEventListener("change", applyScope);
    cycle.addEventListener("change", loadLevels);
    level.addEventListener("change", loadOptions);
    [uniMention, uniLevel, uniFiliere].filter(Boolean).forEach(function (field) {
      field.addEventListener("change", applyScope);
    });

    const form = scope.closest("form");
    if (form) {
      form.addEventListener("submit", function (event) {
        applyScope();
        if (isSchool() && (!cycle.value || !level.value || level.disabled)) {
          event.preventDefault();
          if (!level.value) level.focus();
          return;
        }
        if (!isSchool() && uniLevel && !uniLevel.disabled && uniMention && uniMention.value && !uniLevel.value) {
          event.preventDefault();
          uniLevel.focus();
        }
      });
    }
    applyScope();
  }

  function initSearch() {
    const scope = document.getElementById("recherche_portee_academique");
    const level = document.getElementById("recherche_niveau_scolaire_id");
    const option = document.getElementById("recherche_option_scolaire_id");
    const establishment = document.getElementById("recherche_etablissement_scolaire_id");
    if (!scope) return;

    function updateFilters() {
      const school = scope.value === "scolaire";
      if (level) level.disabled = !school && Boolean(scope.value === "universitaire" || scope.value === "transversal");
      if (option) option.disabled = !school && Boolean(scope.value === "universitaire" || scope.value === "transversal");
      if (establishment) establishment.disabled = !school && Boolean(scope.value === "universitaire" || scope.value === "transversal");
    }
    scope.addEventListener("change", updateFilters);
    updateFilters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initCreation();
      initSearch();
    }, { once: true });
  } else {
    initCreation();
    initSearch();
  }
})();
