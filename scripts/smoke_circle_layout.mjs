import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const root = process.cwd();
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const template = read("app/templates/cercle_chat.html");
const inline = template.match(/<style\b[^>]*>([\s\S]*?)<\/style>/i)?.[1];
if (!inline) throw new Error("Could not locate the circle page inline stylesheet.");
const cssFiles = [
  "app/static/style.css", "app/static/ux.css", "app/static/refonte.css",
  "app/static/csp-utilities.css", "app/static/activite.css",
  "app/static/sidebar.css", "app/static/responsive.css", "app/static/activation.css"
];
const styles = cssFiles.map((p) => "<style>" + read(p).replace(/<\/style/gi, "<\\/style") + "</style>").join("")
  + "<style>" + inline.replace(/<\/style/gi, "<\\/style") + "</style>";

function fixture(empty, theme) {
  const content = empty
    ? '<div id="etat-vide-chat" class="etat-vide-chat"><div class="etat-vide-chat-icone">💬</div><span class="etat-vide-chat-kicker">ESPACE DE DISCUSSION</span><strong class="etat-vide-chat-titre">Commencez la conversation</strong><p class="etat-vide-chat-texte">Posez une question, partagez une méthode de révision ou lancez simplement la discussion avec votre cercle.</p><div class="etat-vide-chat-actions"><button class="etat-vide-chat-action">Poser une question</button><button class="etat-vide-chat-action">Lancer une révision</button><button class="etat-vide-chat-action">Partager une idée</button></div><span class="etat-vide-chat-hint">Entrée pour envoyer · Maj+Entrée pour écrire sur plusieurs lignes</span></div>'
    : '<div class="message" data-message-id="1"><span class="message-avatar">A</span><div class="message-corps"><div class="message-entete"><span class="message-auteur">Étudiant</span><span class="message-heure">20:10</span></div><span class="message-contenu">' + "Lien et message long ".repeat(32) + '</span></div></div>';
  return [
    '<!doctype html><html lang="fr" data-theme="', theme, '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">', styles, '</head><body>',
    '<div class="app-mise-en-page"><aside class="tb-sidebar"><div class="tb-sidebar-marque"><a><span class="tb-sidebar-logo">Gasy Mahay</span></a><button class="tb-sidebar-collapse">‹</button></div><nav class="tb-sidebar-nav"><a class="tb-sidebar-lien">Tableau de bord</a><a class="tb-sidebar-lien">Documents</a><a class="tb-sidebar-lien">Quiz IA</a><a class="tb-sidebar-lien">Mes cercles</a></nav><section class="tb-sidebar-langue"><label for="langue">Langue</label><select id="langue"><option>Français</option></select></section></aside>',
    '<div class="app-page"><header class="mobile-entete-app"><span class="mobile-entete-app-marque">Gasy Mahay</span></header><main class="main-clair main-clair-pleine-largeur" data-page="/cercles/1"><div class="contenu-clair">',
    '<p class="eyebrow"><a href="/cercles">← Cercles d’étude</a></p><div class="entete-cercle"><div class="entete-cercle-identite"><span class="entete-cercle-icone">◎</span><div class="entete-cercle-infos">',
    '<h2 class="entete-cercle-titre">Finance et comptabilité — groupe de révision très long pour vérifier les retours à la ligne</h2><div class="cercle-entete-meta"><span class="cercle-entete-meta-item">Gestion</span><span class="cercle-entete-meta-item">Finance et comptabilité</span><span class="cercle-entete-meta-item">Licence 3</span></div><p class="entete-cercle-sous-titre">● En ligne : <span id="liste-presence">3 membres</span></p>',
    '</div></div><div class="entete-cercle-actions"><a href="#" class="bouton-icone-cercle" aria-label="Rechercher dans l’historique">⌕</a><a href="#" class="bouton-icone-cercle" aria-label="Documents du cercle">▤</a><a href="#" class="bouton-icone-cercle" aria-label="Voir les membres">♙</a><div class="menu-options-cercle"><button class="bouton-icone-cercle" aria-label="Options du cercle">⋯</button></div></div></div>',
    '<div class="disposition-chat"><div class="colonne-conversation"><div id="fenetre-chat" class="fenetre-chat', empty ? ' fenetre-chat-vide' : '', '">', content, '</div><div class="barre-composition">',
    '<form id="form-fichier"><label for="fichier-pdf" class="bouton-icone-cercle" aria-label="Partager un PDF" title="Partager un PDF">＋</label><input type="file" id="fichier-pdf" class="champ-fichier-cache"><button type="submit" class="bouton-envoyer-fichier">Envoyer</button></form>',
    '<div class="conteneur-emoji-picker"><button id="bouton-emoji-toggle" class="bouton-emoji-toggle" aria-label="Emojis">☺</button><div id="panneau-emojis" class="panneau-emojis-v2" hidden><strong>Emojis</strong><input aria-label="Rechercher un emoji"><div class="grille-emojis-v2">😀 👍 📚</div></div></div>',
    '<form id="form-chat"><div class="conteneur-mentions-suggestions"><textarea id="champ-message" class="cercle-chat-textarea" aria-label="Message" placeholder="Écrire un message… (@ pour mentionner, / pour les raccourcis)" rows="1"></textarea><div class="liste-suggestions-mentions" hidden></div></div><button type="submit" class="bouton-envoyer-message" aria-label="Envoyer le message">➤</button></form>',
    '<div class="cercle-chat-indicateurs"><span>Entrée = envoyer · Maj+Entrée = nouvelle ligne</span><span>0/2000</span></div><div class="cercle-chat-outils" aria-label="Outils du cercle"><button class="outil-cercle" id="bouton-commande-cercle" aria-label="Raccourcis de message">⚡ <span class="texte-option">Raccourcis</span></button><button class="outil-cercle" id="bouton-focus-cercle" aria-label="Mode Focus" aria-pressed="false">🎯 <span class="texte-option">Focus</span></button><button class="outil-cercle" id="bouton-compact-cercle">📐 <span class="texte-option">Compact</span></button><button class="outil-cercle" id="bouton-plein-ecran-cercle">⛶ <span class="texte-option">Plein écran</span></button></div>',
    '<div id="commandes-cercle" class="cercle-commandes" hidden><button class="cercle-commande">Question</button><button class="cercle-commande">Révision</button><button class="cercle-commande">Idée</button></div></div></div>',
    '<div id="panneau-thread" class="panneau-thread" hidden><div class="entete-panneau-thread"><h3>Fil de discussion</h3><button class="bouton-fermer-thread" aria-label="Fermer">✕</button></div><div class="corps-panneau-thread">Contenu du fil de discussion</div></div>',
    '</div></div></main><footer class="pied">Mahay · Aide et contact</footer></div></div></body></html>'
  ].join("");
}

