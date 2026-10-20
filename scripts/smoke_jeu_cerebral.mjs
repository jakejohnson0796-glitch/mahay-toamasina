import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const ROOT = process.cwd();
const read = (file) => fs.readFileSync(path.join(ROOT, file), "utf8");
const exists = (file) => fs.existsSync(path.join(ROOT, file));
const homeTemplate = read("app/templates/jeu_cerebral.html");
const sessionTemplate = read("app/templates/jeu_cerebral_session.html");
const resultTemplate = read("app/templates/jeu_cerebral_resultat.html");
const gameScript = read("app/static/js/jeu-cerebral.js");
const rendererScript = read("app/static/js/rendu_ia.js");

const templateContracts = [
  [homeTemplate, /id="form-jeu-cerebral"/, "formulaire de lancement"],
  [homeTemplate, /name="theme" value="calcul"/, "choix de thème"],
  [homeTemplate, /id="jeu-chrono-option"/, "chrono facultatif"],
  [homeTemplate, /id="jeu-reduire-animations"/, "réduction des animations à l'accueil"],
  [sessionTemplate, /id="jeu-pause-toggle"/, "pause"],
  [sessionTemplate, /id="jeu-pause-notice"/, "notice de pause"],
  [sessionTemplate, /id="jeu-chrono-valeur"/, "affichage du chrono"],
  [sessionTemplate, /id="form-reponse-jeu"/, "formulaire de réponse"],
  [sessionTemplate, /id="question-du-jeu" data-rendu/, "question scientifique rendue"],
  [resultTemplate, /jeu-result-reward" role="status"/, "récompense annoncée"],
  [resultTemplate, /class="jeu-answer-list"/, "liste de corrections"],
  [resultTemplate, /id="jeu-reduire-animations-resultat"/, "réduction des animations au résultat"]
];
for (const [source, pattern, label] of templateContracts) {
  assert.match(source, pattern, "Contrat du template manquant : " + label);
}

const baseCssFiles = [
  "app/static/style.css",
  "app/static/ux.css",
  "app/static/refonte.css",
  "app/static/csp-utilities.css",
  "app/static/responsive.css",
  "app/static/responsive-overrides.css",
  "app/static/global-design-system.css",
  "app/static/learning-polish.css"
];
const baseCss = baseCssFiles.map((file) => {
  assert.ok(exists(file), "Feuille CSS absente : " + file);
  return "<style>" + read(file).replace(/<\/style/gi, "<\\/style") + "</style>";
}).join("\n");

function inlineCss(template) {
  const blocks = Array.from(template.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi), (match) => match[1]);
  assert.ok(blocks.length > 0, "Aucun CSS de page trouvé dans le template.");
  return blocks.map((css) => "<style>" + css.replace(/<\/style/gi, "<\\/style") + "</style>").join("\n");
}

function themeCards() {
  const themes = [
    ["aleatoire", "Surprends-moi", "brain-hero.webp"],
    ["logique", "Logique & déduction", "illustrations/logique.svg"],
    ["calcul", "Calcul mental", "illustrations/calcul.svg"],
    ["suites", "Suites & régularités", "illustrations/suites.svg"],
    ["langage", "Mots & analogies", "illustrations/langage.svg"],
    ["observation", "Observation & attention", "illustrations/observation.svg"]
  ];
  return themes.map((theme, index) =>
    '<label class="jeu-theme-option"><input type="radio" name="theme" value="' + theme[0] + '"' +
    (index === 0 ? " checked" : "") + '><span class="jeu-theme-card' +
    (index === 0 ? " jeu-theme-surprise" : "") + '"><span class="jeu-theme-emoji jeu-theme-image">' +
    '<img src="/static/images/jeu-cerebral/' + theme[2] + '" alt="" width="76" height="76" loading="lazy" decoding="async"></span>' +
    "<strong>" + theme[1] + "</strong><span class=\"jeu-theme-description\">Un défi à ton rythme.</span></span></label>"
  ).join("");
}

