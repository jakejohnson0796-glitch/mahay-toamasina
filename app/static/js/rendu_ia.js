/* Gasy Mahay — rendu sécurisé des réponses IA */
// MODIF : nouveau moteur navigateur unique pour Markdown, KaTeX, chimie,
// code et tableaux. Le texte source reste du texte brut ; seul le DOM
// final est généré après sanitization DOMPurify.

(function () {
  "use strict";

  const SELECTEUR_RENDU = "[data-rendu]";

  function verifierDependances() {
    const dependances = [
      ["marked", Boolean(window.marked)],
      ["DOMPurify", Boolean(window.DOMPurify)],
      ["KaTeX", Boolean(window.katex)],
    ];

    const manquantes = dependances
      .filter(function (item) { return !item[1]; })
      .map(function (item) { return item[0]; });

    if (manquantes.length) {
      throw new Error("Rendu IA indisponible : " + manquantes.join(", "));
    }
  }

  function parserMarkdown(brut, enLigne) {
    const texte = String(brut == null ? "" : brut);
    if (enLigne && typeof window.marked.parseInline === "function") {
      return window.marked.parseInline(texte);
    }
    return window.marked.parse(texte, {
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
    });
  }

  function fragmentSanitise(html) {
    // MODIF : DOMPurify retourne directement un fragment DOM ; le contenu IA
    // n'est donc jamais injecté brut avec innerHTML par ce module.
    return window.DOMPurify.sanitize(html, {
      RETURN_DOM_FRAGMENT: true,
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "template"],
      FORBID_ATTR: ["srcdoc"],
      ALLOW_DATA_ATTR: false,
    });
  }

  function rendreMath(element) {
    // MODIF : trust=false empêche KaTeX d'interpréter des commandes dangereuses
    // comme des extensions HTML/URL ; throwOnError=false évite qu'une formule
    // imparfaite fasse disparaître toute la réponse.
    window.katex.renderMathInElement(element, {
      delimiters: [
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
      trust: false,
      strict: "ignore",
    });
  }

  function mettreEnFormeCode(element) {
    if (!window.hljs) {
      return;
    }

    element.querySelectorAll("pre code").forEach(function (bloc) {
      // MODIF : highlight.js n'accepte ici que le nœud code déjà créé par
      // Marked + DOMPurify, jamais du texte IA injecté directement.
      try {
        window.hljs.highlightElement(bloc);
      } catch (erreur) {
        // Un langage inconnu ne doit pas casser toute la réponse.
      }
    });
  }

  function rendreReponseIA(brut, element, options) {
    const cible = element;
    const configuration = Object.assign({ enLigne: false }, options || {});

    if (!cible) {
      throw new Error("rendreReponseIA : élément cible manquant.");
    }

    verifierDependances();

    const texte = String(brut == null ? "" : brut);
    const html = parserMarkdown(texte, configuration.enLigne);
    const fragment = fragmentSanitise(html);

    // MODIF : replaceChildren remplace entièrement le contenu sans écrire la
    // chaîne IA brute dans innerHTML.
    cible.replaceChildren(fragment);

    try {
      rendreMath(cible);
    } catch (erreur) {
      // MODIF : KaTeX ne doit jamais empêcher l'affichage du Markdown déjà
      // sécurisé si une formule isolée est invalide.
      console.warn("[Gasy Mahay] rendu KaTeX partiel :", erreur);
    }

    mettreEnFormeCode(cible);
    cible.dataset.renduTraite = "1";
    return cible;
  }

  function rendreTous(parent) {
    const racine = parent || document;
    racine.querySelectorAll(SELECTEUR_RENDU).forEach(function (element) {
      // MODIF : data-rendu-ligne active automatiquement le mode inline pour
      // les choix courts des QCM, sans paragraphes parasites.
      const enLigne = element.hasAttribute("data-rendu-ligne");
      const source = element.textContent || "";
      rendreReponseIA(source, element, { enLigne: enLigne });
    });
  }

  function initialiser() {
    if (!document.querySelector(SELECTEUR_RENDU)) {
      return;
    }

    try {
      rendreTous(document);
    } catch (erreur) {
      console.error("[Gasy Mahay] impossible d'initialiser le rendu IA :", erreur);
    }
  }

  // MODIF : échantillon pratique pour les tests manuels dans la console.
  window.echantillonRenduIA = String.raw`Explique la dérivée :
\[
\frac{d}{dx}\bigl[x^{n}\bigr] = n\,x^{n-1}, \qquad n\in\mathbb{N}.
\]

En chimie : \ce{2H2 + O2 -> 2H2O}.

En informatique :
\`\`\`python
print("Bonjour Gasy Mahay")
\`\`\`
`;

  // MODIF : API publique demandée par les pages et les tests console.
  window.rendreReponseIA = rendreReponseIA;
  window.rendreTous = rendreTous;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser, { once: true });
  } else {
    initialiser();
  }
})();
