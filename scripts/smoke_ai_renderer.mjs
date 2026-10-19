import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { marked } from 'marked';
import katex from 'katex';
const mhchemSource = fs.readFileSync('node_modules/katex/dist/contrib/mhchem.min.js', 'utf8');
import createDOMPurify from 'dompurify';

// Vérifie les vraies distributions locales produites par le script de build.
const vendorRoot = 'app/static/vendor';
const vendorManifest = JSON.parse(fs.readFileSync(vendorRoot + '/manifest.json', 'utf8'));
const vendorVersions = {
  katex: '0.19.0',
  marked: '18.1.1',
  dompurify: '3.4.17',
  'highlight.js': '11.12.0'
};
for (const [name, version] of Object.entries(vendorVersions)) {
  if (!vendorManifest.packages[name] || vendorManifest.packages[name].version !== version) {
    throw new Error('Vendor package version mismatch for ' + name + ': expected ' + version);
  }
}
const katexCssLocal = fs.readFileSync(vendorRoot + '/katex/katex.min.css', 'utf8');
const fontNames = Array.from(katexCssLocal.matchAll(/url\(["']?(?:\.\/)?fonts\/([^)"']+)["']?\)/g), match => match[1].split('?')[0]);
if (fontNames.length < 10) {
  throw new Error('KaTeX stylesheet does not reference the expected full font set');
}
for (const fontName of fontNames) {
  if (!fs.existsSync(vendorRoot + '/katex/fonts/' + fontName)) {
    throw new Error('KaTeX stylesheet references a font that was not bundled locally: ' + fontName);
  }
}
for (const required of [
  '/katex/katex.min.js',
  '/katex/contrib/mhchem.min.js',
  '/marked/marked.min.js',
  '/dompurify/purify.min.js',
  '/highlightjs/highlight.min.js',
  '/THIRD_PARTY_NOTICES.md'
]) {
  if (!fs.existsSync(vendorRoot + required)) throw new Error('Missing local browser dependency: ' + required);
}

// Exécute les bundles réellement téléchargés dans un navigateur isolé.
const vendorDom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
  url: 'http://localhost/',
  runScripts: 'outside-only',
});
const vendorWindow = vendorDom.window;
for (const scriptPath of [
  vendorRoot + '/katex/katex.min.js',
  vendorRoot + '/katex/contrib/mhchem.min.js',
  vendorRoot + '/marked/marked.min.js',
  vendorRoot + '/dompurify/purify.min.js',
  vendorRoot + '/highlightjs/highlight.min.js'
]) {
  vendorWindow.eval(fs.readFileSync(scriptPath, 'utf8'));
}
if (!vendorWindow.katex || typeof vendorWindow.katex.render !== 'function') {
  throw new Error('Locally vendored KaTeX did not initialize');
}
if (!vendorWindow.marked || typeof vendorWindow.marked.parse !== 'function') {
  throw new Error('Locally vendored Marked did not initialize');
}
if (!vendorWindow.DOMPurify || typeof vendorWindow.DOMPurify.sanitize !== 'function') {
  throw new Error('Locally vendored DOMPurify did not initialize');
}
if (!vendorWindow.hljs || typeof vendorWindow.hljs.highlight !== 'function') {
  throw new Error('Locally vendored Highlight.js did not initialize');
}
const vendorMathHost = vendorWindow.document.createElement('div');
vendorWindow.katex.render('\\frac{1}{2}', vendorMathHost, { throwOnError: false });
vendorWindow.katex.render('\\ce{2H2 + O2 -> 2H2O}', vendorMathHost, { throwOnError: false, strict: 'ignore' });
if (vendorMathHost.querySelectorAll('.katex').length !== 2 || vendorMathHost.querySelector('.katex-error')) {
  throw new Error('Locally vendored KaTeX/mhchem failed the fraction/reaction smoke test');
}
if (!vendorWindow.marked.parse('**test**').includes('<strong>test</strong>')) {
  throw new Error('Locally vendored Marked did not parse Markdown correctly');
}
const vendorUnsafe = vendorWindow.DOMPurify.sanitize('<img src=x onerror=alert(1)><script>alert(2)</script>');
if (/onerror|<script/i.test(vendorUnsafe)) {
  throw new Error('Locally vendored DOMPurify failed the XSS smoke test');
}
if (!vendorWindow.hljs.highlight('const total = 1;', { language: 'javascript' }).value.includes('total')) {
  throw new Error('Locally vendored Highlight.js failed its JavaScript smoke test');
}

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

 // Régression réelle : certains modèles placent les maths dans des backticks,
 // puis laissent une commande \times à l'extérieur. Ces calculs doivent être
 // rendus en une formule complète, tandis que les blocs de code sont préservés.
 const inlineCodeMathHost = window.document.createElement('div');
 window.document.body.appendChild(inlineCodeMathHost);
 const inlineCodeMathSource = [
   "Fraction : `\\frac{123456000}{789000}`.",
   "Euclide : `123456=156`\\times789 + 372.",
   "Puissance : `123456000=123456×10^3`."
 ].join('\\n');
 window.rendreReponseIA(inlineCodeMathSource, inlineCodeMathHost);
 if (inlineCodeMathHost.querySelectorAll('.katex').length < 3) {
   throw new Error('Inline-code math from the Tuteur example was not converted into complete KaTeX formulas');
 }
 if (inlineCodeMathHost.querySelector('code')) {
   throw new Error('Inline mathematical notation remained protected as code');
 }
 const inlineMathClone = inlineCodeMathHost.cloneNode(true);
 inlineMathClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
 const inlineMathPlain = inlineMathClone.textContent || '';
 if (inlineMathPlain.includes('\\times') || inlineMathPlain.includes('\\frac') || inlineMathPlain.includes('`')) {
   throw new Error('Raw inline-code LaTeX remains visible after math recovery');
 }
