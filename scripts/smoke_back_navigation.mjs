import assert from "node:assert/strict";
import fs from "node:fs";
import { chromium } from "playwright";

const base = fs.readFileSync("app/templates/base.html", "utf8");
const css = fs.readFileSync("app/static/back-navigation.css", "utf8");
const js = fs.readFileSync("app/static/js/back-navigation.js", "utf8");

assert.match(base, /class="navigation-retour-globale"/, "Le bouton global doit être dans le layout partagé.");
assert.match(base, /data-navigation-retour/, "Le lien de retour doit avoir son marqueur fonctionnel.");
assert.match(base, /back-navigation\.css/, "La feuille de style doit être chargée globalement.");
assert.match(base, /js\/back-navigation\.js/, "Le script doit être chargé globalement.");
assert.match(base, /_retour_secours/, "Une destination de secours doit exister pour les ouvertures directes.");
assert.match(css, /:focus-visible/, "Le contrôle doit être accessible au clavier.");
assert.match(css, /prefers-reduced-motion/, "Les animations doivent respecter le réglage d'accessibilité.");
assert.match(js, /originePrecedente\.origin === pageActuelle\.origin/, "Le retour historique doit rester sur la même origine.");

const navigateur = await chromium.launch({ headless: true });
const page = await navigateur.newPage({ viewport: { width: 320, height: 800 } });
const html = (fallback) => `<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">` +
  `<style>${css}</style></head><body>
  <main style="padding:12px;max-width:100%;box-sizing:border-box">
    <nav class="navigation-retour-globale" aria-label="Navigation de la page">
      <a class="navigation-retour-bouton" data-navigation-retour href="${fallback}" title="Revenir à la page précédente">
        <span class="navigation-retour-fleche" aria-hidden="true">←</span><span>Retour</span>
      </a>
    </nav><h1>Page de test</h1>
  </main><script>${js}</script></body></html>`;

await page.route("https://mitaridala.test/**", async (route) => {
  const url = new URL(route.request().url());
  const pieces = url.pathname.replace(/\/$/, "").split("/").filter(Boolean);
  const fallback = pieces.length > 1 ? "/" + pieces.slice(0, -1).join("/") : "/dashboard";
  await route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: html(fallback) });
});

try {
  // Historique interne : le bouton revient à la page précédente du même site.
  await page.goto("https://mitaridala.test/previous");
  await page.goto("https://mitaridala.test/quiz/42");
  assert.equal(await page.locator("[data-navigation-retour]").innerText(), "← Retour");
  const bounds = await page.locator("[data-navigation-retour]").evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, height: r.height, width: r.width };
  });
  assert.ok(bounds.left >= 0 && bounds.right <= 320, "Le bouton doit rester dans l'écran mobile: " + JSON.stringify(bounds));
  assert.ok(bounds.height >= 44, "La zone tactile doit mesurer au moins 44px: " + JSON.stringify(bounds));
  await page.locator("[data-navigation-retour]").click();
  await page.waitForURL("https://mitaridala.test/previous");
  assert.equal(new URL(page.url()).pathname, "/previous");

  // Ouverture directe : sans referrer interne, le lien utilise un fallback parent sûr.
  const direct = await navigateur.newPage({ viewport: { width: 320, height: 800 } });
  await direct.goto("https://mitaridala.test/documents/123/quiz");
  assert.equal(await direct.locator("[data-navigation-retour]").getAttribute("href"), "/documents/123");
  await direct.locator("[data-navigation-retour]").click();
  await direct.waitForURL("https://mitaridala.test/documents/123");
  await direct.close();

  console.log("Smoke retour global OK : historique interne, URL directe, fallback parent et bouton mobile accessible.");
} finally {
  await navigateur.close();
}
