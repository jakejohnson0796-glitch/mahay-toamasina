import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import { chromium } from "playwright";

const root = process.cwd();
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const script = read("app/static/js/cercles-list.js");
const schoolSearchScript = read("app/static/js/cascade-scolaire-cercles.js");
const academicUiCss = read("app/static/parcours-academique-ui.css");
const baseTemplate = read("app/templates/base.html");
const template = read("app/templates/cercles_list.html");

assert.match(
  template,
  /id="creation-info-tronc-commun" hidden>/,
  "Le hint Tronc commun doit suivre l'attribut hidden, pas un display:none en ligne."
);
assert.doesNotMatch(
  template,
  /id="creation-info-tronc-commun" style="display:none;"/,
  "Un style en ligne empêcherait le hint d'apparaître après hidden=false."
);

assert.match(template, /<fieldset id="filtres-scolaires"/, "Les filtres collège/lycée doivent être groupés.");
assert.match(template, /<fieldset id="filtres-universitaires"/, "Les filtres universitaires doivent être groupés séparément.");
assert.match(schoolSearchScript, /schoolGroup\.hidden = university \|\| transversal/, "Le groupe scolaire doit se masquer pour les autres parcours.");
assert.match(schoolSearchScript, /universityGroup\.hidden = school \|\| transversal/, "Le groupe universitaire doit se masquer pour les autres parcours.");
assert.match(academicUiCss, /\.groupe-filtres-cercles\[hidden\]/, "Le groupe hidden doit rester masqué malgré les styles de page.");
assert.match(baseTemplate, /parcours-academique-ui\.css/, "Les styles de parcours doivent être chargés par la page.");

const html = `<!doctype html>
<html lang="fr"><head><meta charset="utf-8"></head><body>
  <form id="formulaire-recherche-cercles" action="/cercles">
    <select id="recherche_domaine_id"><option value="">Tous</option><option value="1">Domaine</option></select>
    <select id="recherche_mention_id">
      <option value="">Toutes</option><option value="1" data-domaine-id="1">Mention test</option>
    </select>
    <select id="recherche_niveau">
      <option value="">Tous</option><option value="L3">Licence 3</option>
    </select>
    <select id="recherche_filiere_id"><option value="">Tous les parcours</option></select>
    <button type="submit">Rechercher</button>
  </form>
  <form id="creer-cercle" data-formulaire-creation-cercle>
    <input id="nom" name="nom" value="Cercle de test" required>
    <select id="creation_mention_id" name="mention_id">
      <option value="">Aucune</option><option value="1" selected>Mention test</option>
    </select>
    <select id="creation_niveau" name="niveau">
      <option value="">Tous</option><option value="L3" selected>Licence 3</option>
    </select>
    <select id="creation_filiere_id" name="filiere_id"><option value="">Choisir</option></select>
    <p id="creation-info-tronc-commun" hidden>Aucun parcours spécifique.</p>
    <button type="submit">Créer</button>
  </form>
</body></html>`;

