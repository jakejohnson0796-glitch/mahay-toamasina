import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { marked } from 'marked';
import katex from 'katex';
const mhchemSource = fs.readFileSync('node_modules/katex/dist/contrib/mhchem.min.js', 'utf8');
import createDOMPurify from 'dompurify';

const source = fs.readFileSync('app/static/js/rendu_ia.js', 'utf8');
const aiLearningSource = fs.readFileSync('app/static/js/ai-learning.js', 'utf8');
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  runScripts: 'outside-only',
});
const { window } = dom;
globalThis.document = window.document;
globalThis.NodeFilter = window.NodeFilter;
window.marked = marked;
const purifyInstance = createDOMPurify(window);
window.DOMPurify = purifyInstance;
window.katex = katex;
const formulesRendues = [];
const renduKatexOriginal = window.katex.render.bind(window.katex);
window.katex.render = function (expression, target, options) {
  formulesRendues.push(String(expression));
  return renduKatexOriginal(expression, target, options);
};
window.eval(mhchemSource);
window.hljs = null;
const context = {
  window,
  document: window.document,
  NodeFilter: window.NodeFilter,
  console,
  setTimeout,
  clearTimeout,
};
vm.runInNewContext(source, context, { filename: 'rendu_ia.js' });

const host = window.document.createElement('div');
window.document.body.appendChild(host);
const sample = String.raw`Cinétique :
[[DISPLAY]]\lambda A + \beta B = \gamma C + \delta D[[/DISPLAY]]

Et : [[MATH]]\det(A)=ad-bc[[/MATH]].`;
window.rendreReponseIA(sample, host);

const raw = host.textContent || '';
if (raw.includes('[[DISPLAY]]') || raw.includes('[[MATH]]')) {
  throw new Error('Transport markers remain visible');
}
if (host.querySelectorAll('.katex').length < 2) {
  throw new Error('Expected KaTeX nodes were not generated');
}

const fractionHost = window.document.createElement('div');
window.document.body.appendChild(fractionHost);
const indiceFormules = formulesRendues.length;
window.rendreReponseIA(
  String.raw`Considérons \(\frac{123456000}{789000}\), puis \(\frac{12}{18}\).`,
  fractionHost
);
const formulesFractions = formulesRendues.slice(indiceFormules);
if (!formulesFractions.some((formule) => formule.includes(String.raw`\dfrac{123456000}{789000}`))) {
  throw new Error('Long inline fractions should use displaystyle to remain readable');
}
if (formulesFractions.some((formule) => formule.includes(String.raw`\dfrac{12}{18}`))) {
  throw new Error('Short inline fractions should remain compact');
}
if (fractionHost.querySelectorAll('.katex').length !== 2) {
  throw new Error('Both fractions should be rendered as KaTeX nodes');
}
const visibleClone = host.cloneNode(true);
visibleClone.querySelectorAll('.katex').forEach((node) => node.remove());
const visibleText = visibleClone.textContent || '';
if (visibleText.includes('\\lambda') || visibleText.includes('\\det')) {
  throw new Error('Raw LaTeX command remains outside rendered KaTeX nodes');
}

// Régression du rendu du texte IA historique : paragraphes séparés par les deux
// caractères \n, Markdown et entités d'espacement issues de certains transports.
const legacyMarkdownHost = window.document.createElement('div');
window.document.body.appendChild(legacyMarkdownHost);
const legacyMarkdownSource =
  "La réduction d’une fraction consiste à exprimer la même valeur numérique avec des nombres plus petits, en éliminant les facteurs communs au numérateur et au dénominateur.\\n\\n" +
  "**Pourquoi le PGCD ?**\\n" +
  "Le plus grand commun diviseur (PGCD) est le plus grand entier qui divise simultanément le numérateur et le dénominateur.\\n\\n" +
  "**Méthode pas à pas**\\n" +
  "1. **Calcul du PGCD** : décomposition en facteurs premiers ou algorithme d’Euclide.\\n" +
  "2. **Division** : diviser les deux termes par le PGCD trouvé.\\n" +
  "3. **Vérification** : contrôler que le PGCD vaut 1.\\n\\n" +
  "**Conseils pour éviter les erreurs**\\n" +
  "- Ne pas confondre le PPCM avec le PGCD.\\n" +
  "- Vérifier le plus grand commun diviseur.\\n" +
  "- Refaire le calcul du PGCD.\\n\\n" +
  "En suivant ces étapes, la réduction devient fiable et rapide. &#x20;";
