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
window.DOMPurify = createDOMPurify(window);
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

import 'katex/contrib/mhchem.js';

function creerHost() {
  const host = window.document.createElement('div');
  window.document.body.appendChild(host);
  return host;
}

function visibleTextSansKatex(host) {
  const clone = host.cloneNode(true);
  clone.querySelectorAll('.katex').forEach((node) => node.remove());
  return clone.textContent || '';
}

const host = creerHost();
const sample = [
  'Cinétique :',
  '\\[',
  '\\begin{aligned}',
  'a &= b \\\\',
  'c &= d',
  '\\end{aligned}',
  '\\]',
  '',
  'Matrice :',
  '\\[',
  '\\begin{pmatrix}',
  '1 & 2 \\\\',
  '3 & 4',
  '\\end{pmatrix}',
  '\\]',
  '',
  'Système :',
  '\\[',
  '\\begin{cases}',
  'x+y=10 \\\\',
  'x-y=2',
  '\\end{cases}',
  '\\]',
  '',
  'Physique : \\\\( \\\\mathrm{m\\\\,s^{-2}} \\\\), \\\\( \\\\vec{F} \\\\), \\\\( \\\\nabla \\\\times \\\\vec{E} \\\\).',
  'Chimie : \\\\( \\\\ce{H2O} \\\\), \\\\( \\\\ce{2H2 + O2 -> 2H2O} \\\\), \\\\( \\\\ce{Fe^{3+}} \\\\).',
  'Et : \\\\( \\\\det(A)=ad-bc \\\\).'
].join('\\n');
window.rendreReponseIA(sample, host);

if (host.querySelectorAll('.katex').length < 8) {
  throw new Error('Expected KaTeX nodes were not generated for maths/physics/chemistry');
}
if (host.querySelector('script, img[onerror], iframe')) {
  throw new Error('Unsafe HTML survived sanitization');
}
if (visibleTextSansKatex(host).includes('\\\\lambda') || visibleTextSansKatex(host).includes('\\\\det')) {
  throw new Error('Raw LaTeX command remains outside rendered KaTeX nodes');
}

const codeHost = creerHost();
const fence = String.fromCharCode(96).repeat(3);
const codeSource = [
  'Code :',
  fence + 'python',
  'print("Total:\\nAriary")',
  'print(r"\\\\frac{a}{b}")',
  'print(r"\\\\(\\\\d+)")',
  fence
].join('\\n');
window.rendreReponseIA(codeSource, codeHost);
const code = codeHost.querySelector('pre code');
if (!code || code.textContent !== 'print("Total:\\nAriary")\\nprint(r"\\\\frac{a}{b}")\\nprint(r"\\\\(\\\\d+)")\\n') {
  throw new Error('Code block was modified by the math pipeline');
}
if (code.querySelector('.katex')) {
  throw new Error('KaTeX was rendered inside a code block');
}

const headingHost = creerHost();
const heading = window.document.createElement('h2');
heading.dataset.rendu = '';
heading.textContent = '2*3*4 = 24';
headingHost.appendChild(heading);
window.rendreTous(headingHost);
if (heading.querySelector('p, table')) {
  throw new Error('Invalid block content was inserted into a heading');
}
if (heading.textContent !== '2*3*4 = 24') {
  throw new Error('Arithmetic choice was altered by Markdown');
}

const tableHost = creerHost();
window.rendreReponseIA(
  '| Expression | Valeur |\\n| --- | --- |\\n| \\\\( |x| \\\\) | 2 |',
  tableHost
);
if (!tableHost.querySelector('table .katex')) {
  throw new Error('Absolute-value formula in a Markdown table was not rendered');
}

const xssHost = creerHost();
window.rendreReponseIA('<script>alert(1)</script><img src=x onerror=alert(1)>', xssHost);
if (xssHost.querySelector('script, [onerror]')) {
  throw new Error('XSS payload survived DOMPurify');
}

const before = host.innerHTML;
window.rendreTous(window.document);
const after = host.innerHTML;
if (before !== after) {
  throw new Error('rendreTous is not idempotent');
}

console.log(JSON.stringify({
  ok: true,
  katex_nodes: host.querySelectorAll('.katex').length,
  code_unchanged: true,
  idempotent: true,
}));
