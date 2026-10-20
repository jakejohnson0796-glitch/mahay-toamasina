import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const root = process.cwd();
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const base = read("app/templates/base.html");
const navMatch = base.match(/<nav\b[^>]*class="navigation-mobile-fixe"[^>]*>[\s\S]*?<\/nav>/i);
if (!navMatch) throw new Error("Navigation mobile introuvable dans base.html.");
const navSource = navMatch[0];

const openingAnchors = (navSource.match(/<a\b/gi) || []).length;
const closingAnchors = (navSource.match(/<\/a\s*>/gi) || []).length;
if (openingAnchors !== 6 || closingAnchors !== 6) {
  throw new Error("La navigation doit avoir 6 liens correctement fermés (ouverture=" + openingAnchors + ", fermeture=" + closingAnchors + ").");
}
let anchorOpen = false;
for (const token of navSource.match(/<\/?a\b[^>]*>/gi) || []) {
  if (/^<\/a/i.test(token)) {
    if (!anchorOpen) throw new Error("Balise </a> surnuméraire dans la navigation mobile.");
    anchorOpen = false;
  } else {
    if (anchorOpen) throw new Error("Deux liens <a> imbriqués : le HTML de la navigation est invalide.");
    anchorOpen = true;
  }
}
if (anchorOpen) throw new Error("Un lien mobile ne possède pas de balise de fermeture.");

const expectedHrefs = ["/dashboard", "/documents", "/quiz", "/jeu-cerebral", "/cercles", "/securite"];
for (const href of expectedHrefs) {
  if (!navSource.includes('href="' + href + '"')) throw new Error("Destination mobile manquante : " + href);
}

const navHtml = navSource
  .replace(/\{\{\s*icone\([^}]*\)\s*\}\}/g, '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20"></svg>')
  .replace(/\{\{[\s\S]*?\}\}/g, "")
  .replace(/\{%[\s\S]*?%\}/g, "");

const cssPaths = [...base.matchAll(/href="\/static\/([^"?]+\.css)(?:\?[^"]*)?"/g)]
  .map((match) => "app/static/" + match[1])
  .filter((value, index, all) => all.indexOf(value) === index);
if (!cssPaths.includes("app/static/responsive-universal.css")) {
  throw new Error("responsive-universal.css doit être chargé depuis base.html.");
}
const styles = cssPaths.map((file) => {
  const css = read(file).replace(/<\/style/gi, "<\\/style");
  return "<style data-source=\"" + path.basename(file) + "\">" + css + "</style>";
}).join("\n");

function card(title, description) {
  return '<article class="doc-carte carte-claire"><h2 class="doc-titre">' + title +
    '</h2><p class="doc-description">' + description +
    '</p><div class="doc-actions"><a class="doc-bouton" href="/documents">Ouvrir le document</a><button type="button">Continuer</button></div></article>';
}

