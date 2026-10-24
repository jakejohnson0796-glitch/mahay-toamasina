/* Sélecteurs scolaires : niveau et options chargés depuis le référentiel validé. */
(function () {
  "use strict";

  async function getJSON(url) {
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "same-origin"
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function addOption(select, value, label, extra) {
    const option = document.createElement("option");
    option.value = value == null ? "" : String(value);
    option.textContent = label;
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        option.dataset[key] = String(extra[key]);
      });
    }
    select.appendChild(option);
  }

  function reset(select, placeholder, disabled) {
    if (!select) return;
    select.replaceChildren();
    addOption(select, "", placeholder);
    select.disabled = Boolean(disabled);
  }

  function init() {
    const cycle = document.getElementById("cycle_education");
    const profile = document.getElementById("role");
    const level = document.getElementById("niveau_scolaire_id");
    const option = document.getElementById("option_scolaire_id");
    const establishment = document.getElementById("etablissement_scolaire_id");
    if (!cycle || !profile || !level || !option || !establishment) return;

    let niveauxRequest = 0;
    let optionsRequest = 0;
    let catalogueEstablishmentsLoaded = false;

    function activeSchoolProfile() {
      return profile.value === "etudiant" || profile.value === "professeur";
    }

    async function loadLevels() {
      const requestId = ++niveauxRequest;
      const active = activeSchoolProfile() && ["college", "lycee"].includes(cycle.value);
      reset(level, active ? "Chargement des classes…" : "— Choisissez d’abord votre cycle —", true);
      reset(option, "— Choisissez d’abord une classe —", true);

      if (!active) return;

      const data = await getJSON("/api/scolaire/niveaux?cycle=" + encodeURIComponent(cycle.value));
      if (requestId !== niveauxRequest) return;
      reset(level, "— Choisissez votre classe —", false);

      if (!Array.isArray(data) || data.length === 0) {
        reset(level, "Aucune classe vérifiée disponible — réessayez plus tard", true);
        return;
      }

      data.forEach(function (item) {
        addOption(level, item.id, item.libelle, {
          code: item.code,
          cycle: item.cycle
        });
      });
      level.disabled = false;
    }

    async function loadOptions() {
      const requestId = ++optionsRequest;
      reset(option, level.value ? "Chargement des séries/options…" : "— Choisissez d’abord une classe —", true);
      if (!level.value || level.disabled) return;

      const data = await getJSON("/api/scolaire/niveaux/" + encodeURIComponent(level.value) + "/options");
      if (requestId !== optionsRequest) return;
      reset(option, "— Aucune série/option à préciser —", false);

      if (!Array.isArray(data) || data.length === 0) {
        option.disabled = false;
        return;
      }

      data.forEach(function (item) {
        addOption(option, item.id, item.libelle, { code: item.code });
      });
      option.disabled = false;
    }

    async function loadEstablishments() {
      if (catalogueEstablishmentsLoaded) return;
      catalogueEstablishmentsLoaded = true;
      reset(establishment, "Chargement des établissements vérifiés…", true);
      const data = await getJSON("/api/scolaire/etablissements?limite=50");
      reset(establishment, "— Je préfère ne pas préciser pour l’instant —", false);

      if (!Array.isArray(data)) {
        addOption(establishment, "", "Catalogue indisponible — vous pourrez le compléter plus tard");
        return;
      }
      data.forEach(function (item) {
        const locality = [item.commune, item.region].filter(Boolean).join(" · ");
        addOption(
          establishment,
          item.id,
          item.nom + (locality ? " — " + locality : ""),
          { secteur: item.secteur, type: item.type_etablissement }
        );
      });
      establishment.disabled = false;
    }

    cycle.addEventListener("change", function () {
      level.value = "";
      option.value = "";
      loadLevels();
    });
    level.addEventListener("change", loadOptions);
    profile.addEventListener("change", function () {
      if (activeSchoolProfile() && ["college", "lycee"].includes(cycle.value)) {
        loadLevels();
      } else {
        niveauxRequest += 1;
        optionsRequest += 1;
        reset(level, "— Choisissez d’abord votre cycle —", true);
        reset(option, "— Choisissez d’abord une classe —", true);
      }
    });

    if (cycle.value === "college" || cycle.value === "lycee") loadLevels();
    loadEstablishments();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
