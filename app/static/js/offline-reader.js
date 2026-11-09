(function(){
"use strict";
var DB="mitaridala-offline",VERSION=1,STORE="cours";
var title=document.getElementById("offline-title"),meta=document.getElementById("offline-meta");
var status=document.getElementById("offline-status"),content=document.getElementById("offline-content");
function el(tag,cls,txt){var n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined&&txt!==null)n.textContent=String(txt);return n;}
function dateText(v){if(!v)return"";var d=new Date(v);return Number.isNaN(d.getTime())?"":new Intl.DateTimeFormat("fr-FR",{dateStyle:"medium",timeStyle:"short"}).format(d);}
function openDb(){return new Promise(function(resolve,reject){if(!("indexedDB"in window)){reject(new Error("Stockage hors connexion indisponible."));return;}
var r=indexedDB.open(DB,VERSION);r.onupgradeneeded=function(){if(!r.result.objectStoreNames.contains(STORE))r.result.createObjectStore(STORE,{keyPath:"cle"});};
r.onsuccess=function(){resolve(r.result);};r.onerror=function(){reject(r.error||new Error("Ouverture du stockage impossible."));};});}
function readPack(key){return openDb().then(function(db){return new Promise(function(resolve,reject){var tx=db.transaction(STORE,"readonly"),r=tx.objectStore(STORE).get(key);
r.onsuccess=function(){resolve(r.result||null);};r.onerror=function(){reject(r.error||new Error("Lecture impossible."));};
tx.oncomplete=function(){db.close();};tx.onerror=function(){db.close();};});});}
function deletePack(key){return openDb().then(function(db){return new Promise(function(resolve,reject){var tx=db.transaction(STORE,"readwrite");tx.objectStore(STORE).delete(key);
tx.oncomplete=function(){db.close();resolve();};tx.onerror=function(){db.close();reject(tx.error||new Error("Suppression impossible."));};});});}
function listBlock(label,items,type){
var section=el("section","offline-section");section.appendChild(el("h2","",label));
if(!items.length)section.appendChild(el("p","offline-empty","Aucun élément enregistré."));
items.forEach(function(item){var card=el("article","offline-item");card.appendChild(el("h3","",item.titre||"Sans titre"));
if(item.description)card.appendChild(el("p","",item.description));var details=[];
if(type==="seance"){if(item.statut)details.push("État : "+item.statut.replace(/_/g," "));if(item.cree_le)details.push("Créée le "+dateText(item.cree_le));}
else{if(item.date_limite)details.push("À rendre avant le "+dateText(item.date_limite));if(Number.isFinite(item.bareme))details.push("Barème : "+item.bareme+" points");if(Number.isFinite(item.coefficient))details.push("Coefficient : "+item.coefficient);if(item.periode)details.push(item.periode);if(item.clos)details.push("Devoir clôturé");}
if(details.length)card.appendChild(el("p","offline-detail",details.join(" · ")));section.appendChild(card);});
content.appendChild(section);
}
function render(pack){var course=pack.cours||{};title.textContent=course.nom||"Cours enregistré";
meta.textContent=[course.matiere,course.niveau].filter(Boolean).join(" · ");
status.textContent="Pack disponible sur cet appareil, enregistré le "+dateText(pack.enregistre_le||pack.genere_le)+".";
content.replaceChildren();var intro=el("section","offline-section");intro.appendChild(el("h2","","Présentation du cours"));
if(course.description)intro.appendChild(el("p","",course.description));
if(course.objectifs){intro.appendChild(el("h3","","Objectifs pédagogiques"));intro.appendChild(el("p","",course.objectifs));}
content.appendChild(intro);listBlock("Séances",Array.isArray(pack.seances)?pack.seances:[],"seance");
listBlock("Devoirs et consignes",Array.isArray(pack.devoirs)?pack.devoirs:[],"devoir");
if(pack.limites&&(pack.limites.seances_tronquees||pack.limites.devoirs_tronques))status.textContent+=" Certains éléments anciens ne sont pas inclus dans ce pack.";
}
var params=new URLSearchParams(window.location.hash.replace(/^#/,"")),uid=params.get("u")||"",cid=params.get("c")||"";
if(!/^\d+$/.test(uid)||!/^\d+$/.test(cid)){title.textContent="Aucun cours sélectionné";status.textContent="Ouvre un cours téléchargé depuis ton espace MITARIDALA.";return;}
readPack(uid+":"+cid).then(function(pack){if(!pack||pack.userId!==uid||String(pack.courseId)!==cid||!pack.cours){title.textContent="Cours non disponible";status.textContent="Ce cours n'a pas été téléchargé sur cet appareil ou son pack a été supprimé.";return;}
var expiration=Date.parse(pack.expires_le||"");if(!Number.isFinite(expiration)||expiration<=Date.now()){deletePack(uid+":"+cid).catch(function(){});title.textContent="Pack expiré";status.textContent="Ce téléchargement a expiré après sept jours. Reconnecte-toi pour le renouveler.";return;}render(pack);})
.catch(function(error){title.textContent="Stockage indisponible";status.textContent=error&&error.message?error.message:"Impossible de lire le cours.";});
})();