function scenarioContent(name) {
  const longText = "Vérification responsive MITARIDALA — apprentissage, documents, universités, notions et progression. ".repeat(3);
  if (name === "dashboard") {
    return '<section class="tb-hero"><p class="eyebrow">TON ESPACE</p><h1 class="tb-titre">Bonjour et bienvenue sur MITARIDALA</h1><p class="tb-sous-titre">' + longText + '</p><div class="cta-groupe"><a class="bouton bouton-primaire">Reprendre</a><a class="bouton">Voir mes cours</a></div></section>' +
      '<section class="tb-grille-stats">' + card("Progression", longText) + card("Révisions", longText) + card("Documents", longText) + card("Cercles", longText) + '</section><section class="tb-panneau"><h2>À reprendre</h2>' + card("Algèbre", longText) + '</section>';
  }
  if (name === "documents") {
    return '<h1>Mes documents</h1><form class="filtres"><input aria-label="Rechercher" placeholder="Rechercher un titre très long"><select aria-label="Matière"><option>Mathématiques</option></select><button class="bouton">Filtrer les documents</button></form><section class="doc-grille">' +
      card("Guide très long sur les mathématiques et les méthodes de résolution", longText) +
      card("Physique et chimie — cours complet", longText) +
      card("Informatique et programmation", longText) +
      card("Comptabilité générale", longText) +
      '</section><div class="table-manifeste-conteneur"><table class="table-manifeste"><thead><tr><th>Référence</th><th>Titre du document</th><th>Matière</th><th>Année</th><th>Type</th></tr></thead><tbody><tr><td>DOC-0001</td><td>' + longText + '</td><td>Mathématiques</td><td>2026</td><td>PDF</td></tr></tbody></table></div>';
  }
  if (name === "quiz") {
    return '<section class="quiz-carte-generer"><h1>Quiz IA — entraînement personnalisé</h1><p>' + longText + '</p><div class="quiz-grille">' + card("Exercices guidés", longText) + card("Mode examen", longText) + '</div><section class="carte-claire"><h2>Question 03</h2><p>Quel est le résultat de la simplification de la fraction 12 sur 18 ?</p><div class="katex-display">\\\\frac{12}{18}=\\\\frac{2}{3} \\quad 12345678901234567890</div><label><input type="radio" name="answer"> A. 2/3</label><label><input type="radio" name="answer"> B. 3/4</label><button class="bouton bouton-primaire">Valider la réponse</button></section></section>';
  }
  if (name === "circle") {
    return '<p class="eyebrow">Cercles d’étude</p><section class="entete-cercle"><div class="entete-cercle-identite"><div class="entete-cercle-infos"><h1 class="entete-cercle-titre">Groupe de révision — gestion, finance et comptabilité générale</h1><p>' + longText + '</p></div></div><div class="entete-cercle-actions"><button aria-label="Rechercher">⌕</button><button aria-label="Membres">♙</button></div></section><section class="disposition-chat"><div class="colonne-conversation"><div id="fenetre-chat" class="fenetre-chat"><div class="message"><div class="message-corps"><div class="message-contenu">' + longText + '</div></div></div></div><div class="barre-composition"><textarea aria-label="Message" placeholder="Écrire un message…" rows="2"></textarea><button aria-label="Envoyer">Envoyer</button></div></div></section>';
  }
  if (name === "class") {
    return '<h1>Classe virtuelle</h1><section class="classe-salle-panel"><h2>Salle de cours — Mathématiques appliquées</h2><p>' + longText + '</p><div class="classe-grid">' + card("Participant 1", longText) + card("Participant 2", longText) + card("Tableau blanc", longText) + '</div><div class="classe-salle-controls"><button>Partager</button><button>Quitter la classe</button></div></section>';
  }
  if (name === "admin") {
    return '<h1>Administration</h1><section class="ops-stat-grid">' + card("Utilisateurs", longText) + card("Documents en attente", longText) + '</section><div class="ops-table-wrapper"><table class="tableau-admin"><thead><tr><th>Utilisateur</th><th>Adresse e-mail</th><th>Filière académique</th><th>État</th><th>Actions</th></tr></thead><tbody><tr><td>Étudiant</td><td>adresse-electronique-longue@example.test</td><td>Mathématiques et informatique</td><td>Actif</td><td><button>Modifier les paramètres</button></td></tr></tbody></table></div>';
  }
  return '<section class="auth-card"><h1>Créer mon compte MITARIDALA</h1><p>' + longText + '</p><form><label for="email">Adresse e-mail</label><input id="email" type="email" autocomplete="email"><label for="password">Mot de passe</label><input id="password" type="password" autocomplete="new-password"><button class="bouton bouton-primaire" type="submit">Créer mon compte</button></form></section>';
}

function fixture(name, theme) {
  return '<!doctype html><html lang="fr" data-theme="' + theme + '"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + styles +
    '</head><body><div class="app-mise-en-page"><aside class="tb-sidebar"><a class="tb-sidebar-logo">MITARIDALA</a><nav class="tb-sidebar-nav"><a class="tb-sidebar-lien">Tableau de bord</a><a class="tb-sidebar-lien">Documents</a><a class="tb-sidebar-lien">Quiz IA</a><a class="tb-sidebar-lien">Mes cercles</a></nav></aside>' +
    navHtml + '<div class="app-page"><header class="mobile-entete-app"><span class="mobile-entete-app-marque">MITARIDALA</span><span class="mobile-entete-app-sous-marque">Madagascar</span><a class="mobile-entete-app-avatar" href="/securite" aria-label="Profil">M</a></header>' +
    '<main class="main-clair main-clair-pleine-largeur" data-test-page="' + name + '"><div class="contenu-clair">' + scenarioContent(name) +
    '</div></main><footer class="pied">MITARIDALA — Aide et contact</footer></div></div></body></html>';
}