function homeBody() {
  return '<div class="jeu-cerebral-page">' +
    '<header class="jeu-hero"><div><p class="jeu-eyebrow">MITARIDALA · petite pause futée</p>' +
    '<h1>Un défi à la fois. Tu progresses à ton rythme.</h1>' +
    '<p>Choisis un thème. Chaque essai compte et aucune erreur ne te définit.</p></div>' +
    '<div class="jeu-hero-illustration" aria-hidden="true"><div class="jeu-orbite jeu-orbite-avec-image">' +
    '<img src="/static/images/jeu-cerebral/brain-hero.webp" alt="" width="200" height="165" decoding="async"></div></div></header>' +
    '<section class="jeu-stat-grid" aria-label="Ta progression"><article class="jeu-stat"><span>Sessions terminées</span><strong>2</strong></article>' +
    '<article class="jeu-stat"><span>Moyenne récente</span><strong>80 %</strong></article><article class="jeu-stat"><span>Départ conseillé</span><strong>À ton rythme</strong></article></section>' +
    '<section class="jeu-section" aria-labelledby="jeu-choisir-theme"><div class="jeu-section-head"><div>' +
    '<h2 id="jeu-choisir-theme">Quel terrain de jeu te tente aujourd’hui ?</h2><p>Une session dure quelques minutes.</p></div></div>' +
    '<form method="post" action="/jeu-cerebral/demarrer" id="form-jeu-cerebral">' +
    '<input type="hidden" name="_csrf" value="test-token"><input type="hidden" name="langue" id="jeu-langue" value="fr">' +
    '<fieldset class="jeu-theme-grid" aria-labelledby="jeu-choisir-theme"><legend class="sr-only">Choisis le thème de ton défi</legend>' +
    themeCards() + "</fieldset>" +
    '<fieldset class="jeu-config-options" aria-label="Options facultatives du défi"><legend class="sr-only">Personnalise ton défi</legend>' +
    '<label class="jeu-config-option"><input type="checkbox" name="chronometre" value="1" id="jeu-chrono-option">' +
    '<span><strong>Défi chronométré (facultatif)</strong><small>Le temps écoulé ne retire pas de points.</small></span></label>' +
    '<label class="jeu-config-option"><input type="checkbox" id="jeu-reduire-animations"><span><strong>Réduire les animations</strong>' +
    '<small>Privilégie un affichage plus calme.</small></span></label></fieldset>' +
    '<div class="jeu-lancement"><p>Le niveau est un point de départ, pas une étiquette.</p>' +
    '<button class="jeu-bouton" type="submit">Lancer mon défi <span aria-hidden="true">→</span></button></div></form></section>' +
    '<div class="jeu-note" role="note">Le jeu observe uniquement tes résultats aux exercices pratiqués.</div>' +
    '<section class="jeu-section" aria-labelledby="jeu-historique"><div class="jeu-section-head"><h2 id="jeu-historique">Tes derniers petits défis</h2></div>' +
    '<article class="jeu-history-item">Calcul mental · 80 %</article></section></div>';
}

