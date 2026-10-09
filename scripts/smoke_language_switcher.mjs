import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const source = fs.readFileSync('app/static/js/langue.js', 'utf8');
const dom = new JSDOM(`<!doctype html><html lang="fr"><head><title>Connexion — Gasy Mahay</title></head><body>
  <div class="tb-sidebar-langue">
    <label for="select-langue">Langue</label>
    <select id="select-langue" aria-label="Choisir la langue">
      <option value="fr">Français</option><option value="mg">Malagasy</option>
    </select>
  </div>
  <nav><a id="navigation">Tableau de bord</a></nav>
  <input id="phone" placeholder="Numéro de téléphone" value="0341234567">
  <p id="dynamic">Pas encore de compte ?</p>
  <div id="ai-output" data-rendu>Tableau de bord \\frac{1}{2}</div>
  <pre id="code-sample">Créer mon compte</pre>
</body></html>`, { url: 'http://localhost/', runScripts: 'outside-only' });
const { window } = dom;
window.localStorage.setItem('mahay-langue', 'mg');
vm.runInNewContext(source, { window, document: window.document }, { filename: 'langue.js' });
window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
await new Promise((resolve) => setTimeout(resolve, 0));

const select = window.document.querySelector('#select-langue');
const lang = window.document.documentElement.getAttribute('lang');
if (lang !== 'mg' || select.value !== 'mg') throw new Error('Saved language preference was not restored');
if (window.document.querySelector('#navigation').textContent !== 'Fijerena ankapobeny') {
  throw new Error('Navigation did not switch to Malagasy');
}
if (window.document.querySelector('#phone').getAttribute('placeholder') !== 'Laharana finday') {
  throw new Error('Input placeholder did not switch to Malagasy');
}
if (window.document.querySelector('#dynamic').textContent !== 'Tsy mbola manana kaonty?') {
  throw new Error('Dynamic or existing page text was not translated');
}
if (window.document.querySelector('#ai-output').textContent !== 'Tableau de bord \\frac{1}{2}') {
  throw new Error('AI output must remain untouched by interface translation');
}
if (window.document.querySelector('#code-sample').textContent !== 'Créer mon compte') {
  throw new Error('Code samples must remain untouched');
}

const added = window.document.createElement('p');
added.textContent = 'Créer mon compte';
window.document.body.appendChild(added);
await new Promise((resolve) => setTimeout(resolve, 0));
if (added.textContent !== 'Hamorona kaonty') throw new Error('Dynamically inserted labels are not translated');

select.value = 'fr';
select.dispatchEvent(new window.Event('change', { bubbles: true }));
if (window.document.documentElement.getAttribute('lang') !== 'fr') throw new Error('HTML lang was not restored');
if (window.document.querySelector('#navigation').textContent !== 'Tableau de bord') {
  throw new Error('Switching back to French did not restore the original source');
}
if (window.localStorage.getItem('mahay-langue') !== 'fr') throw new Error('Language preference was not persisted');
console.log(JSON.stringify({ ok: true, locales: ['fr', 'mg'], dynamic: true, ai_content_protected: true }));
