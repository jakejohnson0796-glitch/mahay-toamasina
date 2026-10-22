import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const root = process.cwd();
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const base = read("app/templates/base.html");
const cssPaths = [...base.matchAll(/href="\/static\/([^"?]+\.css)(?:\?[^"]*)?"/g)]
  .map((match) => "app/static/" + match[1])
  .filter((value, index, all) => all.indexOf(value) === index);
const cssFromApp = cssPaths.map((file) =>
  '<style data-source="' + path.basename(file) + '">' +
  read(file).replace(/<\/style/gi, "<\\/style") +
  "</style>"
).join("\n");

function inlineCss(relativePath) {
  const source = read(relativePath);
  const match = source.match(/<style\b[^>]*>([\s\S]*?)<\/style>/i);
  if (!match) throw new Error("Styles inline introuvables dans " + relativePath);
  return "<style>" + match[1] + "</style>";
}
const cssForSheets = cssFromApp +
  inlineCss("app/templates/document_revision.html") +
  inlineCss("app/templates/classe_revision.html");

const fixtures = {
  document:
    '<div class="ai-learning-page document-revision-page">' +
      '<header class="document-revision-hero"><h1>Fiche de révision</h1>' +
      '<p class="document-revision-subtitle">Cours de mathématiques</p>' +
      '<p class="document-revision-meta">Générée le 22/10/2026 · Référence COURS-001</p></header>' +
      '<section class="document-revision-section">' +
        '<div class="document-revision-section-head"><span class="document-revision-number">01</span>' +
        '<div><h2>Notions essentielles</h2><p>Les concepts importants à retenir.</p></div></div>' +
        '<p class="document-revision-body ai-rendered-content" data-rendu>Le déterminant d’une matrice 2 × 2 vaut ad − bc.</p>' +
        '<div class="document-revision-card"><h3>Exemple</h3><p class="ai-rendered-content" data-rendu>Pour A, calcule ad − bc.</p></div>' +
        '<div class="document-revision-formula ai-rendered-content" data-rendu>det(A) = ad − bc</div>' +
      '</section>' +
    '</div>',
  personal:
    '<div class="classe-page fiche-revision-page">' +
      '<header class="fiche-revision-hero"><div class="fiche-revision-eyebrow">MITARIDALA · RÉVISION PERSONNELLE</div>' +
      '<h1>Fiche personnelle</h1><p class="fiche-revision-meta">Mathématiques · Séance 1</p></header>' +
      '<section class="fiche-revision-section">' +
        '<div class="fiche-revision-section-head"><span class="fiche-revision-number">01</span>' +
        '<div><h2>L’essentiel à retenir</h2><p>Une synthèse claire et utile.</p></div></div>' +
        '<p class="fiche-revision-texte ai-rendered-content" data-rendu>Le déterminant d’une matrice 2 × 2 vaut ad − bc.</p>' +
        '<article class="fiche-revision-card"><h3>Exemple</h3><p class="ai-rendered-content" data-rendu>Calcule le déterminant de A.</p></article>' +
        '<div class="fiche-revision-formule ai-rendered-content" data-rendu>det(A) = ad − bc</div>' +
      '</section>' +
    '</div>'
};

const targets = {
  document: [
    ["titre", ".document-revision-hero h1", ".document-revision-hero"],
    ["texte principal", ".document-revision-body", ".document-revision-section"],
    ["métadonnées", ".document-revision-meta", ".document-revision-hero"],
    ["description de section", ".document-revision-section-head p", ".document-revision-section"],
    ["texte de carte", ".document-revision-card p", ".document-revision-card"],
    ["formule", ".document-revision-formula", ".document-revision-formula"]
  ],
  personal: [
    ["titre", ".fiche-revision-hero h1", ".fiche-revision-hero"],
    ["texte principal", ".fiche-revision-texte", ".fiche-revision-section"],
    ["métadonnées", ".fiche-revision-meta", ".fiche-revision-hero"],
    ["description de section", ".fiche-revision-section-head p", ".fiche-revision-section"],
    ["texte de carte", ".fiche-revision-card p", ".fiche-revision-card"],
    ["formule", ".fiche-revision-formule", ".fiche-revision-formule"]
  ]
};

