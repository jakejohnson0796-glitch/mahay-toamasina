/* Chargement des cibles scolaires du dépôt documentaire. */
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
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function addOption(select, value, label, selected) {
    const option = document.createElement("option");
    option.value = value == null ? "" : String(value);
    option.textContent = label;
    option.selected = Boolean(selected);
    select.appendChild(option);
  }

  function reset(select, label, disabled) {
    if (!select) return;
    select.replaceChildren();
    addOption(select, "", label, false);
    select.disabled = Boolean(disabled);
  }

  function init() {
    const scope = document.getElementById("portee_academique");
    const cycle = document.getElementById("cycle_scolaire");
    const level = document.getElementById("niveau_scolaire_id");
    const option = document.getElementById("option_scolaire_id");
    const establishment = document.getElementById("etablissement_scolaire_id");
    const block = document.getElementById("bloc-cible-scolaire");
    if (!scope || !cycle || !level || !option || !establishment || !block) return;

    const currentLevel = block.dataset.currentLevel || "";
    const currentOption = block.dataset.currentOption || "";
    let levelsRequest = 0;
    let optionsRequest = 0;
    let establishmentLoaded = false;

    function isSchoolScope() {
      return scope.value === "scolaire";
    }

    async function loadLevels() {
      const id = ++levelsRequest;
      const school = isSchoolScope();
      const cycleValue = cycle.value;
      reset(level, school && cycleValue ? "Chargement des classes…" : "Choisissez d’abord le cycle", true);
      reset(option, "Choisissez d’abord la classe", true);
      if (!school || !["college", "lycee"].includes(cycleValue)) return;

      const rows = await getJSON("/api/scolaire/niveaux?cycle=" + encodeURIComponent(cycleValue));
      if (id !== levelsRequest) return;
      reset(level, "— Choisissez la classe —", false);
      if (!Array.isArray(rows) || !rows.length) {
        reset(level, "Aucune classe vérifiée disponible", true);
        return;
      }

      let currentWasAdded = false;
      rows.forEach(function (row) {
        const selected = String(row.id) === String(currentLevel);
        currentWasAdded = currentWasAdded || selected;
        addOption(level, row.id, row.libelle, selected);
      });
      if (!currentWasAdded) level.value = "";
      level.disabled = false;
      if (level.value) await loadOptions();
    }

    async function loadOptions() {
      const id = ++optionsRequest;
      reset(option, level.value ? "Chargement des séries/options…" : "Choisissez d’abord la classe", true);
      if (!isSchoolScope() || !level.value || level.disabled) return;

      const rows = await getJSON("/api/scolaire/niveaux/" + encodeURIComponent(level.value) + "/options");
      if (id !== optionsRequest) return;
      reset(option, "— Aucune série/option précisée —", false);
      if (!Array.isArray(rows) || !rows.length) {
        option.disabled = false;
        return;
      }

      let currentWasAdded = false;
      rows.forEach(function (row) {
        const selected = String(row.id) === String(currentOption);
        currentWasAdded = currentWasAdded || selected;
        addOption(option, row.id, row.libelle_affiche || row.libelle, selected);
      });
      if (!currentWasAdded) option.value = "";
      option.disabled = false;
    }

    async function loadEstablishments() {
      if (establishmentLoaded) return;
      establishmentLoaded = true;
      reset(establishment, "Chargement des établissements vérifiés…", true);
      const rows = await getJSON("/api/scolaire/etablissements?limite=50");
      reset(establishment, "— Je préfère ne pas préciser —", false);
      if (!Array.isArray(rows)) return;
      rows.forEach(function (row) {
        const locality = [row.commune, row.region].filter(Boolean).join(" · ");
        addOption(establishment, row.id, row.nom + (locality ? " — " + locality : ""),
          String(row.id) === String(block.dataset.currentEstablishment || ""));
      });
      establishment.disabled = false;
    }

    function applyScope() {
      const visible = isSchoolScope();
      cycle.disabled = !visible;
      cycle.required = visible;
      level.required = visible;
      if (!visible) {
        levelsRequest++;
        optionsRequest++;
        reset(level, "Choisissez d’abord le cycle", true);
        reset(option, "Choisissez d’abord la classe", true);
        return;
      }
      if (cycle.value) loadLevels();
    }

    scope.addEventListener("change", applyScope);
    cycle.addEventListener("change", function () {
      level.value = "";
      option.value = "";
      loadLevels();
    });
    level.addEventListener("change", loadOptions);

    if (isSchoolScope()) {
      cycle.disabled = false;
      cycle.required = true;
      level.required = true;
      if (cycle.value) loadLevels();
    }
    loadEstablishments();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
