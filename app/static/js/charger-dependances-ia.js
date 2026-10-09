/* Repli des dépendances du rendu IA si le CDN principal échoue.
   Les versions sont épinglées et aucun contenu étudiant n'est envoyé à ces CDNs. */
(function (window, document) {
  "use strict";
  var secours = "https://unpkg.com/";
  var urls = {
    css: secours + "katex@0.16.11/dist/katex.min.css",
    katex: secours + "katex@0.16.11/dist/katex.min.js",
    mhchem: secours + "katex@0.16.11/dist/contrib/mhchem.min.js",
    marked: secours + "marked@12.0.2/marked.min.js",
    purify: secours + "dompurify@3.1.6/dist/purify.min.js",
    highlight: secours + "highlight.js@11.10.0/build/highlight.min.js"
  };
  var promesseChargement = null;
  function fonctionExiste(objet, nom) { return Boolean(objet && typeof objet[nom] === "function"); }
  function katexDisponible() { return fonctionExiste(window.katex, "render"); }
  function markedDisponible() { return fonctionExiste(window.marked, "parse"); }
  function purifyDisponible() { return fonctionExiste(window.DOMPurify, "sanitize"); }
  function highlightDisponible() { return fonctionExiste(window.hljs, "highlightElement"); }

  function mhchemDisponible() {
    if (!katexDisponible()) return false;
    var test = document.createElement("span");
    try {
      window.katex.render("\\ce{H2O}", test, { throwOnError: false, strict: "ignore" });
      return !test.querySelector(".katex-error") && Boolean(test.querySelector(".katex"));
    } catch (_) { return false; }
  }

  function feuilleKatexDisponible() {
    try {
      return Array.prototype.some.call(document.styleSheets, function (feuille) {
        return Boolean(feuille.href && feuille.href.indexOf("katex.min.css") !== -1);
      });
    } catch (_) { return false; }
  }

  function chargerScript(url, disponible) {
    if (disponible()) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var script = document.createElement("script");
      var termine = false;
      function finir(ok) {
        if (termine) return;
        termine = true;
        script.onload = null;
        script.onerror = null;
        resolve(Boolean(ok && disponible()));
      }
      script.src = url;
      script.async = false;
      script.onload = function () { finir(true); };
      script.onerror = function () { finir(false); };
      document.head.appendChild(script);
    });
  }

  function chargerFeuilleKatex() {
    if (feuilleKatexDisponible()) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var feuille = document.createElement("link");
      var termine = false;
      function finir(ok) {
        if (termine) return;
        termine = true;
        feuille.onload = null;
        feuille.onerror = null;
        resolve(Boolean(ok));
      }
      feuille.rel = "stylesheet";
      feuille.href = urls.css;
      feuille.onload = function () { finir(true); };
      feuille.onerror = function () { finir(false); };
      document.head.appendChild(feuille);
    });
  }

  async function executerRepli() {
    var etat = {};
    etat.css = await chargerFeuilleKatex();
    etat.katex = await chargerScript(urls.katex, katexDisponible);
    etat.mhchem = katexDisponible()
      ? (mhchemDisponible() || await chargerScript(urls.mhchem, mhchemDisponible))
      : false;
    etat.marked = await chargerScript(urls.marked, markedDisponible);
    etat.purify = await chargerScript(urls.purify, purifyDisponible);
    etat.highlight = await chargerScript(urls.highlight, highlightDisponible);
    if (!etat.katex || !etat.mhchem || !etat.marked || !etat.purify) {
      console.warn("[Gasy Mahay] Le CDN principal et au moins un repli IA sont indisponibles. Le rendu sûr en texte reste actif.");
    }
    return etat;
  }

  window.GasyMahay = window.GasyMahay || {};
  window.GasyMahay.chargerDependancesRenduIA = function () {
    if (!promesseChargement) {
      promesseChargement = executerRepli().catch(function () {
        console.warn("[Gasy Mahay] Le repli des dépendances IA n'a pas pu être terminé.");
        return { css: false, katex: katexDisponible(), mhchem: mhchemDisponible(), marked: markedDisponible(), purify: purifyDisponible(), highlight: highlightDisponible() };
      });
    }
    return promesseChargement;
  };
  window.GasyMahay.chargerDependancesRenduIA();
})(window, document);