const brokenTimesHost = window.document.createElement('div');
window.document.body.appendChild(brokenTimesHost);
const tickCharacter = String.fromCharCode(96);
const brokenTimesSource =
  "Euclide : " + tickCharacter + "123456=156" + tickCharacter +
  String.fromCharCode(9) + "imes789 + 372.";
window.rendreReponseIA(brokenTimesSource, brokenTimesHost);
if (brokenTimesHost.querySelectorAll('.katex').length !== 1) {
  throw new Error('A tab-corrupted LaTeX times command after inline code was not grouped into one formula');
}
const brokenTimesClone = brokenTimesHost.cloneNode(true);
brokenTimesClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const brokenTimesPlain = brokenTimesClone.textContent || '';
if (brokenTimesPlain.includes('imes789') || brokenTimesPlain.includes(String.fromCharCode(9))) {
  throw new Error('A tab-corrupted multiplication command remained visible as raw text');
}

// Régression exacte du Tuteur : les identités fragmentées doivent devenir
// deux formules canoniques, sans conserver l'expansion fautive.
const euclideDetailedHost = window.document.createElement('div');
window.document.body.appendChild(euclideDetailedHost);
const euclideDetailedSource =
  "PGCD — algorithme d'Euclide :\n" +
  " - " + tickCharacter + "987654321=8000" + tickCharacter +
  "\\times123456 + 987654321 - 8000\\times123456 = " +
  tickCharacter + "987654321−987648000=6321" + tickCharacter + "\n" +
  " - " + tickCharacter + "123456=19" + tickCharacter +
  "\\times6321 + 123456 - 19\\times6321 = " +
  tickCharacter + "123456−120099=3357" + tickCharacter;
const indiceFormulesEuclide = formulesRendues.length;
window.rendreReponseIA(euclideDetailedSource, euclideDetailedHost);
if (euclideDetailedHost.querySelectorAll('.katex').length !== 10) {
  throw new Error('The full Euclidean chain should contain ten rendered divisions');
}
const euclideFormules = formulesRendues.slice(indiceFormulesEuclide);
const formulesAttendues = [
  String.raw`987654321=8000\times123456+6321`,
  String.raw`123456=19\times6321+3357`,
  String.raw`2964=7\times393+213`,
  String.raw`393=1\times213+180`,
  String.raw`15=5\times3+0`
];
if (formulesAttendues.some((formule) => !euclideFormules.includes(formule))) {
  throw new Error('The Euclidean chain was not recalculated consistently from the original dividend and divisor');
}
if (euclideFormules.some((formule) =>
  formule.includes(String.raw`393=1\\times315+78`) ||
  formule.includes(String.raw`2964=7\\times393+315`)
)) {
  throw new Error('A stale Euclidean remainder remained in the rendered chain');
}
const euclideDetailedClone = euclideDetailedHost.cloneNode(true);
euclideDetailedClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const euclideDetailedPlain = euclideDetailedClone.textContent || '';
if (
  euclideDetailedPlain.includes('987654321−987648000') ||
  euclideDetailedPlain.includes('123456−120099') ||
  euclideDetailedPlain.includes('393=1×315+78') ||
  euclideDetailedPlain.includes('2964=7×393+315') ||
  euclideDetailedPlain.includes('\\\\times') ||
  euclideDetailedPlain.includes(tickCharacter)
) {
  throw new Error('Broken Euclidean arithmetic remained visible beside the rendered formulas');
}