function sessionBody(options = {}) {
  const chrono = options.chrono === true;
  const id = options.partieId || "responsive-session";
  return '<div class="jeu-session-page" data-partie-id="' + id + '" data-chrono-actif="' + (chrono ? "true" : "false") + '" data-langue="fr">' +
    '<header class="jeu-session-header"><div><p class="jeu-session-breadcrumb"><a href="/jeu-cerebral">Jeu cérébral</a> / Calcul mental</p>' +
    '<h1>🔢 Calcul mental</h1><p class="jeu-session-desc">Lis calmement et découvre la suite pas à pas.</p></div>' +
    '<a class="jeu-bouton-retour" href="/jeu-cerebral">Quitter le défi</a></header>' +
    '<section class="jeu-session-progress" aria-label="Avancement du défi"><div class="jeu-progress-meta"><strong>Question 1 sur 5</strong>' +
    '<span>Une question à la fois · niveau adaptatif</span></div><div class="jeu-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="5" aria-valuenow="0" aria-label="Progression du jeu">' +
    '<div class="jeu-progress-fill" style="width:0%"></div></div></section>' +
    '<section class="jeu-cerebral-toolbar" aria-label="Options du défi"><div class="jeu-chrono-panel" id="jeu-chrono-panel"' +
    (chrono ? "" : " hidden") + '><span class="jeu-chrono-clock" id="jeu-chrono-valeur" aria-label="Temps restant">02:30</span>' +
    '<span class="jeu-chrono-copy"><strong>Objectif de temps</strong><span id="jeu-chrono-message">Aucune pénalité si tu dépasses le temps.</span></span></div>' +
    '<div class="jeu-toolbar-actions"><button type="button" class="jeu-tool-button" id="jeu-pause-toggle" aria-pressed="false">Mettre en pause</button>' +
    '<label class="jeu-tool-check"><input type="checkbox" id="jeu-reduire-animations-session"><span>Réduire les animations</span></label></div>' +
    '<span class="sr-only" id="jeu-pause-status" role="status" aria-live="polite"></span></section>' +
    '<div class="jeu-pause-notice" id="jeu-pause-notice" hidden><strong>Pause en cours 🌿</strong>' +
    '<span>Le défi est en pause. Reprends quand tu es prêt·e ; le chronomètre est suspendu aussi.</span></div>' +
    '<div class="jeu-local-note" role="note"><strong>Mode d’entraînement de secours.</strong> Des questions préparées sont utilisées si l’IA est indisponible.</div>' +
    '<section class="jeu-question-card" aria-labelledby="question-du-jeu"><div class="jeu-question-top">' +
    '<span class="jeu-difficulty">À ton rythme</span><span class="jeu-question-hint">Pas besoin de répondre vite</span>' +
    '<img class="jeu-session-mascotte" src="/static/images/jeu-cerebral/mascotte-pink.webp" alt="" width="70" height="60" loading="lazy" decoding="async"></div>' +
    '<div class="jeu-theme-scene"><img src="/static/images/jeu-cerebral/illustrations/calcul.svg" alt="Illustration du calcul mental" width="74" height="58" loading="lazy" decoding="async">' +
    '<span>Un repère visuel pour le thème · une question à la fois</span></div>' +
    '<div class="jeu-level-steps" aria-label="Progression en trois niveaux"><span class="jeu-level-step" aria-current="step"><i>1</i>Facile</span>' +
    '<span class="jeu-level-step"><i>2</i>Moyen</span><span class="jeu-level-step"><i>3</i>Difficile</span></div>' +
    '<div data-no-translate><h2 class="jeu-question-text" id="question-du-jeu" data-rendu>Combien font \\( 7 \\times 8 + 9 \\) ?</h2></div>' +
    '<form method="post" action="/jeu-cerebral/' + id + '/repondre" id="form-reponse-jeu"><input type="hidden" name="_csrf" value="test-token">' +
    '<input type="hidden" name="index_question" value="0"><fieldset class="jeu-options"><legend class="sr-only">Choisis une réponse</legend>' +
    '<label class="jeu-option"><input type="radio" name="reponse" value="0" required><span data-no-translate data-rendu>64</span></label>' +
    '<label class="jeu-option"><input type="radio" name="reponse" value="1" required><span data-no-translate data-rendu>65</span></label>' +
    '<label class="jeu-option"><input type="radio" name="reponse" value="2" required><span data-no-translate data-rendu>66</span></label>' +
    '<label class="jeu-option"><input type="radio" name="reponse" value="3" required><span data-no-translate data-rendu>67</span></label>' +
    '</fieldset><div class="jeu-submit-row"><p class="jeu-submit-note">Quelle que soit ta réponse, elle aide à choisir la suite.</p>' +
    '<button class="jeu-bouton" type="submit" id="envoyer-reponse">Valider ma réponse</button></div></form></section>' +
    '<div class="jeu-render-contract" data-rendu>Exemple : \\( \\frac{12}{18} = \\frac{2}{3} \\).</div></div>';
}

