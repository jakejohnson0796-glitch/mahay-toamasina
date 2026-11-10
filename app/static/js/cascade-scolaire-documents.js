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
    const subjectSelect = document.getElementById("matiere_scolaire_select");
    const subjectId = document.getElementById("matiere_scolaire_id");
    const subjectText = document.getElementById("matiere");
    const block = document.getElementById("bloc-cible-scolaire");
    const bepcBlock = document.getElementById("bloc-bepc-session-2027");
    const bepcParcours = document.getElementById("bepc_session_2027_parcours");
    const documentType = document.getElementById("type_document");
    const documentYear = document.getElementById("annee");
    if (!scope || !cycle || !level || !option || !establishment || !block) return;

    const currentLevel = block.dataset.currentLevel || "";
    const currentOption = block.dataset.currentOption || "";
    let levelsRequest = 0;
    let optionsRequest = 0;
    let subjectsRequest = 0;
    let establishmentLoaded = false;

    function isSchoolScope() {
      return scope.value === "scolaire";
    }

    function updateBepcProgrammeField() {
      if (!bepcBlock || !bepcParcours || !documentType || !documentYear) return;
      const selectedLevel = level.selectedOptions && level.selectedOptions[0];
      const levelLabel = selectedLevel ? selectedLevel.textContent.trim().toLocaleLowerCase("fr") : "";
      const visible = isSchoolScope()
        && cycle.value === "college"
        && levelLabel === "3e"
        && ["annale", "corrige"].includes(documentType.value)
        && documentYear.value === "2027";
      bepcBlock.hidden = !visible;
      bepcParcours.disabled = !visible;
      bepcParcours.required = visible;
      if (!visible) bepcParcours.value = "";
    }

    async function loadLevels() {
      const id = ++levelsRequest;
      const school = isSchoolScope();
      const cycleValue = cycle.value;
      reset(level, school && cycleValue ? "Chargement des classes…" : "Choisissez d’abord le cycle", true);
      reset(option, "Choisissez d’abord la classe", true);
      updateBepcProgrammeField();
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
      updateBepcProgrammeField();
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
        await loadSubjects();
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
      await loadSubjects();
    }

    async function loadSubjects() {
      const requestId = ++subjectsRequest;
      if (subjectId) subjectId.value = "";
      if (!subjectSelect) return;
      reset(
        subjectSelect,
        isSchoolScope() && level.value
          ? "Chargement des matières vérifiées…"
          : "Disponible pour les parcours collège/lycée",
        true
      );
      if (!isSchoolScope() || !level.value || level.disabled) return;

      let url = "/api/scolaire/niveaux/" + encodeURIComponent(level.value) + "/matieres";
      if (option.value) url += "?option_id=" + encodeURIComponent(option.value);
      const rows = await getJSON(url);
      if (requestId !== subjectsRequest) return;

      reset(subjectSelect, "— Choisissez une matière (facultatif) —", false);
      if (!Array.isArray(rows) || !rows.length) {
        reset(subjectSelect, "Aucune matière vérifiée : utilisez la saisie libre", true);
        return;
      }
      rows.forEach(function (row) {
        addOption(subjectSelect, row.id, row.libelle, false);
      });
      subjectSelect.disabled = false;
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
        subjectsRequest++;
        reset(level, "Choisissez d’abord le cycle", true);
        reset(option, "Choisissez d’abord la classe", true);
        reset(subjectSelect, "Disponible pour les parcours collège/lycée", true);
        if (subjectId) subjectId.value = "";
        updateBepcProgrammeField();
        return;
      }
      if (cycle.value) loadLevels();
      updateBepcProgrammeField();
    }

    scope.addEventListener("change", applyScope);
    cycle.addEventListener("change", function () {
      level.value = "";
      option.value = "";
      if (subjectId) subjectId.value = "";
      loadLevels();
      updateBepcProgrammeField();
    });
    level.addEventListener("change", function () {
      if (subjectId) subjectId.value = "";
      loadOptions();
      updateBepcProgrammeField();
    });
    if (documentType) documentType.addEventListener("change", updateBepcProgrammeField);
    if (documentYear) {
      documentYear.addEventListener("input", updateBepcProgrammeField);
      documentYear.addEventListener("change", updateBepcProgrammeField);
    }
    option.addEventListener("change", loadSubjects);
    if (subjectSelect) {
      subjectSelect.addEventListener("change", function () {
        const selected = subjectSelect.selectedOptions && subjectSelect.selectedOptions[0];
        if (subjectId) subjectId.value = subjectSelect.value || "";
        if (subjectText && subjectSelect.value && selected) {
          subjectText.value = selected.textContent;
          subjectText.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
    }
    if (subjectText) {
      subjectText.addEventListener("input", function () {
        if (!subjectId || !subjectId.value || !subjectSelect) return;
        const selected = subjectSelect.selectedOptions && subjectSelect.selectedOptions[0];
        if (!selected || subjectText.value !== selected.textContent) {
          subjectId.value = "";
          subjectSelect.value = "";
        }
      });
    }

    if (isSchoolScope()) {
      cycle.disabled = false;
      cycle.required = true;
      level.required = true;
      if (cycle.value) loadLevels();
    }
    updateBepcProgrammeField();
    loadEstablishments();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