let apiCalls = 0;
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route(
    (url) => url.hostname === "mahay.test"
      && url.pathname === "/api/academique/mentions/1/parcours-nationaux"
      && url.searchParams.get("niveau") === "L3",
    async (route) => {
      apiCalls += 1;
      if (apiCalls === 1 || apiCalls === 3) {
        await route.abort("failed");
      } else if (apiCalls === 2) {
        await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([{ id: 17, nom: "Finance" }])
        });
      }
    }
  );
  await page.route("http://mahay.test/", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: html })
  );
  await page.goto("http://mahay.test/");
  await page.addScriptTag({ content: script });

  await page.waitForFunction(
    () => document.querySelector("#creer-cercle")?.dataset.parcoursState === "error"
  );
  const creationEnErreur = await page.evaluate(() => ({
    state: document.querySelector("#creer-cercle").dataset.parcoursState,
    selectDisabled: document.querySelector("#creation_filiere_id").disabled,
    hintHidden: document.querySelector("#creation-info-tronc-commun").hidden,
    message: document.querySelector("#creation_filiere_id-etat")?.textContent || "",
    hasRetry: Boolean(document.querySelector("#creation_filiere_id-etat button"))
  }));
  assert.equal(creationEnErreur.state, "error");
  assert.equal(creationEnErreur.selectDisabled, true);
  assert.equal(creationEnErreur.hintHidden, true);
  assert.match(creationEnErreur.message, /réessaie avant de créer le cercle/i);
  assert.equal(creationEnErreur.hasRetry, true);

  const soumissionBloquee = await page.evaluate(() => {
    const form = document.querySelector("#creer-cercle");
    let dejaBloquee = false;
    form.addEventListener("submit", (event) => {
      dejaBloquee = event.defaultPrevented;
      event.preventDefault();
    }, { once: true });
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    return dejaBloquee;
  });
  assert.equal(soumissionBloquee, true, "Une panne API ne doit pas créer par erreur un cercle de tronc commun.");

  await page.locator("#creation_filiere_id-etat button").click();
  await page.waitForFunction(
    () => document.querySelector("#creer-cercle")?.dataset.parcoursState === "ready"
  );
  const troncCommunValide = await page.evaluate(() => {
    const select = document.querySelector("#creation_filiere_id");
    const hint = document.querySelector("#creation-info-tronc-commun");
    return {
      selectDisabled: select.disabled,
      hintHidden: hint.hidden,
      hintDisplay: getComputedStyle(hint).display,
      option: select.options[0]?.textContent || "",
      hasError: Boolean(document.querySelector("#creation_filiere_id-etat"))
    };
  });
  assert.equal(troncCommunValide.selectDisabled, false);
  assert.equal(troncCommunValide.hintHidden, false);
  assert.notEqual(troncCommunValide.hintDisplay, "none");
  assert.match(troncCommunValide.option, /aucun parcours specifique/i);
  assert.equal(troncCommunValide.hasError, false);

  const soumissionTroncAutorisee = await page.evaluate(() => {
    const form = document.querySelector("#creer-cercle");
    let etaitDejaBloquee = false;
    form.addEventListener("submit", (event) => {
      etaitDejaBloquee = event.defaultPrevented;
      event.preventDefault();
    }, { once: true });
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    return etaitDejaBloquee;
  });
  assert.equal(soumissionTroncAutorisee, false, "Un résultat vide confirmé par l'API reste un état métier valide.");

  await page.locator("#recherche_mention_id").selectOption("1");
  await page.locator("#recherche_niveau").selectOption("L3");
  await page.waitForFunction(() => document.querySelector("#recherche_filiere_id-etat")?.textContent.includes("Impossible de charger"));
  const filtreEnErreur = await page.locator("#recherche_filiere_id-etat").textContent();
  assert.match(filtreEnErreur || "", /impossible de charger les parcours/i);
  await page.locator("#recherche_filiere_id-etat button").click();
  await page.waitForFunction(() =>
    Array.from(document.querySelector("#recherche_filiere_id").options).some((o) => o.textContent === "Finance")
  );
  assert.ok(apiCalls >= 4, "Les deux cascades doivent pouvoir réessayer une requête en échec.");

  // Vérifie le basculement réel des filtres scolaire/universitaire.
  const filterPage = await browser.newPage();
  await filterPage.setContent(`
    <!doctype html><html lang="fr"><body>
      <form id="formulaire-recherche-cercles">
        <select id="recherche_portee_academique">
          <option value="">Tous</option><option value="scolaire">Collège / lycée</option>
          <option value="universitaire">Université</option><option value="transversal">Transversal</option>
        </select>
        <fieldset id="filtres-scolaires" class="groupe-filtres-cercles">
          <select id="recherche_niveau_scolaire_id"><option value="">Classe</option></select>
          <select id="recherche_option_scolaire_id"><option value="">Série</option></select>
          <select id="recherche_etablissement_scolaire_id"><option value="">Établissement</option></select>
          <select id="recherche_matiere_scolaire_id"><option value="">Matière</option></select>
        </fieldset>
        <fieldset id="filtres-universitaires" class="groupe-filtres-cercles">
          <select id="recherche_domaine_id"><option value="">Domaine</option></select>
          <select id="recherche_mention_id"><option value="">Mention</option></select>
          <select id="recherche_niveau"><option value="">Niveau</option></select>
          <select id="recherche_filiere_id"><option value="">Parcours</option></select>
        </fieldset>
      </form>
    </body></html>`);
  await filterPage.addScriptTag({ content: schoolSearchScript });
  await filterPage.locator("#recherche_portee_academique").selectOption("scolaire");
  const filtresScolaires = await filterPage.evaluate(() => ({
    scolaireMasque: document.querySelector("#filtres-scolaires").hidden,
    universitaireMasque: document.querySelector("#filtres-universitaires").hidden,
    scolaireDesactive: document.querySelector("#recherche_niveau_scolaire_id").disabled,
    universitaireDesactive: document.querySelector("#recherche_domaine_id").disabled
  }));
  assert.deepEqual(filtresScolaires, {
    scolaireMasque: false, universitaireMasque: true,
    scolaireDesactive: false, universitaireDesactive: true
  });
  await filterPage.locator("#recherche_portee_academique").selectOption("universitaire");
  const filtresUniversitaires = await filterPage.evaluate(() => ({
    scolaireMasque: document.querySelector("#filtres-scolaires").hidden,
    universitaireMasque: document.querySelector("#filtres-universitaires").hidden,
    scolaireDesactive: document.querySelector("#recherche_niveau_scolaire_id").disabled,
    universitaireDesactive: document.querySelector("#recherche_domaine_id").disabled
  }));
  assert.deepEqual(filtresUniversitaires, {
    scolaireMasque: true, universitaireMasque: false,
    scolaireDesactive: true, universitaireDesactive: false
  });
  await filterPage.locator("#recherche_portee_academique").selectOption("transversal");
  const filtresTransversaux = await filterPage.evaluate(() => ({
    scolairesMasques: document.querySelector("#filtres-scolaires").hidden,
    universitairesMasques: document.querySelector("#filtres-universitaires").hidden,
    classeDesactivee: document.querySelector("#recherche_niveau_scolaire_id").disabled,
    domaineDesactive: document.querySelector("#recherche_domaine_id").disabled
  }));
  assert.deepEqual(filtresTransversaux, {
    scolairesMasques: true, universitairesMasques: true,
    classeDesactivee: true, domaineDesactive: true
  });
  await filterPage.locator("#recherche_portee_academique").selectOption("");
  const filtresTous = await filterPage.evaluate(() => ({
    scolairesMasques: document.querySelector("#filtres-scolaires").hidden,
    universitairesMasques: document.querySelector("#filtres-universitaires").hidden,
    classeDesactivee: document.querySelector("#recherche_niveau_scolaire_id").disabled,
    domaineDesactive: document.querySelector("#recherche_domaine_id").disabled
  }));
  assert.deepEqual(filtresTous, {
    scolairesMasques: false, universitairesMasques: false,
    classeDesactivee: false, domaineDesactive: false
  });

  console.log(JSON.stringify({
    checks: [
      "erreur API distincte d'une réponse vide",
      "soumission bloquée durant une panne du référentiel",
      "tronc commun affiché uniquement après une réponse vide valide",
      "hint réellement visible",
      "recherche réessayable après une panne",
      "filtres scolaire/universitaire/transversal réellement séparés et réinitialisables"
    ],
    apiCalls
  }, null, 2));
} finally {
  await browser.close();
}