window.rendreReponseIA(legacyMarkdownSource, legacyMarkdownHost);
if ((legacyMarkdownHost.textContent || '').includes('\\n')) {
  throw new Error('Escaped newline sequences remained visible in legacy AI Markdown');
}
if (legacyMarkdownHost.querySelectorAll('p').length < 4 ||
    legacyMarkdownHost.querySelectorAll('strong').length < 4 ||
    legacyMarkdownHost.querySelectorAll('ol li').length !== 3 ||
    legacyMarkdownHost.querySelectorAll('ul li').length !== 3) {
  throw new Error('Legacy AI paragraphs, bold labels or lists were not rendered as Markdown');
}
if ((legacyMarkdownHost.textContent || '').includes('&#x20;')) {
  throw new Error('Whitespace HTML entity remained visible in rendered AI content');
}

// La normalisation des retours à la ligne ne doit pas convertir \\nabla en newline.
const nakedNablaHost = window.document.createElement('div');
window.document.body.appendChild(nakedNablaHost);
window.rendreReponseIA("Notation : \\nabla f", nakedNablaHost);
if (!nakedNablaHost.querySelector('.katex, .gm-latex-fallback')) {
  throw new Error('The LaTeX command \\\\nabla was incorrectly decoded as a newline');
}

// Régression quiz : les anciens délimiteurs $...$ et $...$ doivent être
// convertis avant le passage Markdown.
const dollarHost = window.document.createElement('div');
window.document.body.appendChild(dollarHost);
const dollarSample = 'Quel est le rang ? $A=\\begin{pmatrix}1 & 0 \\\\ 0 & 1\\end{pmatrix}$ et $$\\det(A)=1$$';
window.rendreReponseIA(dollarSample, dollarHost);
if (dollarHost.querySelectorAll('.katex').length < 2) {
  throw new Error('Legacy dollar delimiters were not rendered');
}
if ((dollarHost.textContent || '').includes('$')) {
  throw new Error('Dollar math delimiters remain visible');
}

// Régression exacte du quiz : un "$$" orphelin avant une formule $...$
// ne doit pas rester affiché à côté de la question.
const quizLikeHost = window.document.createElement('div');
window.document.body.appendChild(quizLikeHost);
const quizLikeSource = [
  "Quel est le rang de l'endomorphisme $$ dont la matrice dans la base canonique est",
  "$A=\\begin{pmatrix}-8 & -4\\\\5 & -3\\\\1 & 0\\end{pmatrix}$ ?"
].join(' ');
window.rendreReponseIA(quizLikeSource, quizLikeHost);
if (!quizLikeHost.querySelector('.katex') || (quizLikeHost.textContent || '').includes('$')) {
  throw new Error('Quiz-like dollar LaTeX was not fully normalized');
}

// Régression Tuteur : du LaTeX nu mélangé au texte doit être rendu sans
// laisser les commandes visibles, notamment pour les exercices/historiques.
const tuteurHost = window.document.createElement('div');
window.document.body.appendChild(tuteurHost);
const tuteurSample = String.raw`Une poutre continue de longueur totale L=6\,\text{m} est constituée de deux segments.
Moment M_1(x)=5\,\text{kN}\cdot\text{m}.
\begin{pmatrix}1 & 0\\2 & 1\end{pmatrix}`;
window.rendreReponseIA(tuteurSample, tuteurHost);
const tuteurTexteSansKaTeX = tuteurHost.cloneNode(true);
tuteurTexteSansKaTeX.querySelectorAll('.katex').forEach((node) => node.remove());
const tuteurVisible = tuteurTexteSansKaTeX.textContent || '';
for (const commande of ['\\text', '\\cdot', '\\begin', '\\end']) {
  if (tuteurVisible.includes(commande)) {
    throw new Error(`Raw LaTeX command remains in Tuteur content: ${commande}`);
  }
}
if (tuteurHost.querySelectorAll('.katex').length < 3) {
  throw new Error('Naked Tuteur LaTeX was not rendered into KaTeX');
}

