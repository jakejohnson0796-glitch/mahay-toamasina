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

console.log(JSON.stringify({ ok: true, katex_nodes: host.querySelectorAll('.katex').length }));