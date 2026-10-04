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
      ["KaTeX", Boolean(window.katex && typeof window.katex.render === "function")],
    ];

    const manquantes = dependances
      .filter(function (item) { return !item[1]; })
      .map(function (item) { return item[0]; });

    if (manquantes.length) {
      throw new Error("Rendu IA indisponible : " + manquantes.join(", "));
    }
  }

  // MODIF : Marked considère \\[ et \\( comme des échappements Markdown et
  // supprime donc le premier antislash. On protège les blocs mathématiques
  // ENTIEREMENT avant Markdown, puis on restaure leurs délimiteurs après
  // sanitization. Ainsi \\frac, \\begin, indices et underscores ne sont
  // pas interprétés comme du Markdown.
  const TOKEN_MATH = "\uE000GMATH_";
  function convertirMarqueursTransport(source) {
    const texte = String(source || "");
    return texte.replace(/\x60\x60\x60[\s\S]*?\x60\x60\x60|\x60[^\x60\n]*\x60|\[\[DISPLAY\]\]([\s\S]*?)\[\[\/DISPLAY\]\]|\[\[MATH\]\]([\s\S]*?)\[\[\/MATH\]\]|\[\[CHEM\]\]([\s\S]*?)\[\[\/CHEM\]\]/g,
      function (match, display, inline, chem) {
        if (display === undefined && inline === undefined && chem === undefined) return match;
        if (display !== undefined) return "\\[" + display + "\\]";
        if (inline !== undefined) return "\\(" + inline + "\\)";
        return "\\(\\ce{" + chem + "}\\)";
      });
  }

  function protegerMath(brut) {
    const math = [];
    const source = convertirMarqueursTransport(String(brut == null ? "" : brut));
    const protection = source.replace(
      /\x60\x60\x60[\s\S]*?\x60\x60\x60|\x60[^\x60\n]*\x60|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)/g,
      function (match) {
        if (match.indexOf("\\[") === 0 || match.indexOf("\\(") === 0) {
          const display = match.indexOf("\\[") === 0;
          const contenu = match.slice(2, -2);
          const index = math.push({ display: display, contenu: contenu }) - 1;
          return TOKEN_MATH + index + "\uE001";
        }
        return match;
      }
    );
    return { source: protection, math: math };
  }

  function restaurerMath(fragment, math) {
    if (!math.length) return;

    const racine = fragment.ownerDocument || document;
    const walker = racine.createTreeWalker(fragment, NodeFilter.SHOW_TEXT);
    const noeuds = [];
    let noeud;
    while ((noeud = walker.nextNode())) noeuds.push(noeud);

    noeuds.forEach(function (texte) {
      const valeur = texte.nodeValue || "";
      const motif = /\uE000GMATH_(\d+)\uE001/g;
      if (!motif.test(valeur)) return;
      motif.lastIndex = 0;

      const parent = texte.parentNode;
      if (!parent) return;

      const morceaux = [];
      let dernier = 0;
      let correspondance;
      while ((correspondance = motif.exec(valeur))) {
        if (correspondance.index > dernier) {
          morceaux.push(racine.createTextNode(valeur.slice(dernier, correspondance.index)));
        }

        const item = math[Number(correspondance[1])];
        if (item) {
          const cible = racine.createElement("span");
          cible.className = item.display ? "gm-katex gm-katex-display" : "gm-katex";
          try {
            window.katex.render(item.contenu, cible, {
              displayMode: Boolean(item.display),
              throwOnError: false,
              trust: false,
              strict: "ignore",
            });
            morceaux.push(cible);
          } catch (erreur) {
            // Conserve le contenu lisible plutôt que de casser tout le bloc.
            morceaux.push(
              racine.createTextNode(
                item.display
                  ? "\\[" + item.contenu + "\\]"
                  : "\\(" + item.contenu + "\\)"
              )
            );
            console.warn("[Gasy Mahay] formule KaTeX invalide :", erreur);
          }
        }
        dernier = motif.lastIndex;
      }

      if (dernier < valeur.length) {
        morceaux.push(racine.createTextNode(valeur.slice(dernier)));
      }

      morceaux.forEach(function (morceau) {
        parent.insertBefore(morceau, texte);
      });
      parent.removeChild(texte);
    });
  }

  function parserMarkdown(brut, enLigne) {
    let texte = String(brut == null ? "" : brut);

    if (enLigne) {
      texte = texte.replace(/(\d)\*(?=\d)/g, "$1\\*");
    }

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

  // MODIF : filet de sécurité pour les réponses IA qui contiennent encore
  // une commande LaTeX nue (`\\det`, `\\frac`, `\\begin{...}`, etc.) sans
  // délimiteur. Le contrat IA reste prioritaire ; ce fallback évite qu'une
  // réponse imparfaitement formatée redevienne du texte brut.
  const COMMANDES_LATEX_NUES = [
    "det", "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "lim",
    "ln", "log", "sin", "cos", "tan", "cot", "exp", "partial", "nabla",
    "vec", "mathbf", "mathbb", "mathrm", "text", "times", "cdot", "pm",
    "leq", "geq", "neq", "approx", "in", "infty", "alpha", "beta", "gamma",
    "delta", "theta", "lambda", "mu", "pi", "sigma"
  ];

  function estCommandeLatexNue(valeur) {
    return COMMANDES_LATEX_NUES.some(function (commande) {
      return new RegExp("\\\\" + commande + "\\b").test(valeur);
    }) || /\\begin\\{[A-Za-z*]+\\}/.test(valeur);
  }

  function rendreLatexNu(element) {
    const racine = element.ownerDocument || document;
    const walker = racine.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const noeuds = [];
    let noeud;
    while ((noeud = walker.nextNode())) {
      if (noeud.parentElement && /^(CODE|PRE)$/.test(noeud.parentElement.tagName)) continue;
      noeuds.push(noeud);
    }

    noeuds.forEach(function (texte) {
      const valeur = texte.nodeValue || "";
      if (!estCommandeLatexNue(valeur)) return;

      const motif = /\\(?:det|frac|dfrac|tfrac|sqrt|sum|prod|int|lim|ln|log|sin|cos|tan|cot|exp|partial|nabla|vec|mathbf|mathbb|mathrm|text|times|cdot|pm|leq|geq|neq|approx|in|infty|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma)\\b|\\begin\\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\\}/g;
      const match = motif.exec(valeur);
      if (!match) return;

      const debut = match.index;
      const avant = valeur.slice(0, debut);
      const reste = valeur.slice(debut);
      const finMatch = reste.search(/[.!?;](?:\\s|$)/);
      const fin = finMatch > 0 ? finMatch : reste.length;
      const formule = reste.slice(0, fin).trim();

      if (!formule || !estCommandeLatexNue(formule)) return;

      const morceaux = [];
      if (avant) morceaux.push(racine.createTextNode(avant));

      const cible = racine.createElement("span");
      cible.className = "gm-latex-fallback";
      try {
        window.katex.render(formule, cible, {
          displayMode: /\\begin\\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\\}/.test(formule),
          throwOnError: false,
          trust: false,
          strict: "ignore"
        });
        morceaux.push(cible);
      } catch (erreur) {
        return;
      }

      const apres = reste.slice(fin);
      if (apres) morceaux.push(racine.createTextNode(apres));
      morceaux.forEach(function (morceau) {
        texte.parentNode.insertBefore(morceau, texte);
      });
      texte.parentNode.removeChild(texte);
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

  function contexteEnLigne(element, configuration) {
    if (configuration.enLigne) return true;
    if (!element || !element.tagName) return false;
    return /^(H1|H2|H3|H4|H5|H6|P|SPAN|STRONG|EM|LABEL|BUTTON|SMALL)$/.test(element.tagName);
  }

  function rendreReponseIA(brut, element, options) {
    const cible = element;
    const configuration = Object.assign({ enLigne: false, force: false }, options || {});

    if (!cible) {
      throw new Error("rendreReponseIA : élément cible manquant.");
    }

    if ((cible.tagName === "CODE" || cible.tagName === "PRE") && !configuration.force) {
      return cible;
    }

    if (cible.dataset.renduTraite === "1" && !configuration.force) {
      return cible;
    }

    verifierDependances();

    const protection = protegerMath(String(brut == null ? "" : brut));
    const html = parserMarkdown(
      protection.source,
      contexteEnLigne(cible, configuration)
    );
    const fragment = fragmentSanitise(html);
    restaurerMath(fragment, protection.math);

    cible.replaceChildren(fragment);
    cible.classList.add("ai-rendered-content");

    rendreLatexNu(cible);
    mettreEnFormeCode(cible);
    cible.dataset.renduTraite = "1";
    cible.dataset.renduVersion = "3";
    return cible;
  }

  function rendreTous(parent) {
    const racine = parent || document;
    racine.querySelectorAll(SELECTEUR_RENDU).forEach(function (element) {
      if (element.dataset.renduTraite === "1") return;
      const enLigne = element.hasAttribute("data-rendu-ligne");
      const source = element.textContent || "";
      rendreReponseIA(source, element, { enLigne: enLigne });
    });
  }

  function initialiser(tentative) {
    const numeroTentative = Number(tentative || 0);
    if (!document.querySelector(SELECTEUR_RENDU)) {
      return;
    }

    try {
      verifierDependances();
      rendreTous(document);
    } catch (erreur) {
      // MODIF : les scripts CDN sont defer ; en cas de chargement retardé,
      // on retente brièvement au lieu de laisser le Markdown/LaTeX brut.
      if (numeroTentative < 20) {
        window.setTimeout(function () {
          initialiser(numeroTentative + 1);
        }, 150);
        return;
      }
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