// Régression historique Tuteur : la carte utilise maintenant le renderer
// commun, exactement comme la réponse complète.
const historyHost = window.document.createElement('div');
historyHost.innerHTML = '<div class="ai-tuteur-history-question" data-rendu data-rendu-ligne></div>';
window.document.body.appendChild(historyHost);
const historyElement = historyHost.querySelector('[data-rendu]');
const historySample = String.raw`Explique-moi Continuité des rotations : L=6\\,\\text{m}, 0\\le x\\le 3\\,\\text{m}, M_1(x)=5\\,\\text{kN}\\cdot\\text{m}. Matrice : \\begin{pmatrix}1 & 0\\\\2 & 1\\end{pmatrix}`;
window.rendreReponseIA(historySample, historyElement, { enLigne: true });
const historyClone = historyElement.cloneNode(true);
historyClone
  .querySelectorAll('.katex, .gm-katex, .gm-latex-fallback')
  .forEach((node) => node.remove());
const historyVisible = historyClone.textContent || '';
for (const commande of ['\\\\text', '\\\\cdot', '\\\\begin', '\\\\end']) {
  if (historyVisible.includes(commande)) {
    throw new Error(`Raw LaTeX command remains in Tutor history: ${commande}`);
  }
}
if (historyElement.querySelectorAll('.katex').length < 3) {
  throw new Error('Tutor history LaTeX was not rendered');
}

// Régression anti-double-rendu : l'annotation LaTeX de KaTeX ne doit pas
// être retraitée par le filet de sécurité naked-LaTeX.
const nested = historyElement.querySelectorAll('.katex .gm-latex-fallback, .katex .gm-katex');
if (nested.length) {
  throw new Error('Renderer reprocessed KaTeX output');
}

// Mode dégradé
window.marked = null;
window.DOMPurify = null;
host.replaceChildren();
window.rendreReponseIA(sample, host);
const rawDegrade = host.textContent || "";
if (rawDegrade.includes("[[DISPLAY]]") || rawDegrade.includes("[[MATH]]")) {
  throw new Error("Transport markers remain visible in degraded mode");
}
if (host.querySelectorAll(".katex").length < 2) {
  throw new Error("KaTeX direct rendering must survive missing Markdown dependencies");
}

// Réactivation : le renderer doit retrouver la même source et repasser en rendu riche.
window.marked = marked;
window.DOMPurify = purifyInstance;
host.replaceChildren();
window.rendreReponseIA(sample, host);
if (host.querySelectorAll(".katex").length < 2) {
  throw new Error("Renderer did not recover after dependencies became available");
}


// Régressions supplémentaires : code, contexte inline, tableau, XSS, idempotence.
const codeHost = window.document.createElement('div');
window.document.body.appendChild(codeHost);
const fence = String.fromCharCode(96).repeat(3);
const codeSource = [
  'Code :',
  fence + 'python',
  'print("Total:\\nAriary")',
  'print(r"\\\\frac{a}{b}")',
  'print(r"\\\\(\\\\d+\\\\)")',
  fence
].join('\n');
window.rendreReponseIA(codeSource, codeHost);
const code = codeHost.querySelector('pre code');
const expectedCode = codeSource.split('\n').slice(2, 5).join('\n') + '\n';
if (!code || code.textContent !== expectedCode) {
  throw new Error(
    'Code block was modified by the math pipeline: ' +
    JSON.stringify({ expected: expectedCode, got: code ? code.textContent : null })
  );
}
if (code.querySelector('.katex')) {
  throw new Error('KaTeX rendered inside code');
}

const headingHost = window.document.createElement('div');
window.document.body.appendChild(headingHost);
const heading = window.document.createElement('h2');
heading.dataset.rendu = '';
heading.textContent = '2*3*4 = 24';
headingHost.appendChild(heading);
window.rendreTous(headingHost);
if (heading.querySelector('p, table')) {
  throw new Error('Block HTML inserted inside heading context');
}
if (heading.textContent !== '2*3*4 = 24') {
  throw new Error('Arithmetic text altered');
}

const tableHost = window.document.createElement('div');
window.document.body.appendChild(tableHost);
const tableSource = [
  '| Expression | Valeur |',
  '| --- | --- |',
  '| \\(x^2\\) | 4 |'
].join('\n');
window.rendreReponseIA(tableSource, tableHost);
if (!tableHost.querySelector('table')) {
  throw new Error('Markdown table missing');
}
if (!tableHost.querySelector('table .katex')) {
  throw new Error('Math inside table was not rendered');
}

const xssHost = window.document.createElement('div');
window.document.body.appendChild(xssHost);
window.rendreReponseIA('<script>alert(1)</script><img src=x onerror=alert(1)>', xssHost);
if (xssHost.querySelector('script, [onerror]')) {
  throw new Error('XSS payload survived DOMPurify');
}