// Régression Tuteur : les anciennes fractions PGCD concaténées doivent
// redevenir des fractions KaTeX cohérentes sans laisser les nombres collés.
const pgcdFractionHost = window.document.createElement('div');
window.document.body.appendChild(pgcdFractionHost);
const pgcdFractionSource = [
  "1. Factorisation des puissances de 10 :",
  "   `9876543210=987654321×10` et `1234560=123456×10`.",
  "   Les 10 se simplifient, il reste `987654321123456`.",
  "2. Calcul du PGCD de 987654321 et 123456.",
  "3. Division par le PGCD :\\",
  "   `987654321/3123456/3=32921810741152`.",
  "   La fraction finale réduite est `32921810741152`."
].join("\n");
const formulesPgcdAvant = formulesRendues.length;
window.rendreReponseIA(pgcdFractionSource, pgcdFractionHost);
const formulesPgcdRendues = formulesRendues.slice(formulesPgcdAvant);
if (
  !formulesPgcdRendues.some((formule) => formule.includes('987654321') && formule.includes('123456')) ||
  !formulesPgcdRendues.some((formule) => formule.includes('329218107') && formule.includes('41152')) ||
  !formulesPgcdRendues.some((formule) => formule.includes('987654321') && formule.includes('123456') && formule.includes('329218107') && formule.includes('41152'))
) {
  throw new Error('Malformed PGCD fractions were not rebuilt as verified numerator/denominator expressions');
}
const pgcdFractionClone = pgcdFractionHost.cloneNode(true);
pgcdFractionClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const pgcdFractionPlain = pgcdFractionClone.textContent || '';
if (pgcdFractionPlain.includes('987654321123456') || pgcdFractionPlain.includes('32921810741152')) {
  throw new Error('Concatenated PGCD numerator and denominator remained visible after rendering');
}

