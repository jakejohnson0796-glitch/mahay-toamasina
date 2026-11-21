(function () {
  "use strict";

  const form = document.querySelector("[data-presence-bulk-form]");
  if (!form) return;

  const payload = form.querySelector("[data-presence-payload]");
  const summary = form.querySelector("[data-presence-summary]");
  const submit = form.querySelector("[data-presence-submit]");
  const rows = Array.from(form.querySelectorAll("[data-presence-row]"));

  function compter() {
    const resultats = { present: 0, absent: 0, retard: 0, excuse: 0, a_renseigner: 0 };
    rows.forEach(function (row) {
      const select = row.querySelector("[data-presence-status]");
      const valeur = select ? select.value : "a_renseigner";
      if (Object.prototype.hasOwnProperty.call(resultats, valeur)) resultats[valeur] += 1;
    });
    return resultats;
  }

  function actualiserResume() {
    const compteurs = compter();
    if (!summary) return;
    summary.textContent = rows.length
      ? "Présents : " + compteurs.present + " · Absents : " + compteurs.absent +
        " · Retards : " + compteurs.retard + " · À renseigner : " + compteurs.a_renseigner
      : "Aucun apprenant à pointer.";
  }

  form.querySelectorAll("[data-presence-status]").forEach(function (select) {
    select.addEventListener("change", actualiserResume);
  });

  const allPresent = form.querySelector("[data-presence-all-present]");
  if (allPresent) {
    allPresent.addEventListener("click", function () {
      form.querySelectorAll("[data-presence-status]").forEach(function (select) {
        select.value = "present";
      });
      actualiserResume();
    });
  }

  form.addEventListener("submit", function (event) {
    const lignes = rows.map(function (row) {
      const status = row.querySelector("[data-presence-status]");
      const note = row.querySelector("[data-presence-note]");
      return {
        utilisateur_id: Number(row.getAttribute("data-presence-user-id")),
        statut: status ? status.value : "a_renseigner",
        justificatif: note ? note.value : ""
      };
    });
    if (!lignes.length || lignes.some(function (line) {
      return !Number.isSafeInteger(line.utilisateur_id) || line.utilisateur_id <= 0;
    })) {
      event.preventDefault();
      if (summary) summary.textContent = "Impossible d'enregistrer un registre vide ou invalide.";
      return;
    }
    payload.value = JSON.stringify(lignes);
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Enregistrement…";
    }
  });

  actualiserResume();
})();