const before = host.innerHTML;
window.rendreTous(window.document);
if (before !== host.innerHTML) {
  throw new Error('Renderer is not idempotent with stable dependencies');
}


// Chargement borné : simule un CDN principal qui ne répond pas,
// les autres ressources principales qui échouent, puis un secours disponible.
const loaderSource = fs.readFileSync('app/static/js/charger-dependances-ia.js', 'utf8');
const fallbackDom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
  url: 'http://localhost/',
  runScripts: 'outside-only',
});
const fallbackWindow = fallbackDom.window;
let mhchemFallbackReady = false;
let renduRelanceApresChargement = false;
fallbackWindow.rendreTous = function () { renduRelanceApresChargement = true; };
const fallbackRequests = [];
const primaryRequests = [];
function createFakeKatex() {
  return { render(expression, target) {
    const node = fallbackWindow.document.createElement('span');
    node.className = String(expression).startsWith('\\ce{') && !mhchemFallbackReady ? 'katex-error' : 'katex';
    target.appendChild(node);
  } };
}
const setTimeoutOriginal = fallbackWindow.setTimeout.bind(fallbackWindow);
fallbackWindow.setTimeout = function (callback, delay) {
  return setTimeoutOriginal(callback, delay === 2500 ? 0 : delay);
};
const appendHeadOriginal = fallbackWindow.document.head.appendChild.bind(fallbackWindow.document.head);
fallbackWindow.document.head.appendChild = function (element) {
  const result = appendHeadOriginal(element);
  const url = element.src || element.href || '';
  if (url.startsWith('https://cdn.jsdelivr.net/')) {
    primaryRequests.push(url);
    if (!url.includes('/dist/katex.min.js')) {
      Promise.resolve().then(function () {
        if (typeof element.onerror === 'function') element.onerror(new fallbackWindow.Event('error'));
      });
    }
  } else if (url.startsWith('https://unpkg.com/')) {
    fallbackRequests.push(url);
    Promise.resolve().then(function () {
      if (element.tagName === 'SCRIPT') {
        if (url.includes('/dist/katex.min.js')) fallbackWindow.katex = createFakeKatex();
        else if (url.includes('/dist/contrib/mhchem.min.js')) mhchemFallbackReady = true;
        else if (url.includes('/marked.min.js')) fallbackWindow.marked = { parse: function () { return ''; } };
        else if (url.includes('/dist/purify.min.js')) fallbackWindow.DOMPurify = { sanitize: function () { return fallbackWindow.document.createDocumentFragment(); } };
        else if (url.includes('/build/highlight.min.js')) fallbackWindow.hljs = { highlightElement: function () {} };
      }
      if (typeof element.onload === 'function') element.onload(new fallbackWindow.Event('load'));
    });
  }
  return result;
};
vm.runInNewContext(loaderSource, {
  window: fallbackWindow,
  document: fallbackWindow.document,
  console: { warn: function () {}, error: function () {} },
}, { filename: 'charger-dependances-ia.js' });
const fallbackState = await fallbackWindow.GasyMahay.chargerDependancesRenduIA();
if (!fallbackState.katex || !fallbackState.mhchem || !fallbackState.marked || !fallbackState.purify) {
  throw new Error('CDN timeout/fallback did not recover the required AI renderer dependencies');
}
if (!primaryRequests.some((url) => url.includes('/dist/katex.min.js'))) {
  throw new Error('Primary KaTeX CDN was not tried');
}
for (const fragment of [
  '/dist/katex.min.css',
  '/dist/katex.min.js',
  '/dist/contrib/mhchem.min.js',
  '/marked.min.js',
  '/dist/purify.min.js',
]) {
  if (!fallbackRequests.some((url) => url.includes(fragment))) {
    throw new Error('Expected fallback resource was not requested: ' + fragment);
  }
}
if (!fallbackState.css) {
  throw new Error('KaTeX CSS fallback did not recover');
}
if (!renduRelanceApresChargement) {
  throw new Error('Renderer was not retriggered after dependency loading completed');
}


