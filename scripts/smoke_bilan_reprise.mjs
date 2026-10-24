import fs from "node:fs";
import vm from "node:vm";
import { JSDOM } from "jsdom";

const source = fs.readFileSync("app/static/js/bilan-reprise.js", "utf8");
const now = Date.now();
const userId = "7";
const prefix = "mitaridala:bilan-reprise:v1:" + userId + ":";
const keys = {
  activity: prefix + "derniere-activite",
  summary: prefix + "dernier-bilan",
  summaryFor: prefix + "bilan-pour-activite",
  lock: prefix + "verrou",
  tab: prefix + "onglet-actif",
};
const lastActivity = now - 4 * 60 * 60 * 1000;
const lastSummary = now - 24 * 60 * 60 * 1000;
const seed = {
  [keys.activity]: String(lastActivity),
  [keys.summary]: String(lastSummary),
  [keys.summaryFor]: String(lastActivity),
};

const data = {
  stats: { quiz: 1, documents: 1, tuteur: 1, jeux: 1 },
  activites: [{
    type: "quiz",
    matiere: "Mathématiques",
    score: 4,
    nb_questions: 5,
    pourcentage: 80,
    date: new Date(now - 60 * 60 * 1000).toISOString(),
  }],
  apprentissages: [{
    matiere: "Mathématiques",
    notion: "Fractions",
    score: 80,
    etat: "solide_a_confirmer",
    questions: 5,
    date: new Date(now - 60 * 60 * 1000).toISOString(),
  }],
  renforcer: [{
    matiere: "Mathématiques",
    notion: "Équations",
    score: 42,
    erreurs: 3,
    raison_code: "score_low",
    date: new Date(now - 60 * 60 * 1000).toISOString(),
  }],
  mission: {
    type: "active",
    active: true,
    etape: "comprendre",
    action: "tuteur",
    titre: "Débloquer une difficulté",
    matiere: "Mathématiques",
    notion: "Fractions",
    score: 42,
    objectif: "Comprendre une erreur puis pratiquer.",
    methode: "Tuteur IA puis quiz ciblé.",
    lien: "/session-apprentissage",
    libelle_action: "Reprendre",
  },
  methodes: [{
    titre: "Fiches de révision",
    description: "Réviser.",
    lien: "/mes-revisions",
  }],
  acces_ia: true,
  has_activity: true,
  has_learning_data: true,
};

const markup = `<!doctype html>
<html lang="fr"><body>
<div id="bilan-reprise-fond" data-user-key="7" data-endpoint="/api/apprentissage/bilan-reprise" hidden aria-hidden="true">
  <div class="bilan-reprise-voile" data-bilan-fermer></div>
  <section id="bilan-reprise-dialogue" role="dialog" aria-modal="true" tabindex="-1">
    <button id="bilan-reprise-fermer" data-bilan-i18n-aria="closeLabel"></button>
    <h2 id="bilan-reprise-titre" data-bilan-i18n="title"></h2>
    <p id="bilan-reprise-intro" data-bilan-i18n="intro"></p>
    <p id="bilan-reprise-periode"></p>
    <div id="bilan-reprise-stats"></div>
    <div id="bilan-reprise-activites"></div>
    <div id="bilan-reprise-apprentissages"></div>
    <div id="bilan-reprise-renforcer"></div>
    <div id="bilan-reprise-mission"></div>
    <div id="bilan-reprise-methodes"></div>
    <button id="bilan-reprise-continuer" data-bilan-i18n="close"></button>
    <a id="bilan-reprise-action" href="/session-apprentissage" hidden><span id="bilan-reprise-action-texte"></span></a>
  </section>
</div></body></html>`;

function creerDom(storageEntries, language = "fr") {
  const dom = new JSDOM(markup, {
    url: "https://mitaridala.test/dashboard",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  Object.entries(storageEntries || {}).forEach(([key, value]) => window.localStorage.setItem(key, value));
  window.localStorage.setItem("mahay-langue", language);
  const appels = [];
  window.fetch = async (url, options) => {
    appels.push({ url, options });
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(data)) };
  };
  vm.runInNewContext(source, { window, document: window.document }, { filename: "bilan-reprise.js" });
  return { dom, window, appels };
}