function rgb(value) {
  const match = value.match(/rgba?\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(",").map((part) => Number.parseFloat(part.trim()));
  if (parts.length < 3 || parts.slice(0, 3).some((part) => !Number.isFinite(part))) return null;
  return parts.slice(0, 3);
}
function luminance(values) {
  const linear = values.map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}
function contrast(first, second) {
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
const failures = [];
let checks = 0;
try {
  for (const theme of ["clair", "sombre"]) {
    for (const [kind, markup] of Object.entries(fixtures)) {
      const html = '<!doctype html><html lang="fr" data-theme="' + theme + '">' +
        '<head><meta charset="utf-8">' + cssForSheets + '</head>' +
        '<body><main class="main-clair main-clair-pleine-largeur"><div class="contenu-clair">' +
        markup + '</div></main></body></html>';
      await page.setContent(html);
      const values = await page.evaluate((kind) => {
        const specs = {
          document: [
            ["titre", ".document-revision-hero h1", ".document-revision-hero"],
            ["texte principal", ".document-revision-body", ".document-revision-section"],
            ["métadonnées", ".document-revision-meta", ".document-revision-hero"],
            ["description de section", ".document-revision-section-head p", ".document-revision-section"],
            ["texte de carte", ".document-revision-card p", ".document-revision-card"],
            ["formule", ".document-revision-formula", ".document-revision-formula"]
          ],
          personal: [
            ["titre", ".fiche-revision-hero h1", ".fiche-revision-hero"],
            ["texte principal", ".fiche-revision-texte", ".fiche-revision-section"],
            ["métadonnées", ".fiche-revision-meta", ".fiche-revision-hero"],
            ["description de section", ".fiche-revision-section-head p", ".fiche-revision-section"],
            ["texte de carte", ".fiche-revision-card p", ".fiche-revision-card"],
            ["formule", ".fiche-revision-formule", ".fiche-revision-formule"]
          ]
        };
        return specs[kind].map(([label, selector, surfaceSelector]) => {
          const element = document.querySelector(selector);
          if (!element) return { label, missing: true };
          let surface = document.querySelector(surfaceSelector) || element;
          let background = null;
          while (surface && !background) {
            const computed = getComputedStyle(surface).backgroundColor;
            const match = computed.match(/rgba?\(([^)]+)\)/i);
            if (match) {
              const parts = match[1].split(",").map((part) => Number.parseFloat(part.trim()));
              if (parts.length < 4 || parts[3] > 0.99) background = parts.slice(0, 3);
            }
            surface = surface.parentElement;
          }
          const foreground = getComputedStyle(element).color;
          const fg = foreground.match(/rgba?\(([^)]+)\)/i);
          const channels = fg ? fg[1].split(",").map((part) => Number.parseFloat(part.trim())).slice(0, 3) : null;
          return { label, foreground, background, channels };
        });
      }, kind);
      for (const value of values) {
        if (value.missing) {
          failures.push(theme + "/" + kind + "/" + value.label + ": élément introuvable");
          continue;
        }
        checks += 1;
        const ratio = value.channels && value.background ? contrast(value.channels, value.background) : 0;
        if (!ratio || ratio < 4.5) {
          failures.push(theme + "/" + kind + "/" + value.label + ": contraste " +
            ratio.toFixed(2) + ":1 (texte " + value.foreground + ", fond " +
            (value.background ? value.background.join(",") : "introuvable") + ")");
        }
      }
    }
  }
} finally {
  await browser.close();
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Contraste des fiches réussi : " + checks +
  " contrôles, thèmes clair/sombre, fiches documentaires/personnelles (minimum 4.5:1).");
