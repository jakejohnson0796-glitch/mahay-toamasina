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
  <main id="referentiel">
    <h2 id="referentiel-heading">Referentiel academique</h2>
    <p id="referentiel-copy">Affecter les mentions aux filières et gérer les universités.</p>
    <p>Filière officielle : <span id="referentiel-value" data-no-translate>Sciences de Gestion</span></p>
  </main>
  <select id="academic-values"><option value="gestion" data-no-translate>Sciences de Gestion</option></select>
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
if (window.document.querySelector('#referentiel-heading').textContent !== 'Tahirin-kevitra fototra akademika') {
  throw new Error('Academic referential interface heading did not switch to Malagasy');
}
if (!window.document.querySelector('#referentiel-copy').textContent.startsWith('Manendry')) {
  throw new Error('Academic referential interface description did not switch to Malagasy');
}
if (window.document.querySelector('#referentiel-value').textContent !== 'Sciences de Gestion' ||
    window.document.querySelector('#academic-values').options[0].text !== 'Sciences de Gestion') {
  throw new Error('Official academic reference values must remain in French');
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
  <h2 id="premium-active">Premium actif</h2>
  <span id="active-status">Actif</span>
  <span id="singular-premium"><strong>1</strong><span> jour Premium restant</span></span>
  <span id="singular-ia"><strong>1</strong><span> jour d'IA restant</span></span>
  <p id="premium-sentence"><span>Il te reste </span><strong>5</strong><span> d'accès Premium.</span></p>
  <h2 id="security-heading">Compte · sécurité &amp; profil</h2>
  <p id="help-heading">Trouver une réponse sans parcourir tout le site.</p>
  <p id="ia-trial-alert">Le Quiz IA et le Tuteur IA sont inclus pendant les 14 premiers jours de l'essai. Le reste des fonctionnalités Premium reste accessible pendant 60 jours.</p>
  <p id="pending-subscription">La demande a bien été reçue. Ton accès Premium reste actif pendant la vérification (5 jours). L'accès IA reste ouvert pendant 4 jours.</p>
  <p id="dynamic-greeting">Bonjour, Jake</p>
  <p id="guide-copy">Ce guide te montre le chemin le plus simple dans Gasy Mahay : créer ton compte, retrouver une ressource, pratiquer, utiliser l'IA, travailler en groupe et sécuriser ton compte. Il précise aussi les durées d'accès de l'essai gratuit pour éviter toute mauvaise surprise.</p>
  <p id="circle-copy">Les cercles sont des espaces collaboratifs. L'accès dépend du cercle, du statut du compte et, selon les cas, de l'abonnement.</p>
  <p id="contact-copy">Une question, une suggestion, un partenariat ou un problème sur le site ? Écris ton message ici, puis ouvre WhatsApp en un clic — ou scanne le QR avec ton téléphone.</p>
  <p id="about-copy">Gasy Mahay rassemble ressources académiques, entraînement, entraide, accompagnement par IA et classe virtuelle dans un même environnement pensé pour les étudiants de Madagascar.</p>
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
if (window.document.querySelector('#premium-active').textContent !== 'Premium mavitrika') {
  throw new Error('Premium active state did not switch to Malagasy');
}
if (window.document.querySelector('#active-status').textContent !== 'Mavitrika') {
  throw new Error('Active badge did not switch to Malagasy');
}
if (window.document.querySelector('#singular-premium').textContent !== '1 andro Premium sisa') {
  throw new Error('Singular Premium counter did not switch to Malagasy');
}
if (window.document.querySelector('#singular-ia').textContent !== '1 andro sisa ahafahana mampiasa ny IA') {
  throw new Error('Singular AI counter did not switch to Malagasy');
}
if (window.document.querySelector('#security-heading').textContent !== 'Kaonty · fiarovana sy mombamomba') {
  throw new Error('Security page heading did not switch to Malagasy');
}
if (window.document.querySelector('#help-heading').textContent !== 'Mitadiava valiny nefa tsy mila mijery ny tranonkala manontolo.') {
  throw new Error('Help page content did not switch to Malagasy');
}
if (window.document.querySelector('#ia-trial-alert').textContent !== "Ny Quiz IA sy ny Tuteur IA dia tafiditra mandritra ny 14 andro voalohany amin'ny andrana. Mbola azo ampiasaina mandritra ny 60 andro ny fampiasa Premium hafa.") {
  throw new Error('Dynamic trial duration paragraph did not switch to Malagasy');
}
if (window.document.querySelector('#pending-subscription').textContent !== "Voaray ny fangatahanao. Mbola mavitrika mandritra ny fanamarinana (5 andro) ny fidiranao Premium. Mbola azo ampiasaina mandritra ny 4 andro ny IA.") {
  throw new Error('Dynamic subscription confirmation paragraph did not switch to Malagasy');
}
if (window.document.querySelector('#dynamic-greeting').textContent !== 'Manao ahoana, Jake') {
  throw new Error('Dynamic greeting without an emoji did not switch to Malagasy');
}
if (!window.document.querySelector('#guide-copy').textContent.startsWith('Ity torolalana ity')) {
  throw new Error('Full guide paragraph did not switch to Malagasy');
}
if (!window.document.querySelector('#circle-copy').textContent.startsWith('Sehatra iarahana miasa')) {
  throw new Error('Full circles paragraph did not switch to Malagasy');
}
if (!window.document.querySelector('#contact-copy').textContent.startsWith('Manana fanontaniana')) {
  throw new Error('Full contact paragraph did not switch to Malagasy');
}
if (!window.document.querySelector('#about-copy').textContent.startsWith('Atambatry ny Gasy Mahay')) {
  throw new Error('Full about page paragraph did not switch to Malagasy');
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
if (window.document.querySelector('#subscription-title').textContent !== "Ton abonnement, ton état d'accès, ton prochain pas.") {
  throw new Error('Returning to French did not restore the main subscription heading');
}
if (mutable.textContent !== 'Déposer un document') {
  throw new Error('Returning to French did not restore dynamically updated text');
}
console.log(JSON.stringify({ ok: true, locales: ['fr', 'mg'], dynamic: true, ai_content_protected: true }));