// Prévention issue du guide des symboles : distinguer Unicode, LaTeX, unités et contexte.
const guideHost = window.document.createElement('div');
window.document.body.appendChild(guideHost);
const guideSource = [
  'Symboles Unicode : ≤, ≥, ≠, ≈, →, ↔, ∈, ⊆, ∀, ∃, ℝ, Ω, μ, λ, √, π, ∑, ∫, ∂, ∇.',
  'Unités SI : v = 3 m/s ; a = 2 m/s² ; ρ = 1 kg/m³ ; Ω·m ; J/(mol·K).',
  String.raw`Formules : \(\Delta x=3\), \(\Omega=2\pi f\), \(\hbar\omega\).`,
  String.raw`Notation historique nue : \Delta x, \Omega, \angle ABC, \perp d, \hbar\omega.`,
  'Chimie : Co ≠ CO ; H₂O(l) ⇌ 2 H⁺(aq).',
  'Informatique : a <= b && b != null; x ^ 2; obj?.value ?? 0.',
  'Comptabilité : Ar 125 000 ; MGA ; HT ; TVA ; TTC.'
].join('\n');
window.rendreReponseIA(guideSource, guideHost);
if (guideHost.querySelectorAll('.gm-latex-fallback').length < 5) {
  throw new Error('Undelimited historical Greek/physics LaTeX did not use the fallback renderer');
}
if (guideHost.querySelectorAll('.katex').length < 3) {
  throw new Error('Guide Greek-letter/physics formulas were not rendered');
}
const guideClone = guideHost.cloneNode(true);
guideClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const guideVisible = guideClone.textContent || '';
for (const command of ['\\Delta', '\\Omega', '\\hbar', '\\angle', '\\perp']) {
  if (guideVisible.includes(command)) throw new Error('Raw LaTeX command remained visible: ' + command);
}
for (const symbol of ['≤', 'ℝ', 'Ω', '∇', 'm/s²', 'Ω·m', 'Co ≠ CO', 'Ar 125 000', 'MGA', 'TVA', '&&', '?.', '??']) {
  if (!guideVisible.includes(symbol)) throw new Error('Guide symbol/context was altered: ' + symbol);
}
// Régression exacte du cas signalé : les escapes JSON \f doivent redevenir des fractions.
const badQuizHost = window.document.createElement('div');
window.document.body.appendChild(badQuizHost);
const formFeed = String.fromCharCode(12);
window.rendreReponseIA(
  'Question 03\nQuel est le résultat de la simplification de (displaystyle ' + formFeed + 'rac{12}{18}) ?',
  badQuizHost
);
if (badQuizHost.querySelectorAll('.katex').length < 1) {
  throw new Error('Broken historical quiz fraction was not recovered');
}
const badQuizText = badQuizHost.cloneNode(true);
badQuizText.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
if ((badQuizText.textContent || '').includes(formFeed) || (badQuizText.textContent || '').includes('\\frac')) {
  throw new Error('Broken raw control/LaTeX remained visible in the quiz question');
}
const fractionOptions = ['2/3', '3/4', '4/6', '5/9'];
const optionLabels = ['A', 'B', 'C', 'D'];
const optionNodes = [];
for (let index = 0; index < fractionOptions.length; index += 1) {
  const row = window.document.createElement('div');
  row.className = 'quiz-choice';
  const label = window.document.createElement('span');
  label.className = 'quiz-choice-label';
  label.textContent = optionLabels[index];
  const answer = window.document.createElement('span');
  answer.className = 'quiz-choice-value';
  const [numerator, denominator] = fractionOptions[index].split('/');
  window.document.body.appendChild(row);
  row.append(label, answer);
  window.rendreReponseIA('(' + formFeed + 'rac{' + numerator + '}{' + denominator + '})', answer);
  optionNodes.push(row);
}
if (optionNodes.length !== 4 || new Set(optionNodes.map((row) => row.querySelector('.quiz-choice-label')?.textContent)).size !== 4) {
  throw new Error('Quiz answers were not kept as four separate selectable options');
}
if (optionNodes.some((row) => row.querySelectorAll('.katex').length < 1)) {
  throw new Error('One or more quiz fraction options were not rendered');
}
for (const row of optionNodes) {
  const answer = row.querySelector('.quiz-choice-value');
  const clone = answer.cloneNode(true);
  clone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
  const visible = clone.textContent || '';
  if (visible.includes(formFeed) || visible.includes('\\frac')) throw new Error('Raw fraction leaked in a choice');
}

