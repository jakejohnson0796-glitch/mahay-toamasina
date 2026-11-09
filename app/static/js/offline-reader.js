(function () {
  "use strict";
  var DB_NAME = "mitaridala-offline", DB_VERSION = 1, STORE = "cours";
  var title = document.getElementById("offline-title");
  var meta = document.getElementById("offline-meta");
  var status = document.getElementById("offline-status");
  var content = document.getElementById("offline-content");

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function dateText(value) {
    if (!value) return "";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("fr-FR", {dateStyle: "medium", timeStyle: "short"}).format(date);
  }
  function libraryLink() {
    var link = el("a", "offline-library-link", "← Mes cours hors connexion");
    link.href = "/static/offline.html";
    return link;
  }
  function openDb() {
    return new Promise(function (resolve, reject) {
      if (!("indexedDB" in window)) {
        reject(new Error("Stockage hors connexion indisponible."));
        return;
      }
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = function () {
        if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, {keyPath: "cle"});
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error("Ouverture du stockage impossible.")); };
    });
  }
  function readPack(key) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly"), request = tx.objectStore(STORE).get(key);
        request.onsuccess = function () { resolve(request.result || null); };
        request.onerror = function () { reject(request.error || new Error("Lecture impossible.")); };
        tx.oncomplete = function () { db.close(); };
        tx.onerror = function () { db.close(); };
      });
    });
  }
  function readAllPacks() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly"), request = tx.objectStore(STORE).getAll();
        request.onsuccess = function () { resolve(request.result || []); };
        request.onerror = function () { reject(request.error || new Error("Lecture des cours impossible.")); };
        tx.oncomplete = function () { db.close(); };
        tx.onerror = function () { db.close(); };
      });
    });
  }
  function deletePack(key) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = function () { db.close(); resolve(); };
        tx.onerror = function () { db.close(); reject(tx.error || new Error("Suppression impossible.")); };
      });
    });
  }
  function listBlock(label, items, type) {
    var section = el("section", "offline-section");
    section.appendChild(el("h2", "", label));
    if (!items.length) section.appendChild(el("p", "offline-empty", "Aucun élément enregistré."));
    items.forEach(function (item) {
      var card = el("article", "offline-item");
      card.appendChild(el("h3", "", item.titre || "Sans titre"));
      if (item.description) card.appendChild(el("p", "", item.description));
      var details = [];
      if (type === "seance") {
        if (item.statut) details.push("État : " + item.statut.replace(/_/g, " "));
        if (item.cree_le) details.push("Créée le " + dateText(item.cree_le));
      } else {
        if (item.date_limite) details.push("À rendre avant le " + dateText(item.date_limite));
        if (Number.isFinite(item.bareme)) details.push("Barème : " + item.bareme + " points");
        if (Number.isFinite(item.coefficient)) details.push("Coefficient : " + item.coefficient);
        if (item.periode) details.push(item.periode);
        if (item.clos) details.push("Devoir clôturé");
      }
      if (details.length) card.appendChild(el("p", "offline-detail", details.join(" · ")));
      section.appendChild(card);
    });
    content.appendChild(section);
  }
  function renderCourse(pack) {
    var course = pack.cours || {};
    title.textContent = course.nom || "Cours enregistré";
    meta.textContent = [course.matiere, course.niveau].filter(Boolean).join(" · ");
    status.textContent = "Pack enregistré le " + dateText(pack.enregistre_le) + " · expiration le " + dateText(pack.expires_le) + ".";
    content.replaceChildren();
    content.appendChild(libraryLink());
    var intro = el("section", "offline-section");
    intro.appendChild(el("h2", "", "Présentation du cours"));
    if (course.description) intro.appendChild(el("p", "", course.description));
    if (course.objectifs) {
      intro.appendChild(el("h3", "", "Objectifs pédagogiques"));
      intro.appendChild(el("p", "", course.objectifs));
    }
    content.appendChild(intro);
    listBlock("Séances", Array.isArray(pack.seances) ? pack.seances : [], "seance");
    listBlock("Devoirs et consignes", Array.isArray(pack.devoirs) ? pack.devoirs : [], "devoir");
    if (pack.limites && (pack.limites.seances_tronquees || pack.limites.devoirs_tronques)) {
      status.textContent += " Certains éléments anciens ne sont pas inclus.";
    }
  }
  function renderLibrary(userId) {
    title.textContent = "Mes cours téléchargés";
    meta.textContent = "Bibliothèque locale · lecture seule";
    content.replaceChildren();
    readAllPacks().then(function (packs) {
      var now = Date.now(), valid = [], expired = [];
      packs.forEach(function (pack) {
        if (!pack || pack.userId !== userId) return;
        var expiry = Date.parse(pack.expires_le || "");
        if (!Number.isFinite(expiry) || expiry <= now) expired.push(pack.cle);
        else valid.push(pack);
      });
      expired.forEach(function (key) { deletePack(key).catch(function () {}); });
      valid.sort(function (a, b) { return Date.parse(b.enregistre_le || 0) - Date.parse(a.enregistre_le || 0); });
      if (!valid.length) {
        status.textContent = expired.length
          ? "Tes téléchargements ont expiré. Reconnecte-toi pour les renouveler."
          : "Aucun cours enregistré. Connecte-toi, ouvre un cours et choisis « Enregistrer pour le hors connexion ».";
        return;
      }
      status.textContent = valid.length + " cours disponible(s) hors connexion. Les packs expirent après sept jours.";
      valid.forEach(function (pack) {
        var card = el("article", "offline-section offline-course-card"), course = pack.cours || {};
        card.appendChild(el("h2", "", course.nom || "Cours sans titre"));
        card.appendChild(el("p", "offline-detail", [course.matiere, course.niveau].filter(Boolean).join(" · ")));
        card.appendChild(el("p", "offline-detail", "Enregistré le " + dateText(pack.enregistre_le) + " · expiration le " + dateText(pack.expires_le)));
        var link = el("a", "offline-open-link", "Ouvrir le cours");
        link.href = "/static/offline.html#u=" + encodeURIComponent(userId) + "&c=" + encodeURIComponent(pack.courseId);
        card.appendChild(link);
        content.appendChild(card);
      });
    }).catch(function (error) {
      status.textContent = error && error.message ? error.message : "Impossible de lire les cours enregistrés.";
    });
  }

  var params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  var userId = params.get("u") || "", courseId = params.get("c") || "";
  if (userId && courseId && /^\d+$/.test(userId) && /^\d+$/.test(courseId)) {
    readPack(userId + ":" + courseId).then(function (pack) {
      if (!pack || pack.userId !== userId || String(pack.courseId) !== courseId || !pack.cours) {
        title.textContent = "Cours non disponible";
        status.textContent = "Ce cours n'a pas été téléchargé sur cet appareil ou son pack a été supprimé.";
        content.appendChild(libraryLink());
        return;
      }
      var expiry = Date.parse(pack.expires_le || "");
      if (!Number.isFinite(expiry) || expiry <= Date.now()) {
        deletePack(userId + ":" + courseId).catch(function () {});
        title.textContent = "Pack expiré";
        status.textContent = "Ce téléchargement a expiré après sept jours. Reconnecte-toi pour le renouveler.";
        content.appendChild(libraryLink());
        return;
      }
      renderCourse(pack);
    }).catch(function (error) {
      title.textContent = "Stockage indisponible";
      status.textContent = error && error.message ? error.message : "Impossible de lire le cours.";
    });
  } else {
    var lastUser = "";
    try { lastUser = localStorage.getItem("mitaridala:offline:last-user") || ""; } catch (_) {}
    if (!/^\d+$/.test(lastUser)) {
      title.textContent = "Bibliothèque hors connexion";
      status.textContent = "Aucun compte récent n'est disponible sur cet appareil. Reconnecte-toi, puis enregistre tes cours.";
    } else {
      renderLibrary(lastUser);
    }
  }
})();