const first = creerDom(seed, "mg");
await new Promise((resolve) => setTimeout(resolve, 0));
const root = first.window.document.getElementById("bilan-reprise-fond");
if (first.appels.length !== 1) throw new Error("The recap should be fetched after a four-hour idle period.");
if (root.hidden) throw new Error("The recap did not open after inactivity.");
if (first.window.document.getElementById("bilan-reprise-titre").textContent !== "Faly mihaona aminao indray") {
  throw new Error("The recap did not respect the saved Malagasy language preference.");
}
if (!first.window.document.getElementById("bilan-reprise-activites").textContent.includes("Matematika")) {
  // The quiz subject can remain French when it is the user's stored subject name;
  // only the labels/UI strings must be localized.
  if (!first.window.document.getElementById("bilan-reprise-activites").textContent.includes("Mathématiques")) {
    throw new Error("The real recent activity was not rendered in the recap.");
  }
}
if (first.window.localStorage.getItem(keys.summary) !== String(lastSummary)) {
  throw new Error("Opening the recap must not mark it as acknowledged.");
}
if (first.window.localStorage.getItem(keys.summaryFor) !== String(lastActivity)) {
  throw new Error("Opening the recap must not suppress it on reload before dismissal.");
}
if (!first.window.localStorage.getItem(keys.lock)) throw new Error("The cross-tab lock was not held while the recap was open.");

// Closing the tab while the dialog is open must leave the recap unacknowledged
// and release the lock, so the next load can show it again.
first.window.dispatchEvent(new first.window.Event("pagehide"));
if (first.window.localStorage.getItem(keys.summary) !== String(lastSummary)) {
  throw new Error("Page exit while open incorrectly acknowledged the recap.");
}
if (first.window.localStorage.getItem(keys.lock)) throw new Error("Page exit while open did not release the lock.");
if (first.window.sessionStorage.getItem(keys.tab) !== null) {
  throw new Error("Page exit while open must allow the next load to retry.");
}
const retryStorage = {};
for (let i = 0; i < first.window.localStorage.length; i += 1) {
  const key = first.window.localStorage.key(i);
  retryStorage[key] = first.window.localStorage.getItem(key);
}
const retry = creerDom(retryStorage, "fr");
await new Promise((resolve) => setTimeout(resolve, 0));
if (retry.appels.length !== 1 || retry.window.document.getElementById("bilan-reprise-fond").hidden) {
  throw new Error("A reload that interrupted the recap should display it again.");
}

// Explicit dismissal records the recap; a fresh tab/refresh immediately after
// dismissal must not present a duplicate popup.
retry.window.document.getElementById("bilan-reprise-continuer")
  .dispatchEvent(new retry.window.MouseEvent("click", { bubbles: true }));
if (!retry.window.document.getElementById("bilan-reprise-fond").hidden) {
  throw new Error("The continue button did not close the recap.");
}
if (retry.window.localStorage.getItem(keys.summary) == null ||
    retry.window.localStorage.getItem(keys.summaryFor) !== retry.window.localStorage.getItem(keys.activity)) {
  throw new Error("Explicit dismissal did not persist the acknowledged recap.");
}
const acknowledgedStorage = {};
for (let i = 0; i < retry.window.localStorage.length; i += 1) {
  const key = retry.window.localStorage.key(i);
  acknowledgedStorage[key] = retry.window.localStorage.getItem(key);
}
const fresh = creerDom(acknowledgedStorage, "fr");
await new Promise((resolve) => setTimeout(resolve, 0));
if (fresh.appels.length !== 0 || !fresh.window.document.getElementById("bilan-reprise-fond").hidden) {
  throw new Error("An already acknowledged recap should not reopen on an ordinary fresh tab.");
}

console.log("Bilan reprise smoke passed: idle trigger, Malagasy copy, no premature acknowledgement, retry on interruption, and no duplicate after dismissal.");
