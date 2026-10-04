import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
import { marked } from 'marked';
import katex from 'katex';
import createDOMPurify from 'dompurify';

const source = fs.readFileSync('app/static/js/rendu_ia.js', 'utf8');
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

// Mode dégradé : Marked et DOMPurify indisponibles, les formules doivent
// toujours disparaître des marqueurs de transport.
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

console.log(JSON.stringify({ ok: true, katex_nodes: host.querySelectorAll('.katex').length, code_unchanged: true, idempotent: true }));