import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

const code = await readFile(new URL("../app/static/js/pwa.js", import.meta.url), "utf8");
const key = "mitaridala:quiz-draft:v1:4:91";
const html = '<!doctype html><form data-quiz-form data-quiz-adaptatif="0" data-quiz-mode-examen="0" data-quiz-owner="4" data-quiz-tentative-id="91"><input type="hidden" name="_csrf" value="secret-csrf"><input type="radio" name="question_0" value="0"><input type="radio" name="question_0" value="1"><input type="radio" name="confiance_0" value="forte"><p data-quiz-draft-status></p><button data-quiz-draft-clear hidden></button></form>';

function ouvrir(path, brouillon, markup = html, echecEcriture = false) {
  const dom = new JSDOM(markup, { url: "https://mitaridala.test" + path, runScripts: "outside-only" });
  if (brouillon) dom.window.localStorage.setItem(key, brouillon);
  if (echecEcriture) {
    dom.window.Storage.prototype.setItem = function () { throw new Error("quota dépassé"); };
  }
  dom.window.eval(code);
  return dom;
}

const dom = ouvrir("/quiz/91");
const form = dom.window.document.querySelector("form");
for (const input of form.querySelectorAll('input[type="radio"]')) {
  input.checked = true;
  input.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
}
const saved = dom.window.localStorage.getItem(key);
assert.ok(saved, "les choix doivent être enregistrés localement");
assert.equal(saved.includes("secret-csrf"), false, "le jeton CSRF ne doit pas être stocké");
assert.equal(JSON.parse(saved).reponses.question_0, "1");
assert.equal(JSON.parse(saved).confiances.confiance_0, "forte");

Object.defineProperty(dom.window.navigator, "onLine", { configurable: true, value: false });
const submit = new dom.window.Event("submit", { bubbles: true, cancelable: true });
form.dispatchEvent(submit);
assert.equal(submit.defaultPrevented, true);
assert.match(form.querySelector("[data-quiz-draft-status]").textContent, /Connexion indisponible/);

const reprise = ouvrir("/quiz/91", saved);
assert.equal(reprise.window.document.querySelector('input[name="question_0"][value="1"]').checked, true);
assert.equal(reprise.window.document.querySelector('input[name="question_0"][value="0"]').checked, false);
assert.match(reprise.window.document.querySelector("[data-quiz-draft-status]").textContent, /Brouillon retrouvé/);

const resultat = ouvrir("/quiz/91/resultat", saved);
assert.equal(resultat.window.localStorage.getItem(key), null);

const examenHtml = html.replace('data-quiz-mode-examen="0"', 'data-quiz-mode-examen="1"');
const examen = ouvrir("/quiz/91", null, examenHtml);
examen.window.document.querySelector('input[name="question_0"]').checked = true;
examen.window.document.querySelector('input[name="question_0"]').dispatchEvent(new examen.window.Event("change", { bubbles: true }));
assert.equal(examen.window.localStorage.getItem(key), null);

const stockagePlein = ouvrir("/quiz/91", null, html, true);
const reponseSansStockage = stockagePlein.window.document.querySelector('input[name="question_0"][value="1"]');
reponseSansStockage.checked = true;
reponseSansStockage.dispatchEvent(new stockagePlein.window.Event("change", { bubbles: true }));
Object.defineProperty(stockagePlein.window.navigator, "onLine", { configurable: true, value: false });
const envoiSansStockage = new stockagePlein.window.Event("submit", { bubbles: true, cancelable: true });
stockagePlein.window.document.querySelector("form").dispatchEvent(envoiSansStockage);
assert.equal(envoiSansStockage.defaultPrevented, true);
assert.match(stockagePlein.window.document.querySelector("[data-quiz-draft-status]").textContent, /n'a pas pu enregistrer/);

console.log("Quiz draft recovery smoke passed.");
