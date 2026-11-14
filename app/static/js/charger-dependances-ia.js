/* Chargement borné des dépendances IA locales.
   Les bibliothèques sont vérifiées par SHA-512 pendant le build ; aucun CDN
   JavaScript externe n'est contacté pendant l'exécution du site. */
(function (window, document) {
  "use strict";

  var DELAI_MAX_MS = 2500;
  var local = "/static/vendor/";
  var versionsLocales = { katex: "0.19.1", marked: "18.1.1", purify: "3.4.17", highlight: "11.12.0" };
  var ressources = {
    css: [local + "katex/katex.min.css?v=" + versionsLocales.katex],
    katex: [local + "katex/katex.min.js?v=" + versionsLocales.katex],
    mhchem: [local + "katex/contrib/mhchem.min.js?v=" + versionsLocales.katex],
    marked: [local + "marked/marked.min.js?v=" + versionsLocales.marked],
    purify: [local + "dompurify/purify.min.js?v=" + versionsLocales.purify],
    highlight: [local + "highlightjs/highlight.min.js?v=" + versionsLocales.highlight]
  };

  var promesseChargement = null;
  function fonctionExiste(objet, nom) {
    return Boolean(objet && typeof objet[nom] === "function");
  }
  function katexDisponible() {
    return fonctionExiste(window.katex, "render");
  }
  function markedDisponible() {
    return fonctionExiste(window.marked, "parse");
  }
  function purifyDisponible() {
    return fonctionExiste(window.DOMPurify, "sanitize");
  }
  function highlightDisponible() {
    return fonctionExiste(window.hljs, "highlightElement");
  }
  function mhchemDisponible() {
    if (!katexDisponible()) return false;
    var test = document.createElement("span");
    try {
      window.katex.render("\\ce{H2O}", test, { throwOnError: false, strict: "ignore" });
      return !test.querySelector(".katex-error") && Boolean(test.querySelector(".katex"));
    } catch (_) {
      return false;
    }
  }
  function cssDisponible() {
    return Array.prototype.some.call(document.querySelectorAll('link[rel="stylesheet"]'), function (feuille) {
      return Boolean(feuille.href && feuille.href.indexOf("katex.min.css") !== -1 && feuille.dataset.gmKatexCharge === "ok");
    });
  }

  function chargerScript(url, disponible) {
    if (disponible()) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var script = document.createElement("script");
      var termine = false;
      var minuteur = window.setTimeout(function () { finir(false); }, DELAI_MAX_MS);

      function finir(ok) {
        if (termine) return;
        termine = true;
        window.clearTimeout(minuteur);
        script.onload = null;
        script.onerror = null;
        if (!ok && script.parentNode) script.parentNode.removeChild(script);
        resolve(Boolean(ok && disponible()));
      }

      // Propager le nonce aux scripts dynamiques pour la CSP stricte.
      var scriptAutorise = document.querySelector("script[nonce]");
      if (scriptAutorise) script.nonce = scriptAutorise.nonce;
      script.src = url;
      script.async = true;
      script.onload = function () { finir(true); };
      script.onerror = function () { finir(false); };
      document.head.appendChild(script);
    });
  }

  function chargerCSS(url) {
    if (cssDisponible()) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var feuille = document.createElement("link");
      var termine = false;
      var minuteur = window.setTimeout(function () { finir(false); }, DELAI_MAX_MS);

      function finir(ok) {
        if (termine) return;
        termine = true;
        window.clearTimeout(minuteur);
        feuille.onload = null;
        feuille.onerror = null;
        if (ok) {
          feuille.dataset.gmKatexCharge = "ok";
        } else if (feuille.parentNode) {
          feuille.parentNode.removeChild(feuille);
        }
        resolve(Boolean(ok));
      }

      feuille.rel = "stylesheet";
      feuille.href = url;
      feuille.onload = function () { finir(true); };
      feuille.onerror = function () { finir(false); };
      document.head.appendChild(feuille);
    });
  }

  async function avecSecours(nom, disponible, chargeur) {
    if (disponible()) return true;
    var liste = ressources[nom];
    for (var i = 0; i < liste.length; i += 1) {
      try {
        if (await chargeur(liste[i], disponible)) return true;
      } catch (_) {
        // Une origine externe ne doit jamais interrompre le reste de la page.
      }
    }
    return Boolean(disponible());
  }

  async function executerChargement() {
    // Les éléments indépendants sont essayés en parallèle. mhchem attend KaTeX.
    var resultats = await Promise.all([
      avecSecours("css", cssDisponible, function (url) { return chargerCSS(url); }),
      avecSecours("katex", katexDisponible, chargerScript),
      avecSecours("marked", markedDisponible, chargerScript),
      avecSecours("purify", purifyDisponible, chargerScript),
      avecSecours("highlight", highlightDisponible, chargerScript)
    ]);

    var etat = {
      css: resultats[0],
      katex: resultats[1],
      marked: resultats[2],
      purify: resultats[3],
      highlight: resultats[4],
      mhchem: false
    };
    if (etat.katex) {
      etat.mhchem = await avecSecours("mhchem", mhchemDisponible, chargerScript);
    }

    if (!etat.css || !etat.katex || !etat.mhchem || !etat.marked || !etat.purify) {
      console.warn("[MITARIDALA] Les dépendances IA sont indisponibles ou incomplètes. Vérifier notamment la feuille CSS KaTeX, indispensable à la mise en page des formules.", {
        css: etat.css,
        katex: etat.katex,
        mhchem: etat.mhchem,
        marked: etat.marked,
        purify: etat.purify
      });
    }
    return etat;
  }

  window.GasyMahay = window.GasyMahay || {};
  window.GasyMahay.chargerDependancesRenduIA = function () {
    if (!promesseChargement) {
      promesseChargement = executerChargement()
        .catch(function () {
          console.warn("[MITARIDALA] Le chargement des dépendances IA a échoué ; le texte reste accessible.");
          return {
            css: cssDisponible(),
            katex: katexDisponible(),
            mhchem: mhchemDisponible(),
            marked: markedDisponible(),
            purify: purifyDisponible(),
            highlight: highlightDisponible()
          };
        })
        .then(function (etat) {
          // Le renderer peut avoir affiché un repli texte avant la fin du
          // chargement. Repasser alors sur la source brute, notamment pour
          // les formules chimiques si mhchem est arrivé après KaTeX.
          window.GasyMahay.etatDependancesRenduIA = etat;
          if (typeof window.rendreTous === "function") {
            try { window.rendreTous(document); } catch (_) {}
          }
          return etat;
        });
    }
    return promesseChargement;
  };

  window.GasyMahay.chargerDependancesRenduIA();
})(window, document);