const widths = [360, 390, 430, 768, 1024, 1440];
const browser = await chromium.launch({ headless: true });
const failures = [];
let states = 0;
try {
  const page = await browser.newPage();
  for (const width of widths) {
    const height = width <= 430 ? 800 : (width === 768 ? 900 : 960);
    for (const theme of ["clair", "sombre"]) {
      for (const empty of [true, false]) {
        states += 1;
        await page.setViewportSize({ width, height });
        await page.setContent(fixture(empty, theme), { waitUntil: "domcontentloaded" });
        const m = await page.evaluate(() => {
          const rect = (s) => { const e=document.querySelector(s); if(!e||e.hidden)return null; const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; };
          const chat=document.querySelector("#fenetre-chat"), composer=document.querySelector(".barre-composition");
          const header=document.querySelector(".entete-cercle-actions");
          return {
            viewport:innerWidth, rootWidth:document.documentElement.scrollWidth, bodyWidth:document.body.scrollWidth,
            main:rect("main"), header:rect(".entete-cercle-actions"), chat:rect("#fenetre-chat"),
            chatClient:chat.clientWidth, chatScroll:chat.scrollWidth, composer:rect(".barre-composition"),
            composerClient:composer.clientWidth, composerScroll:composer.scrollWidth,
            send:rect(".bouton-envoyer-message"), fileLabel:rect('label[for="fichier-pdf"]'),
            fileFallback:rect(".bouton-envoyer-fichier"),
            actions:Array.from(header.querySelectorAll("a,button")).map(e=>{const r=e.getBoundingClientRect();return {width:r.width,height:r.height,right:r.right};})
          };
        });
        if (m.rootWidth > width+1 || m.bodyWidth > width+1) failures.push("Document overflow "+width+"/"+theme+"/empty="+empty+" root="+m.rootWidth+" body="+m.bodyWidth);
        if (!m.main || m.main.x < -1 || m.main.right > width+1) failures.push("Main out of viewport "+width+"/"+theme);
        if (!m.chat || m.chat.x < -1 || m.chat.right > width+1) failures.push("Chat out of viewport "+width+"/"+theme);
        if (!m.composer || m.composer.x < -1 || m.composer.right > width+1 || m.composerScroll > m.composerClient+1) failures.push("Composer overflow "+width+"/"+theme+" "+JSON.stringify(m.composer));
        if (m.chatScroll > m.chatClient+2) failures.push("Conversation horizontal overflow "+width+"/"+theme);
        if (width <= 700) {
          if (!m.send || m.send.width < 43 || m.send.height < 43) failures.push("Send target <44px at "+width);
          if (!m.fileLabel || m.fileLabel.width < 43 || m.fileLabel.height < 43) failures.push("Attachment target <44px at "+width);
          if (!m.fileFallback || m.fileFallback.width < 20) failures.push("Attachment fallback hidden at "+width);
          if (m.actions.some(r=>r.width<43||r.height<43||r.right>width+1)) failures.push("Header actions too small/offscreen "+width+" "+JSON.stringify(m.actions));
        }
        if (empty && width > 700 && m.chat && m.chat.height > 410) failures.push("Empty panel too tall "+width+": "+m.chat.height);

        await page.evaluate(() => { document.querySelector("#panneau-emojis").hidden=false; document.querySelector("#commandes-cercle").hidden=false; });
        const popups=await page.evaluate(()=>["#panneau-emojis","#commandes-cercle"].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return {selector:s,x:r.x,right:r.right};}));
        if (popups.some(r=>r.x < -1 || r.right > innerWidth+1)) failures.push("Popup outside viewport "+width+"/"+theme+" "+JSON.stringify(popups));
        await page.evaluate(()=>{document.querySelector("#panneau-emojis").hidden=true;document.querySelector("#commandes-cercle").hidden=true;document.querySelector("#panneau-thread").hidden=false;});
        const thread=await page.evaluate(()=>{const r=document.querySelector("#panneau-thread").getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};});
        if(thread.x < -1 || thread.y < -1 || thread.right > width+1 || thread.bottom > height+1) failures.push("Thread panel outside viewport "+width+"/"+theme+" "+JSON.stringify(thread));
      }
    }
    await page.setViewportSize({width,height});
    await page.setContent(fixture(false,"clair"));
    await page.evaluate(()=>document.body.classList.add("cercle-mode-focus"));
    const focus=await page.locator("#bouton-focus-cercle").evaluate(e=>({display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,height:e.getBoundingClientRect().height}));
    if(focus.display==="none"||focus.visibility==="hidden"||focus.height<1) failures.push("Focus mode has no visible exit at "+width+": "+JSON.stringify(focus));
  }
} finally { await browser.close(); }
console.log(JSON.stringify({viewports:widths,states,failures},null,2));
if(failures.length) process.exit(1);
