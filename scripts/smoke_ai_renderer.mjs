import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { marked } from 'marked';
import katex from 'katex';
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
const visibleClone = host.cloneNode(true);
visibleClone.querySelectorAll('.katex').forEach((node) => node.remove());
const visibleText = visibleClone.textContent || '';
if (visibleText.includes('\\lambda') || visibleText.includes('\\det')) {
  throw new Error('Raw LaTeX command remains outside rendered KaTeX nodes');
}

// Régression quiz : les anciens délimiteurs $...$ et $$...$$ doivent être
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

// Régression historique Tuteur : la carte compacte ne doit plus afficher
// de LaTeX/Markdown brut. On valide le résumé directement dans le DOM.
const historyDom = new JSDOM('<!doctype html><html><body><div class="ai-tuteur-history-question" data-ai-resume></div></body></html>', {
  url: 'http://localhost/',
  runScripts: 'outside-only',
});
const historyContext = {
  window: historyDom.window,
  document: historyDom.window.document,
  NodeFilter: historyDom.window.NodeFilter,
  console,
  setTimeout,
  clearTimeout,
};
const historyElement = historyDom.window.document.querySelector('[data-ai-resume]');
historyElement.setAttribute(
  'data-ai-resume',
  String.raw\`Explique-moi Continuité des rotations : L=6\,\text{m}, 0\le x\le 3\,\text{m}, M_1(x)=5\,\text{kN}\cdot\text{m}.
Matrice : \begin{pmatrix}1 & 0\\2 & 1\end{pmatrix}\`
);
vm.runInNewContext(aiLearningSource, historyContext, { filename: 'ai-learning.js' });
await new Promise((resolve) => setTimeout(resolve, 0));
const historyVisible = historyElement.textContent || '';
for (const brut of ['\\text', '\\cdot', '\\begin', '\\end', '$']) {
  if (historyVisible.includes(brut)) {
    throw new Error(\`Raw history formatting remains visible: \${brut}\`);
  }
}
if (!historyVisible.includes('L=6') || !historyVisible.includes('kN')) {
  throw new Error('History summary lost the useful mathematical context');
}

// Mode dégradé

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
  throw new Error('Code block was modified by the math pipeline');
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

console.log(JSON.stringify({ ok: true, legacy_dollar_math: true, katex_nodes: host.querySelectorAll('.katex').length, code_unchanged: true, idempotent: true }));
]) {
  if (historyVisible.includes(brut)) {
    throw new Error(`Raw history formatting remains visible: ${brut}`);
  }
}
if (!historyVisible.includes('L=6') || !historyVisible.includes('kN')) {
  throw new Error('History summary lost the useful mathematical context');
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
  throw new Error('Code block was modified by the math pipeline');
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

console.log(JSON.stringify({ ok: true, legacy_dollar_math: true, katex_nodes: host.querySelectorAll('.katex').length, code_unchanged: true, idempotent: true }));