function resultBody() {
  return '<div class="jeu-result-page" data-partie-id="result-responsive" data-session-terminee="true">' +
    '<header class="jeu-result-hero"><div><p class="jeu-result-eyebrow">Jeu cérébral · ton bilan</p>' +
    '<h1>Chaque essai compte</h1><p>Tu as avancé à ton rythme. Voici ce que tu peux retenir pour la prochaine fois.</p>' +
    '<div class="jeu-result-actions"><a class="jeu-btn jeu-btn-primary" href="/jeu-cerebral">Choisir un autre thème</a>' +
    '<a class="jeu-btn" href="/mes-revisions">Voir mes révisions</a></div></div>' +
    '<div class="jeu-result-score" aria-label="Score de la session"><img src="/static/images/jeu-cerebral/trophy.webp" alt="" width="64" height="38" loading="lazy" decoding="async">' +
    '<strong>80 %</strong><span>4/5 bonnes réponses</span><div class="jeu-result-reward" role="status" aria-label="Récompense de la session">' +
    '<span class="jeu-reward-stars" aria-hidden="true">✦ ✦ ✦</span><strong>Éclat brillant</strong><span>Trois étoiles de progression</span></div></div></header>' +
    '<div class="jeu-result-settings"><label><input type="checkbox" id="jeu-reduire-animations-resultat"><span>Réduire les animations</span></label></div>' +
    '<section class="jeu-result-section" aria-labelledby="jeu-conseils-title"><h2 id="jeu-conseils-title">Quelques pistes pour la suite</h2>' +
    '<p class="jeu-result-muted">Basées sur tes réponses à cette session.</p><div class="jeu-tip-grid">' +
    '<article class="jeu-tip"><h3>Ce que tu as bien repéré</h3><div class="jeu-chip-list"><span class="jeu-chip">Pourcentages simples</span></div></article>' +
    '<article class="jeu-tip"><h3>Des idées à renforcer</h3><div class="jeu-chip-list"><span class="jeu-chip">Proportionnalité</span></div></article></div>' +
    '<div class="jeu-advice" data-no-translate><strong>Une idée pour la prochaine fois</strong><br>Refais un exercice court sans te presser.</div></section>' +
    '<section class="jeu-result-section" aria-labelledby="jeu-reponses-title"><h2 id="jeu-reponses-title">Revenons doucement sur les questions</h2>' +
    '<p class="jeu-result-muted">Les explications servent à comprendre le raisonnement.</p><div class="jeu-answer-list">' +
    '<article class="jeu-answer"><div class="jeu-answer-head"><strong>1. <span data-no-translate data-rendu>Combien font \\(7 \\times 8 + 9\\) ?</span></strong><span class="jeu-answer-state">Juste</span></div>' +
    '<p class="jeu-answer-label">Ta réponse :</p><p data-no-translate data-rendu>65</p><p class="jeu-answer-explain" data-no-translate data-rendu>On calcule \\(7 \\times 8 = 56\\), puis \\(56 + 9 = 65\\).</p></article>' +
    '<article class="jeu-answer"><div class="jeu-answer-head"><strong>2. <span data-no-translate data-rendu>Quelle est la racine carrée approchée de \\(1000\\) ?</span></strong><span class="jeu-answer-state">À retenir</span></div>' +
    '<p class="jeu-answer-label">Ta réponse :</p><p data-no-translate data-rendu>30</p><p class="jeu-answer-label">Bonne réponse :</p><p data-no-translate data-rendu>\\(\\sqrt{1000}\\approx31,6\\)</p>' +
    '<p class="jeu-answer-explain" data-no-translate data-rendu>La valeur est proche de \\(31,6\\).</p></article></div></section></div>';
}

function rendererBody() {
  return '<main id="renderer-tests"><h1>Contrat de rendu scientifique</h1>' +
    '<div id="rendu-math"></div><div id="rendu-physique"></div><div id="rendu-chimie"></div>' +
    '<div id="rendu-comptabilite"></div><div id="rendu-code"></div><div id="rendu-nonfiable"></div></main>';
}

function pageHtml(type, mode, options = {}) {
  const template = type === "home" ? homeTemplate : type === "session" ? sessionTemplate : resultTemplate;
  const styles = type === "renderer" ? "" : inlineCss(template);
  const body = type === "home" ? homeBody() : type === "session" ? sessionBody(options) : type === "result" ? resultBody() : rendererBody();
  const katexCss = type === "renderer" ? '<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">' : "";
  let scripts = '<script defer src="/static/js/jeu-cerebral.js?v=smoke"></script>';
  if (type === "renderer") {
    scripts = [
      '<script src="/static/vendor/katex/katex.min.js"></script>',
      '<script src="/static/vendor/katex/contrib/mhchem.min.js"></script>',
      '<script src="/static/vendor/marked/marked.min.js"></script>',
      '<script src="/static/vendor/dompurify/purify.min.js"></script>',
      '<script src="/static/vendor/highlightjs/highlight.min.js"></script>',
      '<script src="/static/js/rendu_ia.js"></script>'
    ].join("");
  }
  return '<!doctype html><html lang="fr" data-theme="' + mode + '"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + katexCss +
    baseCss + styles + '</head><body><main class="main-clair main-clair-pleine-largeur"><div class="contenu-clair">' +
    body + '</div></main>' + scripts + '</body></html>';
}

