// MITARIDALA — enregistrement du service worker PWA.
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function (erreur) {
      // La PWA reste facultative : une indisponibilité du service worker
      // ne doit jamais empêcher l'application principale de fonctionner.
      console.warn("[MITARIDALA] Service worker indisponible.", erreur);
    });
  });
})();
 
// Sauvegarde locale des quiz classiques pour reprendre après une coupure réseau.
(function recuperationBrouillonQuiz() {
  "use strict";
  var prefixe = "mitaridala:quiz-draft:v1:";
  var dureeMax = 7 * 24 * 60 * 60 * 1000;
  var stockage;
  try { stockage = window.localStorage; } catch (_) { return; }

  function effacerTentative(id) {
    try {
      for (var i = stockage.length - 1; i >= 0; i -= 1) {
        var cle = stockage.key(i);
        if (cle && cle.indexOf(prefixe) === 0 && cle.endsWith(":" + id)) stockage.removeItem(cle);
      }
    } catch (_) {}
  }

  var resultat = window.location.pathname.match(/^\/quiz\/(\d+)\/resultat\/?$/);
  if (resultat) { effacerTentative(resultat[1]); return; }

  var form = document.querySelector("form[data-quiz-form]");
  if (!form || form.dataset.quizAdaptatif === "1" || form.dataset.quizModeExamen === "1") return;
  var proprietaire = (form.dataset.quizOwner || "").trim();
  var tentative = (form.dataset.quizTentativeId || "").trim();
  if (!/^\d+$/.test(proprietaire) || !/^\d+$/.test(tentative)) return;

  var cle = prefixe + proprietaire + ":" + tentative;
  var statut = document.querySelector("[data-quiz-draft-status]");
  var boutonEffacer = document.querySelector("[data-quiz-draft-clear]");
  function annoncer(texte) { if (statut) statut.textContent = texte; }
  function lire() {
    var reponses = {}, confiances = {};
    form.querySelectorAll('input[type="radio"]:checked').forEach(function (input) {
      if (/^question_\d+$/.test(input.name) && /^\d+$/.test(input.value)) reponses[input.name] = input.value;
      if (/^confiance_\d+$/.test(input.name) && ["faible", "moyenne", "forte"].indexOf(input.value) !== -1) confiances[input.name] = input.value;
    });
    return { reponses: reponses, confiances: confiances };
  }
  function sauver() {
    var donnees = lire();
    if (!Object.keys(donnees.reponses).length && !Object.keys(donnees.confiances).length) {
      try { stockage.removeItem(cle); } catch (_) { return false; }
      if (boutonEffacer) boutonEffacer.hidden = true;
      return true;
    }
    try {
      stockage.setItem(cle, JSON.stringify({
        version: 1, proprietaire: proprietaire, tentative: tentative,
        enregistreLe: Date.now(), reponses: donnees.reponses, confiances: donnees.confiances
      }));
      if (boutonEffacer) boutonEffacer.hidden = false;
      return true;
    } catch (_) {
      annoncer("Le navigateur ne peut pas enregistrer ce brouillon sur cet appareil.");
      return false;
    }
  }
  function appliquer(valeurs, confiance) {
    Object.keys(valeurs || {}).forEach(function (nom) {
      var valeur = String(valeurs[nom]);
      var nomValide = confiance ? /^confiance_\d+$/.test(nom) : /^question_\d+$/.test(nom);
      var valeurValide = confiance ? ["faible", "moyenne", "forte"].indexOf(valeur) !== -1 : /^\d+$/.test(valeur);
      if (!nomValide || !valeurValide) return;
      form.querySelectorAll('input[type="radio"]').forEach(function (input) {
        if (input.name === nom && input.value === valeur) input.checked = true;
      });
    });
  }

  try {
    var brouillon = JSON.parse(stockage.getItem(cle) || "null");
    if (brouillon && brouillon.version === 1 &&
        brouillon.proprietaire === proprietaire && String(brouillon.tentative) === tentative &&
        Number.isFinite(brouillon.enregistreLe) && Date.now() - brouillon.enregistreLe <= dureeMax) {
      appliquer(brouillon.reponses, false);
      appliquer(brouillon.confiances, true);
      annoncer("Brouillon retrouvé : tes réponses ont été rétablies sur cet appareil.");
      if (boutonEffacer) boutonEffacer.hidden = false;
    } else {
      stockage.removeItem(cle);
      annoncer("Tes réponses se sauvegardent sur cet appareil.");
    }
  } catch (_) {
    try { stockage.removeItem(cle); } catch (__) {}
    annoncer("Tes réponses se sauvegardent sur cet appareil.");
  }

  form.addEventListener("change", function (event) {
    if (event.target && event.target.matches('input[type="radio"]')) {
      if (sauver()) annoncer("Brouillon enregistré sur cet appareil.");
    }
  });
  form.addEventListener("submit", function (event) {
    var brouillonEnregistre = sauver();
    if (navigator.onLine === false) {
      event.preventDefault();
      if (brouillonEnregistre) {
        annoncer("Connexion indisponible : tes réponses sont conservées sur cet appareil. Reconnecte-toi puis valide le quiz.");
      } else {
        annoncer("Connexion indisponible : le navigateur n'a pas pu enregistrer tes réponses. Ne ferme pas la page ; reconnecte-toi avant de continuer.");
      }
    }
  });
  window.addEventListener("online", function () {
    try {
      if (stockage.getItem(cle)) annoncer("Connexion rétablie : tes réponses sont prêtes. Valide le quiz pour les envoyer.");
    } catch (_) {}
  });
  if (boutonEffacer) boutonEffacer.addEventListener("click", function () {
    try { stockage.removeItem(cle); } catch (_) {}
    form.querySelectorAll('input[type="radio"]:checked').forEach(function (input) { input.checked = false; });
    boutonEffacer.hidden = true;
    annoncer("Brouillon effacé de cet appareil.");
  });
})();