// Régression exacte du Tuteur : les fractions et les chaînes d'Euclide
// doivent rester cohérentes avec leur PGCD, même si le texte est concaténé.
const pgcdExemplesHost = window.document.createElement('div');
window.document.body.appendChild(pgcdExemplesHost);
const pgcdExemplesSource = [
  "Pour réduire une fraction, on divise le numérateur et le dénominateur par leur plus grand commun diviseur (PGCD).",
  "Exemple : \x60" + "48180" + "\x60.",
  "On calcule le PGCD de 48 et 180 avec l'algorithme d'Euclide : \\\\(180=60\\\\times3+0), \x6048=36×1+12\x60, \x6036=12×3+0\x60.",
  "Le dernier reste non nul est 12, donc PGCD(48,180)=12.",
  "On divise chaque terme : \x6048÷12180÷12=415\x60. La fraction est maintenant irréductible.",
  "Exercice proposé (progressif) : réduire la fraction \x6084210\x60.",
  "Correction de l'exercice : 1. Calcul du PGCD(84,210) : \\\\(210=105\\\\times2+0), \x6084=42×2+0\x60. Donc PGCD=42.",
  "2. Division : \x6084÷42210÷42=25\x60. La fraction réduite est \x6025\x60."
].join("\n");
const pgcdFormulaOffset = formulesRendues.length;
window.rendreReponseIA(pgcdExemplesSource, pgcdExemplesHost);
const pgcdFormules = formulesRendues.slice(pgcdFormulaOffset);
const pgcdExpected = [
  'frac{48}{180}',
  'frac{4}{15}',
  'frac{84}{210}',
  'frac{2}{5}',
  '180=3times48+36',
  '48=1times36+12',
  '36=3times12+0',
  '210=2times84+42',
  '84=2times42+0'
];
const pgcdFormulesNormalisees = pgcdFormules.map((actual) =>
  actual.split(String.fromCharCode(92)).join('').replace(/\s+/g, '')
);
if (pgcdExpected.some((expected) => !pgcdFormulesNormalisees.some((actual) => actual.includes(expected)))) {
  throw new Error('Missing PGCD expressions: ' + pgcdExpected.filter((expected) => !pgcdFormulesNormalisees.some((actual) => actual.includes(expected))).join(', ') + '; actual=' + JSON.stringify(pgcdFormules) + '; html=' + pgcdExemplesHost.innerHTML);
}
const pgcdExemplesClone = pgcdExemplesHost.cloneNode(true);
pgcdExemplesClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const pgcdPlain = pgcdExemplesClone.textContent || '';
if (
  pgcdPlain.includes('48180') ||
  pgcdPlain.includes('84210') ||
  pgcdPlain.includes('48÷12180÷12=415') ||
  pgcdPlain.includes('84÷42210÷42=25') ||
  pgcdPlain.includes('180=60×3+0') ||
  pgcdPlain.includes('210=105×2+0')
) {
  throw new Error('Malformed concatenated PGCD arithmetic remained visible after rendering');
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
const localRequests = [];
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
  if (url.startsWith('http://localhost/static/vendor/')) {
    localRequests.push(url);
    Promise.resolve().then(function () {
      if (typeof element.onerror === 'function') element.onerror(new fallbackWindow.Event('error'));
    });
  } else if (url.startsWith('https://cdn.jsdelivr.net/')) {
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
for (const localFragment of [
  '/katex/katex.min.css',
  '/katex/katex.min.js',
  '/katex/contrib/mhchem.min.js',
  '/marked/marked.min.js',
  '/dompurify/purify.min.js',
  '/highlightjs/highlight.min.js'
]) {
  if (!localRequests.some((url) => url.includes(localFragment))) {
    throw new Error('Local dependency was not tried before CDN fallback: ' + localFragment);
  }
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



// Succès normal : les ressources locales doivent suffire sans appeler un CDN.
const localDom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
  url: 'http://localhost/',
  runScripts: 'outside-only',
});
const localWindow = localDom.window;
let localMhchemReady = false;
let localRerendered = false;
const localAssetRequests = [];
const unexpectedExternalRequests = [];
localWindow.rendreTous = function () { localRerendered = true; };
function createLocallyAvailableKatex() {
  return { render(expression, target) {
    const node = localWindow.document.createElement('span');
    node.className = String(expression).startsWith('\\ce{') && !localMhchemReady ? 'katex-error' : 'katex';
    target.appendChild(node);
  } };
}
const appendLocalHeadOriginal = localWindow.document.head.appendChild.bind(localWindow.document.head);
localWindow.document.head.appendChild = function (element) {
  const result = appendLocalHeadOriginal(element);
  const url = element.src || element.href || '';
  if (url.startsWith('http://localhost/static/vendor/')) {
    localAssetRequests.push(url);
    Promise.resolve().then(function () {
      if (element.tagName === 'LINK') {
        element.dataset.gmKatexCharge = 'ok';
      } else if (element.tagName === 'SCRIPT') {
        if (url.includes('/katex/katex.min.js')) localWindow.katex = createLocallyAvailableKatex();
        else if (url.includes('/katex/contrib/mhchem.min.js')) localMhchemReady = true;
        else if (url.includes('/marked/marked.min.js')) localWindow.marked = { parse: function () { return ''; } };
        else if (url.includes('/dompurify/purify.min.js')) localWindow.DOMPurify = { sanitize: function () { return localWindow.document.createDocumentFragment(); } };
        else if (url.includes('/highlightjs/highlight.min.js')) localWindow.hljs = { highlightElement: function () {} };
      }
      if (typeof element.onload === 'function') element.onload(new localWindow.Event('load'));
    });
  } else if (url.startsWith('https://')) {
    unexpectedExternalRequests.push(url);
    Promise.resolve().then(function () {
      if (typeof element.onerror === 'function') element.onerror(new localWindow.Event('error'));
    });
  }
  return result;
};
vm.runInNewContext(loaderSource, {
  window: localWindow,
  document: localWindow.document,
  console: { warn: function () {}, error: function () {} },
}, { filename: 'charger-dependances-ia-local.js' });
const localState = await localWindow.GasyMahay.chargerDependancesRenduIA();
if (!localState.katex || !localState.mhchem || !localState.marked || !localState.purify || !localState.css || !localState.highlight) {
  throw new Error('The local asset set did not initialize every renderer dependency');
}
if (unexpectedExternalRequests.length) {
  throw new Error('A CDN was contacted even though local dependency files were available: ' + unexpectedExternalRequests.join(', '));
}
if (!localRerendered) {
  throw new Error('Renderer was not retriggered after local dependency loading');
}
for (const localFragment of [
  '/katex/katex.min.css',
  '/katex/katex.min.js',
  '/katex/contrib/mhchem.min.js',
  '/marked/marked.min.js',
  '/dompurify/purify.min.js',
  '/highlightjs/highlight.min.js'
]) {
  if (!localAssetRequests.some((url) => url.includes(localFragment))) {
    throw new Error('Expected vendored local asset was not loaded: ' + localFragment);
  }
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


// Audit multidisciplinaire : matrices, fonctions par morceaux, unités SI,
// réactions chimiques, montants comptables et opérateurs de programmation.
const multiDisciplineHost = window.document.createElement('div');
window.document.body.appendChild(multiDisciplineHost);
const tickForCode = String.fromCharCode(96);
const codeFence = tickForCode.repeat(3);
const multiDisciplineSource = [
  String.raw`Mathématiques — matrice : \(A=\begin{pmatrix}1&2\\3&4\end{pmatrix}\).`,
  String.raw`Fonction par morceaux : \(f(x)=\begin{cases}x^2,&x\ge 0\\-x,&x<0\end{cases}\).`,
  String.raw`Physique : \(\Delta E=\hbar\omega\), \(v=3\,\mathrm{m/s}\), \(a=2\,\mathrm{m/s^{2}}\), \(\rho=1\,\mathrm{kg/m^{3}}\).`,
  String.raw`Chimie : \(\ce{2H2 + O2 -> 2H2O}\) et \(\ce{Fe^{3+} + 3OH^- -> Fe(OH)3}\).`,
  'Comptabilité : Ar 125 000 MGA ; HT 100 000 ; TVA 20 000 ; TTC 120 000.',
  'Informatique : ' + tickForCode + 'const ok = a <= b && value !== null; const fallback = obj?.value ?? 0;' + tickForCode,
  'Code clôturé :\n' + codeFence + 'js\nconst ratio = 12 / 18;\\nif (ratio <= 1 && ready !== null) console.log(ratio);\n' + codeFence
].join('\n');
const multiFormulaOffset = formulesRendues.length;
window.rendreReponseIA(multiDisciplineSource, multiDisciplineHost);
const multiRenderedFormulas = formulesRendues.slice(multiFormulaOffset);
if (multiRenderedFormulas.length !== 8) {
  throw new Error('Expected exactly eight scientific expressions; got ' + multiRenderedFormulas.length + ': ' + JSON.stringify(multiRenderedFormulas));
}
if (multiDisciplineHost.querySelectorAll('.katex-error').length) {
  throw new Error('A matrix, piecewise function, SI unit or chemical equation caused a KaTeX error');
}
for (const formula of [
  String.raw`\begin{pmatrix}`,
  String.raw`\begin{cases}`,
  String.raw`\mathrm{kg/m^{3}}`,
  String.raw`\ce{2H2 + O2 -> 2H2O}`,
  String.raw`\ce{Fe^{3+} + 3OH^- -> Fe(OH)3}`
]) {
  if (!multiRenderedFormulas.some((rendered) => rendered.includes(formula))) {
    throw new Error('Scientific formula was lost or rewritten: ' + formula);
  }
}
const multiPlainClone = multiDisciplineHost.cloneNode(true);
multiPlainClone.querySelectorAll('.katex, .gm-katex, .gm-latex-fallback').forEach((node) => node.remove());
const multiPlainText = multiPlainClone.textContent || '';
for (const preserved of [
  'Ar 125 000 MGA',
  'HT 100 000',
  'TVA 20 000',
  'TTC 120 000',
  'a <= b && value !== null',
  'obj?.value ?? 0',
  'const ratio = 12 / 18;',
  'ready !== null'
]) {
  if (!multiPlainText.includes(preserved)) {
    throw new Error('Non-mathematical content was altered or lost: ' + preserved);
  }
}
if (multiDisciplineHost.querySelector('code') === null || multiDisciplineHost.querySelector('pre') === null) {
  throw new Error('Inline or fenced programming code was not preserved as code');
}
if (multiDisciplineHost.querySelector('code .katex, pre .katex')) {
  throw new Error('Programming code was incorrectly passed to KaTeX');
}

// Vérifie la sanitisation réelle du HTML hostile dans le même pipeline.
// Le texte utile doit rester visible, mais les attributs exécutables et scripts sont retirés.
const securityHost = window.document.createElement('div');
window.document.body.appendChild(securityHost);
window.rendreReponseIA(
  'Texte sûr <img src="x" onerror="alert(1)"> après image <script>alert(2)</script>',
  securityHost
);
if (securityHost.querySelector('img[onerror], script')) {
  throw new Error('Un attribut exécutable ou un script HTML a survécu à DOMPurify');
}
if (!(securityHost.textContent || '').includes('Texte sûr') || !(securityHost.textContent || '').includes('après image')) {
  throw new Error('Safe text around sanitized HTML was lost');
}

console.log(JSON.stringify({ ok: true, legacy_dollar_math: true, katex_nodes: host.querySelectorAll('.katex').length, code_unchanged: true, idempotent: true }));
