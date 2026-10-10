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

// Check that the common student workflows switch language, including dynamic
// counters, and that returning to French restores the exact original strings.
const parcours = window.document.createElement('section');
parcours.innerHTML = `
  <h2 id="routine">Ta routine du jour</h2>
  <button id="illusion">Déconstruire avec le Tuteur IA</button>
  <p id="notice">Aucune notification à afficher pour le moment.</p>
  <span id="bonjour">Bonjour, Rakoto 👋</span>
  <span id="compteur">1/3 aujourd'hui</span>
`;
window.document.body.appendChild(parcours);
await new Promise((resolve) => setTimeout(resolve, 0));
if (window.document.querySelector('#routine').textContent !== 'Ny fandaharam-pianaranao anio') {
  throw new Error('Dashboard routine label did not switch to Malagasy');
}
if (window.document.querySelector("#illusion").textContent !== "Handinika miaraka amin'ny Mpampianatra IA") {
  throw new Error('Tutor action did not switch to Malagasy');
}
if (window.document.querySelector("#notice").textContent !== "Tsy misy fampandrenesana aseho amin'izao fotoana izao.") {
  throw new Error('Notification empty state did not switch to Malagasy');
}
if (window.document.querySelector('#bonjour').textContent !== 'Manao ahoana, Rakoto 👋') {
  throw new Error('Dynamic greeting did not preserve the student name');
}
if (window.document.querySelector('#compteur').textContent !== '1/3 androany') {
  throw new Error('Dynamic counter did not switch to Malagasy');
}

// Vérifie que la langue couvre aussi le contenu central, et pas seulement la barre latérale.
const abonnement = window.document.createElement('section');
abonnement.innerHTML = `
  <span id="premium-kicker">Accès Premium · étudiant</span>
  <h1 id="subscription-title">Ton abonnement, ton état d'accès, ton prochain pas.</h1>
  <p id="subscription-copy">Visualise ton essai, ton abonnement actuel et envoie une demande de paiement depuis un espace unique.</p>
  <span id="premium-counter"><strong>5</strong><span> jours Premium restants</span></span>
  <span id="ia-counter"><strong>5</strong><span> jours d'IA restants</span></span>
  <span id="access-state">état actuel de l'accès</span>
  <p id="premium-sentence"><span>Il te reste </span><strong>5</strong><span> d'accès Premium.</span></p>
  <h2 id="security-heading">Compte · sécurité &amp; profil</h2>
  <p id="help-heading">Trouver une réponse sans parcourir tout le site.</p>
`;
window.document.body.appendChild(abonnement);
await new Promise((resolve) => setTimeout(resolve, 0));
if (window.document.querySelector('#premium-kicker').textContent !== 'Fidirana Premium · mpianatra') {
  throw new Error('Subscription page kicker did not switch to Malagasy');
}
if (window.document.querySelector('#subscription-title').textContent !== "Ny famandrihanao, ny satan'ny fidiranao ary ny dingana manaraka.") {
  throw new Error('Main subscription heading did not switch to Malagasy');
}
if (!window.document.querySelector('#subscription-copy').textContent.includes('Jereo eto')) {
  throw new Error('Main subscription description did not switch to Malagasy');
}
if (window.document.querySelector('#premium-counter').textContent !== '5 andro Premium sisa') {
  throw new Error('Premium day counter was not translated or spacing was lost');
}
if (window.document.querySelector('#ia-counter').textContent !== '5 andro sisa ahafahana mampiasa ny IA') {
  throw new Error('AI day counter did not switch to Malagasy');
}
if (window.document.querySelector('#premium-sentence').textContent !== "Mbola manana 5 andro ahafahana miditra amin'ny Premium.") {
  throw new Error('Dynamic sentence did not preserve spaces around inserted values');
}
if (window.document.querySelector('#security-heading').textContent !== 'Kaonty · fiarovana sy mombamomba') {
  throw new Error('Security page heading did not switch to Malagasy');
}
if (window.document.querySelector('#help-heading').textContent !== 'Mitadiava valiny nefa tsy mila mijery ny tranonkala manontolo.') {
  throw new Error('Help page content did not switch to Malagasy');
}

// Les modifications de texte en place doivent être retraduites et réversibles.
const mutable = window.document.createElement('p');
mutable.appendChild(window.document.createTextNode('Aucun document trouvé.'));
window.document.body.appendChild(mutable);
await new Promise((resolve) => setTimeout(resolve, 0));
if (mutable.textContent !== 'Tsy nahitana tahirin-kevitra.') {
  throw new Error('Inserted dynamic text was not translated');
}
mutable.firstChild.nodeValue = 'Déposer un document';
await new Promise((resolve) => setTimeout(resolve, 0));
if (mutable.textContent !== 'Handefa tahirin-kevitra') {
  throw new Error('In-place text mutation was not translated');
}

select.value = 'fr';
select.dispatchEvent(new window.Event('change', { bubbles: true }));
if (window.document.documentElement.getAttribute('lang') !== 'fr') throw new Error('HTML lang was not restored');
if (window.document.querySelector('#navigation').textContent !== 'Tableau de bord') {
  throw new Error('Switching back to French did not restore the original source');
}
if (window.document.querySelector('#routine').textContent !== 'Ta routine du jour') {
  throw new Error('Switching back to French did not restore dashboard labels');
}
if (window.document.querySelector('#bonjour').textContent !== 'Bonjour, Rakoto 👋') {
  throw new Error('Switching back to French did not restore the dynamic greeting');
}
if (window.localStorage.getItem('mahay-langue') !== 'fr') throw new Error('Language preference was not persisted');
console.log(JSON.stringify({ ok: true, locales: ['fr', 'mg'], dynamic: true, ai_content_protected: true }));