const widths = [265, 320, 360, 390, 430, 540, 768, 820, 1024, 1280, 1440];
const scenarios = ["dashboard", "documents", "quiz", "circle", "class", "admin", "auth"];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 390, height: 840 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true
});
const failures = [];
let checks = 0;
try {
  for (const scenario of scenarios) {
    await page.setContent(fixture(scenario, "clair"), { waitUntil: "domcontentloaded" });
    for (const width of widths) {
      await page.setViewportSize({ width: width, height: width < 600 ? 820 : 940 });
      const result = await page.evaluate(() => {
        const nav = document.querySelector(".navigation-mobile-fixe");
        const anchors = Array.from(nav.querySelectorAll("a"));
        const labels = anchors.map((a) => {
          const spans = Array.from(a.querySelectorAll(":scope > span"));
          return spans.length ? spans[spans.length - 1].textContent.trim() : "";
        });
        const r = (element) => {
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          return { x: rect.x, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
        };
        const main = document.querySelector("main");
        const appPage = document.querySelector(".app-page");
        return {
          viewport: window.innerWidth,
          rootWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
          mainWidth: main ? main.scrollWidth : 0,
          mainClientWidth: main ? main.clientWidth : 0,
          mainRect: r(main),
          appPageWidth: appPage ? appPage.scrollWidth : 0,
          appPageClientWidth: appPage ? appPage.clientWidth : 0,
          navDisplay: getComputedStyle(nav).display,
          navRect: r(nav),
          anchors: anchors.map(r),
          labels,
          anchorCount: anchors.length
        };
      });
      checks += 1;
      if (result.rootWidth > width + 1 || result.bodyWidth > width + 1) {
        failures.push(scenario + " @ " + width + "px: débordement document (root=" + result.rootWidth + ", body=" + result.bodyWidth + ")");
      }
      if (result.mainRect && (result.mainRect.x < -1 || result.mainRect.right > width + 1)) {
        failures.push(scenario + " @ " + width + "px: contenu principal hors écran " + JSON.stringify(result.mainRect));
      }
      if (result.mainWidth > result.mainClientWidth + 3) {
        failures.push(scenario + " @ " + width + "px: contenu principal plus large que son conteneur (" + result.mainWidth + "/" + result.mainClientWidth + ")");
      }
      if (result.anchorCount !== 6 || result.labels.join("|") !== "Accueil|Docs|Quiz|Jeu|Cercles|Profil") {
        failures.push(scenario + " @ " + width + "px: onglets mobiles manquants/désordonnés " + JSON.stringify(result.labels));
      }
      if (width <= 768) {
        if (result.navDisplay === "none" || !result.navRect || result.navRect.width > width + 1 || result.navRect.right > width + 1) {
          failures.push(scenario + " @ " + width + "px: barre mobile masquée ou hors écran");
        }
        for (let i = 0; i < result.anchors.length; i += 1) {
          const item = result.anchors[i];
          if (!item || item.x < -1 || item.right > width + 1 || item.height < 44) {
            failures.push(scenario + " @ " + width + "px: zone tactile incorrecte pour l'onglet " + result.labels[i] + " " + JSON.stringify(item));
            break;
          }
          if (i > 0 && item.x < result.anchors[i - 1].right - 1) {
            failures.push(scenario + " @ " + width + "px: onglets qui se chevauchent horizontalement");
            break;
          }
        }
      } else if (result.navDisplay !== "none") {
        failures.push(scenario + " @ " + width + "px: la navigation mobile apparaît sur grand écran");
      }
    }
  }

  await page.setContent(fixture("dashboard", "sombre"), { waitUntil: "domcontentloaded" });
  for (const width of [265, 360, 768, 1024, 1440]) {
    await page.setViewportSize({ width: width, height: width < 600 ? 820 : 940 });
    const state = await page.evaluate(() => ({
      width: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      navBackground: getComputedStyle(document.querySelector(".navigation-mobile-fixe")).backgroundColor
    }));
    checks += 1;
    if (state.documentWidth > width + 1) failures.push("Thème sombre @ " + width + "px: débordement document");
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error("Smoke responsive global : " + failures.length + " anomalie(s) sur " + checks + " états.");
  for (const failure of failures.slice(0, 30)) console.error(" - " + failure);
  process.exit(1);
}
console.log("Smoke responsive global OK : " + checks + " états (7 familles de pages, 11 largeurs de 265 à 1440 px, thèmes clair/sombre, 6 onglets mobiles sans chevauchement).");