const browser = await chromium.launch({ headless: true });
const failures = [];
const widths = [320, 360, 390, 430, 768, 1024, 1440];
let responsiveStates = 0;
try {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    if (location.hostname === "jeu.test") {
      window.__jeuTestNow = 1800000000000;
      Date.now = () => window.__jeuTestNow;
    }
  });
  const page = await context.newPage();
  await page.route("http://jeu.test/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/static/")) {
      const relative = path.join("app", url.pathname.slice(1));
      const absolute = path.resolve(ROOT, relative);
      if (!absolute.startsWith(path.resolve(ROOT, "app/static") + path.sep) || !exists(relative)) {
        await route.fulfill({ status: 404, body: "Not found" });
        return;
      }
      const extension = path.extname(absolute).toLowerCase();
      const mime = extension === ".webp" ? "image/webp"
        : extension === ".svg" ? "image/svg+xml"
        : extension === ".css" ? "text/css"
        : extension === ".js" ? "text/javascript"
        : extension === ".woff2" ? "font/woff2"
        : extension === ".woff" ? "font/woff"
        : extension === ".ttf" ? "font/ttf"
        : "application/octet-stream";
      await route.fulfill({ status: 200, contentType: mime, body: fs.readFileSync(absolute) });
      return;
    }
    const mode = url.searchParams.get("mode") === "sombre" ? "sombre" : "clair";
    const type = url.pathname === "/session" ? "session"
      : url.pathname === "/result" ? "result"
      : url.pathname === "/renderer" ? "renderer"
      : "home";
    const options = {
      chrono: url.searchParams.get("chrono") === "1",
      partieId: url.searchParams.get("partie") || "responsive-session"
    };
    await route.fulfill({ status: 200, contentType: "text/html", body: pageHtml(type, mode, options) });
  });

  // La génération IA et le backend sont couverts par les tests applicatifs ;
  // ce smoke test exerce le vrai JS front-end et les CSS du dépôt dans Chromium.
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of widths) {
    for (const mode of ["clair", "sombre"]) {
      for (const type of ["home", "session", "result"]) {
        responsiveStates += 1;
        await page.setViewportSize({ width, height: width <= 430 ? 820 : 960 });
        await page.goto("http://jeu.test/" + type + "?mode=" + mode + "&uid=" + responsiveStates, { waitUntil: "load" });
        await page.evaluate(() => {
          document.querySelectorAll('img[loading="lazy"]').forEach((img) => { img.loading = "eager"; });
        });
        await page.waitForFunction(() => Array.from(document.images).every((img) => img.complete && img.naturalWidth > 0), null, { timeout: 8000 });
        const layout = await page.evaluate(() => ({
          viewport: window.innerWidth,
          doc: document.documentElement.scrollWidth,
          body: document.body.scrollWidth,
          root: (() => {
            const el = document.querySelector(".jeu-cerebral-page, .jeu-session-page, .jeu-result-page");
            const r = el.getBoundingClientRect();
            return { x: r.x, right: r.right, width: r.width };
          })(),
          loadedImages: Array.from(document.images).map((img) => ({ src: img.getAttribute("src"), width: img.naturalWidth, height: img.naturalHeight }))
        }));
        if (layout.doc > width + 1 || layout.body > width + 1) {
          failures.push("Débordement horizontal " + type + "/" + mode + "/" + width + "px : " + JSON.stringify(layout));
        }
        if (layout.root.x < -1 || layout.root.right > width + 1) {
          failures.push("Conteneur du jeu hors écran " + type + "/" + mode + "/" + width + "px : " + JSON.stringify(layout.root));
        }
        if (layout.loadedImages.some((img) => img.width < 1 || img.height < 1)) {
          failures.push("Illustration non chargée " + type + "/" + mode + "/" + width + "px");
        }
        if (type === "home") {
          assert.equal(await page.locator('input[name="theme"]').count(), 6, "Les six choix de thèmes doivent apparaître.");
          await page.locator('input[name="theme"][value="calcul"]').check();
          assert.equal(await page.locator('input[name="theme"][value="calcul"]').isChecked(), true);
          await page.locator("#jeu-chrono-option").check();
          assert.equal(await page.locator("#jeu-chrono-option").isChecked(), true);
          const card = await page.locator('input[name="theme"][value="calcul"] + .jeu-theme-card').boundingBox();
          if (!card || card.width < Math.min(width - 28, 220)) failures.push("Carte de thème trop étroite à " + width + "px.");
        }
        if (type === "session") {
          const pause = page.locator("#jeu-pause-toggle");
          await pause.click();
          assert.equal(await pause.getAttribute("aria-pressed"), "true");
          assert.equal(await page.locator("#jeu-pause-notice").isVisible(), true);
          assert.equal(await page.locator("#jeu-pause-status").innerText(), "Défi en pause.");
          assert.equal(await page.locator("#form-reponse-jeu fieldset").isDisabled(), true);
          assert.equal(await page.locator("#envoyer-reponse").isDisabled(), true);
          await pause.click();
          assert.equal(await pause.getAttribute("aria-pressed"), "false");
          assert.equal(await page.locator("#jeu-pause-notice").isHidden(), true);
          assert.equal(await page.locator("#form-reponse-jeu fieldset").isDisabled(), false);
        }
        if (type === "result") {
          assert.equal(await page.locator(".jeu-result-reward[role=status]").count(), 1);
          assert.equal(await page.locator(".jeu-answer").count(), 2);
          assert.equal(await page.locator(".jeu-result-actions a").count(), 2);
        }
      }
    }
  }

  // Le réglage est partagé entre l'accueil, la session et l'écran de bilan.
  await page.setViewportSize({ width: 390, height: 820 });
  await page.goto("http://jeu.test/home?mode=clair&uid=preferences", { waitUntil: "load" });
  await page.locator("#jeu-reduire-animations").check();
  assert.equal(await page.locator(".jeu-cerebral-page").evaluate((e) => e.classList.contains("jeu-reduit-mouvement")), true);
  assert.equal(await page.evaluate(() => localStorage.getItem("mitaridala-jeu-reduire-animations")), "1");
  await page.goto("http://jeu.test/session?mode=clair&partie=preference-session", { waitUntil: "load" });
  assert.equal(await page.locator("#jeu-reduire-animations-session").isChecked(), true);
  assert.equal(await page.locator(".jeu-session-page").evaluate((e) => e.classList.contains("jeu-reduit-mouvement")), true);
  await page.locator("#jeu-reduire-animations-session").uncheck();
  await page.goto("http://jeu.test/result?mode=clair", { waitUntil: "load" });
  assert.equal(await page.locator("#jeu-reduire-animations-resultat").isChecked(), false);
  assert.equal(await page.locator(".jeu-result-page").evaluate((e) => e.classList.contains("jeu-reduit-mouvement")), false);

  // Le chrono doit se suspendre avec la pause, survivre à un rechargement,
  // reprendre sans consommer le temps de pause et ne jamais bloquer les réponses.
  await page.goto("http://jeu.test/session?chrono=1&mode=clair&partie=pause-clock", { waitUntil: "load" });
  assert.equal(await page.locator("#jeu-chrono-valeur").innerText(), "02:30");
  const key = "mitaridala:jeu:pause-clock:";
  const before = await page.evaluate((prefix) => Number(sessionStorage.getItem(prefix + "deadline")), key);
  assert.ok(before > 0, "Le chrono doit enregistrer une échéance de session.");
  await page.locator("#jeu-pause-toggle").click();
  const pauseAt = await page.evaluate((prefix) => Number(sessionStorage.getItem(prefix + "pause-at")), key);
  assert.ok(pauseAt > 0, "L'heure de pause doit être conservée.");
  await page.reload({ waitUntil: "load" });
  assert.equal(await page.locator("#jeu-pause-toggle").getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator("#form-reponse-jeu fieldset").isDisabled(), true);
  await page.evaluate(() => { window.__jeuTestNow += 12000; });
  await page.locator("#jeu-pause-toggle").click();
  const after = await page.evaluate((prefix) => Number(sessionStorage.getItem(prefix + "deadline")), key);
  assert.equal(after - before, 12000, "Le temps passé en pause ne doit pas consommer le chrono.");
  assert.equal(await page.locator("#jeu-chrono-valeur").innerText(), "02:30");
  assert.equal(await page.locator("#form-reponse-jeu fieldset").isDisabled(), false);
  await page.evaluate(() => { window.__jeuTestNow += 3000; });
  await page.waitForFunction(() => document.querySelector("#jeu-chrono-valeur").textContent === "02:27", null, { timeout: 2500 });
  const activeBeforeExpiry = await page.locator("#form-reponse-jeu fieldset").isDisabled();
  assert.equal(activeBeforeExpiry, false, "Les réponses doivent rester possibles avec le chrono arrivé à son terme.");
  await page.evaluate(() => {
    const root = document.querySelector(".jeu-session-page");
    const deadline = Number(sessionStorage.getItem("mitaridala:jeu:pause-clock:deadline"));
    window.__jeuTestNow = deadline + 1000;
  });
  await page.waitForFunction(() => document.querySelector("#jeu-chrono-valeur").textContent === "00:00", null, { timeout: 2500 });
  assert.match(await page.locator("#jeu-chrono-message").innerText(), /Temps cible écoulé/);
  assert.equal(await page.locator("#form-reponse-jeu fieldset").isDisabled(), false);

  // Contrôles de rendu réellement produits dans Chromium avec les bibliothèques
  // locales verrouillées et vérifiées par scripts/vendor_frontend_dependencies.py.
  await page.setViewportSize({ width: 390, height: 820 });
  await page.goto("http://jeu.test/renderer", { waitUntil: "load" });
  assert.equal(await page.evaluate(() => typeof window.rendreReponseIA), "function");
  const fence = String.fromCharCode(96).repeat(3);
  const cases = [
    ["rendu-math", "Fraction : \\( \\frac{12}{18} = \\frac{2}{3} \\) ; racine : \\( \\sqrt{1000} \\approx 31{,}6 \\)."],
    ["rendu-physique", "Physique : \\( \\vec{F}=m\\vec{a} \\), unité : \\( \\mathrm{m/s^2} \\)."],
    ["rendu-chimie", "Réaction : \\( \\ce{2H2 + O2 -> 2H2O} \\)."],
    ["rendu-comptabilite", "Montant : 12 000 Ar. Débit = 12 000 Ar ; crédit = 12 000 Ar."],
    ["rendu-code", fence + "python\nprint('Ar = 12 000')\n" + fence],
    ["rendu-nonfiable", "Texte utilisateur : <img src=x onerror=alert(1)>"]
  ];
  for (const [id, source] of cases) {
    await page.evaluate(({ id, source }) => window.rendreReponseIA(source, document.getElementById(id)), { id, source });
  }
  const rendererState = await page.evaluate(() => ({
    math: document.querySelectorAll("#rendu-math .katex .katex-html").length,
    physics: document.querySelectorAll("#rendu-physique .katex .katex-html").length,
    chemistry: document.querySelectorAll("#rendu-chimie .katex .katex-html").length,
    accounting: document.querySelector("#rendu-comptabilite").textContent,
    code: document.querySelector("#rendu-code pre code")?.textContent || "",
    injected: document.querySelector("#rendu-nonfiable [onerror]") !== null
  }));
  assert.ok(rendererState.math >= 2, "La fraction et la racine doivent être rendues par KaTeX : " + JSON.stringify(rendererState));
  assert.ok(rendererState.physics >= 1, "La formule de physique doit être rendue par KaTeX.");
  assert.ok(rendererState.chemistry >= 1, "La réaction chimique doit être rendue par mhchem.");
  assert.match(rendererState.accounting, /12 000 Ar/);
  assert.match(rendererState.code, /print\('Ar = 12 000'\)/);
  assert.equal(rendererState.injected, false, "Le rendu doit neutraliser les attributs HTML actifs.");

  console.log(JSON.stringify({
    responsiveStates,
    widths,
    checks: [
      "accueil/session/résultat sur sept largeurs et deux thèmes visuels",
      "chargement de toutes les illustrations visibles et différées",
      "sélection d'un thème et activation du chrono facultatif",
      "pause/reprise, verrouillage des réponses et annonce accessible",
      "préférence de réduction des animations conservée entre les écrans",
      "chrono suspendu pendant la pause, même après rechargement",
      "chrono arrivé à zéro sans bloquer les réponses",
      "rendu navigateur de mathématiques, physique, chimie, comptabilité et code",
      "neutralisation du HTML non fiable par le renderer"
    ],
    rendererState
  }, null, 2));
  if (failures.length) {
    console.error(JSON.stringify({ failures }, null, 2));
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