// Packs de cours en lecture hors connexion, isolés par compte et effacés à la déconnexion.
(function packsCoursHorsLigne() {
  "use strict";
  var DB_NAME="mitaridala-offline", DB_VERSION=1, STORE="cours";
  var LIMITE_OCTETS=2*1024*1024, DUREE_PACK_MS=7*24*60*60*1000;

  function annoncer(carte,texte){var zone=carte.querySelector("[data-offline-status]");if(zone)zone.textContent=texte;}
  function ouvrirBase(){
    return new Promise(function(resolve,reject){
      if(!("indexedDB" in window)){reject(new Error("Le stockage hors connexion n'est pas disponible."));return;}
      var demande=indexedDB.open(DB_NAME,DB_VERSION);
      demande.onupgradeneeded=function(){var db=demande.result;if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:"cle"});};
      demande.onsuccess=function(){resolve(demande.result);};
      demande.onerror=function(){reject(demande.error||new Error("Impossible d'ouvrir le stockage local."));};
    });
  }
  function operation(mode,action){
    return ouvrirBase().then(function(db){
      return new Promise(function(resolve,reject){
        var tx=db.transaction(STORE,mode), store=tx.objectStore(STORE), result=action(store);
        tx.oncomplete=function(){db.close();resolve(result&&result.result);};
        tx.onerror=function(){db.close();reject(tx.error||new Error("Opération locale impossible."));};
        tx.onabort=function(){db.close();reject(tx.error||new Error("Opération locale annulée."));};
      });
    });
  }
  function lire(cle){
    return ouvrirBase().then(function(db){
      return new Promise(function(resolve,reject){
        var tx=db.transaction(STORE,"readonly"),req=tx.objectStore(STORE).get(cle);
        req.onsuccess=function(){resolve(req.result||null);};
        req.onerror=function(){reject(req.error||new Error("Lecture locale impossible."));};
        tx.oncomplete=function(){db.close();};
        tx.onerror=function(){db.close();};
      });
    });
  }
  function ecrire(pack){return operation("readwrite",function(store){return store.put(pack);});}
  function supprimer(cle){return operation("readwrite",function(store){return store.delete(cle);});}
  function supprimerTous(){return operation("readwrite",function(store){return store.clear();});}

  function initialiser(carte){
    var userId=(carte.dataset.userId||"").trim(), courseId=(carte.dataset.courseId||"").trim();
    var url=carte.dataset.exportUrl||"", cle=userId+":"+courseId;
    var save=carte.querySelector("[data-offline-save]"), del=carte.querySelector("[data-offline-delete]");
    var open=carte.querySelector("[data-offline-open]");
    if(!/^\d+$/.test(userId)||!/^\d+$/.test(courseId)||!save||!del||!open)return;

    function setPack(pack){
      var expiration=pack&&Date.parse(pack.expires_le||"");
      var ok=Boolean(pack&&pack.userId===userId&&String(pack.courseId)===courseId&&Number.isFinite(expiration)&&expiration>Date.now());
      open.hidden=!ok;del.hidden=!ok;
      if(ok)open.href="/static/offline.html#u="+encodeURIComponent(userId)+"&c="+encodeURIComponent(courseId);
      else if(pack)supprimer(cle).catch(function(){});
      return ok;
    }
    lire(cle).then(function(pack){
      var disponible=setPack(pack);
      annoncer(carte,disponible?"Ce cours est enregistré sur cet appareil (expiration dans 7 jours).":(pack?"Ce pack a expiré. Télécharge-le à nouveau en étant connecté.":"Aucun pack hors connexion enregistré."));
    }).catch(function(erreur){save.disabled=true;annoncer(carte,erreur.message||"Stockage local indisponible.");});

    save.addEventListener("click",function(){
      if(navigator.onLine===false){annoncer(carte,"Reconnecte-toi pour télécharger le contenu du cours.");return;}
      save.disabled=true;annoncer(carte,"Téléchargement du contenu pédagogique…");
      fetch(url,{method:"GET",credentials:"same-origin",cache:"no-store"})
        .then(function(response){
          if(!response.ok){
            if(response.status===401||response.status===403)throw new Error("Connecte-toi avec un compte autorisé à consulter ce cours.");
            throw new Error("Le serveur n'a pas pu préparer le pack.");
          }
          if((response.headers.get("content-type")||"").indexOf("application/json")===-1)throw new Error("Réponse du serveur invalide.");
          return response.json();
        })
        .then(function(data){
          if(!data||data.schema_version!==1||!data.cours||String(data.cours.id)!==courseId)throw new Error("Le contenu reçu ne correspond pas à ce cours.");
          var pack={cle:cle,userId:userId,courseId:courseId,enregistre_le:new Date().toISOString(),
            expires_le:new Date(Date.now()+DUREE_PACK_MS).toISOString(),
            cours:data.cours,seances:data.seances||[],devoirs:data.devoirs||[],limites:data.limites||{}};
          if(new TextEncoder().encode(JSON.stringify(pack)).byteLength>LIMITE_OCTETS)throw new Error("Ce pack dépasse la limite de 2 Mo.");
          return ecrire(pack).then(function(){setPack(pack);annoncer(carte,"Cours enregistré. Tu peux maintenant l'ouvrir sans connexion.");});
        })
        .catch(function(error){annoncer(carte,error&&error.message?error.message:"Téléchargement impossible.");})
        .finally(function(){save.disabled=false;});
    });
    del.addEventListener("click",function(){
      del.disabled=true;
      supprimer(cle).then(function(){setPack(null);annoncer(carte,"Téléchargement local supprimé.");})
        .catch(function(error){annoncer(carte,error.message||"Suppression impossible.");})
        .finally(function(){del.disabled=false;});
    });
  }

  function demarrer(){
    document.querySelectorAll("[data-offline-course]").forEach(initialiser);
    document.querySelectorAll('form[action="/deconnexion"]').forEach(function(form){
      form.addEventListener("submit",function(event){
        event.preventDefault();
        supprimerTous().catch(function(){}).finally(function(){form.submit();});
      });
    });
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",demarrer);else demarrer();
})();
