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
if (raw.includes('\\lambda') || raw.includes('\\det')) {
  throw new Error('Raw LaTeX command remains visible in text');
}
console.log(JSON.stringify({ ok: true, katex_nodes: host.querySelectorAll('.katex').length }));