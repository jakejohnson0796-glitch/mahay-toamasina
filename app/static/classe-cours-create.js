(function () {
  "use strict";

  const form = document.querySelector("[data-cours-create-form]");
  if (!form) return;

  const scope = form.querySelector("[data-cours-scope]");
  const universityPanel = form.querySelector('[data-cours-panel="universitaire"]');
  const schoolPanel = form.querySelector('[data-cours-panel="scolaire"]');
  const cycle = form.querySelector("[data-cours-cycle]");
  const level = form.querySelector("[data-cours-level]");
  const option = form.querySelector("[data-cours-option]");
  const subject = form.querySelector("[data-cours-subject]");
  const status = form.querySelector("[data-cours-catalogue-status]");

  let levelRequestId = 0;
  let subjectRequestId = 0;

  function message(value) {
    if (status) status.textContent = value;
  }

  function reset(select, placeholder) {
    if (!select) return;
    select.replaceChildren(new Option(placeholder, ""));
    select.value = "";
    select.disabled = true;
  }

  function setPanel(panel, active) {
    if (!panel) return;
    panel.hidden = !active;
    panel.querySelectorAll("input, select, textarea").forEach(function (control) {
      control.disabled = !active;
    });
  }

  function actualiserPortee() {
    const scolaire = scope && scope.value === "scolaire";
    setPanel(universityPanel, !scolaire);
    setPanel(schoolPanel, scolaire);
    if (scolaire) {
      chargerNiveaux();
    } else {
      message("");
    }
  }

  async function lireJson(url) {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    if (!response.ok) {
      throw new Error("Le catalogue scolaire est temporairement indisponible.");
    }
    return response.json();
  }

  async function chargerNiveaux() {
    const id = ++levelRequestId;
    const cycleValue = cycle ? cycle.value : "";
    reset(level, cycleValue ? "Chargement des classes…" : "Choisir d'abord un cycle");
    reset(option, "Aucune série / option");
    reset(subject, "Choisir une classe d'abord");
    if (!cycleValue) {
      message("Choisis le cycle pour afficher ses classes vérifiées.");
      return;
    }

    message("Chargement des classes vérifiées…");
    try {
      const rows = await lireJson("/api/scolaire/niveaux?cycle=" + encodeURIComponent(cycleValue));
      if (id !== levelRequestId || !schoolPanel || schoolPanel.hidden) return;
      level.replaceChildren(new Option("Choisir une classe", ""));
      rows.forEach(function (item) {
        level.add(new Option(item.libelle + " · " + item.code, String(item.id)));
      });
      level.disabled = false;
      message(rows.length
        ? rows.length + " classe(s) vérifiée(s) disponible(s)."
        : "Aucune classe vérifiée n'est disponible pour ce cycle.");
    } catch (error) {
      if (id === levelRequestId) message(error.message || "Impossible de charger les classes.");
    }
  }

  async function chargerOptionsEtMatieres() {
    const id = ++subjectRequestId;
    const levelId = level ? level.value : "";
    reset(option, "Chargement des séries / options…");
    reset(subject, "Chargement des matières…");
    if (!levelId) {
      message("Choisis une classe pour afficher les matières de son programme.");
      return;
    }

    message("Chargement des séries et des matières du programme…");
    try {
      const [options, matieres] = await Promise.all([
        lireJson("/api/scolaire/niveaux/" + encodeURIComponent(levelId) + "/options"),
        lireJson("/api/scolaire/niveaux/" + encodeURIComponent(levelId) + "/matieres")
      ]);
      if (id !== subjectRequestId || !schoolPanel || schoolPanel.hidden) return;

      option.replaceChildren(new Option("Aucune série / option", ""));
      options.forEach(function (item) {
        option.add(new Option(item.libelle_affiche || item.libelle, String(item.id)));
      });
      option.disabled = false;

      remplirMatieres(matieres);
      message(matieres.length
        ? options.length + " série(s) / option(s) et " + matieres.length + " matière(s) vérifiée(s)."
        : "Aucune matière générale vérifiée pour cette classe. Vérifie la série ou choisis un autre niveau.");
    } catch (error) {
      if (id === subjectRequestId) message(error.message || "Impossible de charger le programme.");
    }
  }

  function remplirMatieres(rows) {
    reset(subject, "Choisir une matière");
    rows.forEach(function (item) {
      const label = item.libelle_malagasy
        ? item.libelle + " · " + item.libelle_malagasy
        : item.libelle;
      subject.add(new Option(label, String(item.id)));
    });
    subject.disabled = false;
  }

  async function chargerMatieresPourOption() {
    const id = ++subjectRequestId;
    const levelId = level ? level.value : "";
    const optionId = option ? option.value : "";
    reset(subject, "Chargement des matières…");
    if (!levelId) return;

    const query = optionId ? "?option_id=" + encodeURIComponent(optionId) : "";
    message("Mise à jour des matières selon la série sélectionnée…");
    try {
      const rows = await lireJson(
        "/api/scolaire/niveaux/" + encodeURIComponent(levelId) + "/matieres" + query
      );
      if (id !== subjectRequestId || !schoolPanel || schoolPanel.hidden) return;
      remplirMatieres(rows);
      message(rows.length
        ? rows.length + " matière(s) vérifiée(s) disponible(s)."
        : "Aucune matière vérifiée n'est associée à cette série / option.");
    } catch (error) {
      if (id === subjectRequestId) message(error.message || "Impossible de charger les matières.");
    }
  }

  if (scope) scope.addEventListener("change", actualiserPortee);
  if (cycle) cycle.addEventListener("change", chargerNiveaux);
  if (level) level.addEventListener("change", chargerOptionsEtMatieres);
  if (option) option.addEventListener("change", chargerMatieresPourOption);

  form.addEventListener("submit", function (event) {
    if (scope && scope.value === "scolaire") {
      if (!cycle || !cycle.value || !level || !level.value || !subject || !subject.value) {
        event.preventDefault();
        message("Complète le cycle, la classe et la matière avant de créer le cours.");
      }
    }
  });

  actualiserPortee();
})();