// Chaque collision JSON connue consomme la séquence entière ; le mot résiduel
// (rac/ext/abla/ho/eta) ne doit pas rester visible après le rendu.
const corruptedCommands = [
  { name: 'form-feed / frac', value: formFeed + 'rac{1}{2}', tail: 'rac' },
  { name: 'tab / text', value: '\t' + 'ext{m}', tail: 'ext' },
  { name: 'newline / nabla', value: '\n' + 'abla f', tail: 'abla' },
  { name: 'carriage-return / rho', value: '\r' + 'ho', tail: 'ho' },
  { name: 'backspace / beta', value: String.fromCharCode(8) + 'eta', tail: 'eta' }
];
for (const sample of corruptedCommands) {
  const target = window.document.createElement('div');
  window.document.body.appendChild(target);
  window.rendreReponseIA('Contrôle : ' + sample.value, target);
  if (!target.querySelector('.katex, .gm-latex-fallback, .gm-katex')) {
    throw new Error('Legacy control escape was not recovered: ' + sample.name);
  }
  const plain = target.cloneNode(true);
  plain.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
  const visible = plain.textContent || '';
  if (visible.includes(sample.tail) || /[\u0008\u000C\t\r]/.test(visible)) {
    throw new Error('Control character or command tail remained visible: ' + sample.name);
  }
}
// Les corrections doivent aussi intervenir si les données historiques ont déjà des délimiteurs math.
const delimitedCorruptions = [
  { name: 'inline delimiters', value: 'Inline : \\(' + formFeed + 'rac{1}{2}\\)' },
  { name: 'legacy dollar delimiters', value: 'Dollar : ' + String.fromCharCode(36) + formFeed + 'rac{3}{4}' + String.fromCharCode(36) },
  { name: 'display delimiters', value: 'Display : \\[' + '\t' + 'ext{m}\\]' }
];
for (const sample of delimitedCorruptions) {
  const target = window.document.createElement('div');
  window.document.body.appendChild(target);
  window.rendreReponseIA(sample.value, target);
  if (!target.querySelector('.katex')) {
    throw new Error('Corrupted command inside delimited math was not repaired: ' + sample.name);
  }
  const plain = target.cloneNode(true);
  plain.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
  if (/[\u0008\u000C\t\r]/.test(plain.textContent || '')) {
    throw new Error('Control character remained in an already-delimited formula: ' + sample.name);
  }
}

// Régressions exactes issues du rendu réel : commandes sans antislash,
// \t interprété en tabulation avant « imes », symboles de physique et chimie.
const scienceRecoveryHost = window.document.createElement('div');
window.document.body.appendChild(scienceRecoveryHost);
const tabEscape = String.fromCharCode(9);
const scienceRecoverySource = [
  'Estimation : ( sqrt{1000}approx31,6) ; estimation arrondie : 30\u202F≈\u202F32.',
  "On calcule d'abord (7" + tabEscape + "imes 8 + 9 = 65), puis on explique le résultat.",
  'Physique : (rho = 1 kg/m^3) et (Delta E = hbar omega).',
  "Chimie : 2H2 + O2 -> 2H2O ; Co n'est pas CO."
].join('\n');
window.rendreReponseIA(scienceRecoverySource, scienceRecoveryHost);
if (scienceRecoveryHost.querySelectorAll('.katex').length < 5) {
  throw new Error('Math/physics/reaction expressions were not grouped into KaTeX');
}
if (scienceRecoveryHost.querySelectorAll('.katex-error').length) {
  throw new Error('A recovered scientific formula contains a KaTeX error');
}
const scienceRecoveryClone = scienceRecoveryHost.cloneNode(true);
scienceRecoveryClone
  .querySelectorAll('.katex, .gm-katex, .gm-latex-fallback')
  .forEach((node) => node.remove());
const scienceRecoveryText = scienceRecoveryClone.textContent || '';
for (const raw of ['sqrt{1000}', 'approx31,6', 'imes 8', 'rho =', 'Delta E', 'hbar omega', '\\ce{2H2']) {
  if (scienceRecoveryText.includes(raw)) {
    throw new Error('Raw scientific notation remained visible: ' + raw);
  }
}
if (!scienceRecoveryText.includes("Co n'est pas CO")) {
  throw new Error('Chemical element capitalization Co/CO was altered');
}
if (!scienceRecoveryText.includes('30\u202F≈\u202F32')) {
  throw new Error('A valid Unicode approximation was altered');
}

console.log(JSON.stringify({ ok: true, legacy_dollar_math: true, katex_nodes: host.querySelectorAll('.katex').length, code_unchanged: true, idempotent: true }));
