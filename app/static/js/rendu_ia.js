/* Gasy Mahay — rendu sécurisé des réponses IA */
// MODIF : nouveau moteur navigateur unique pour Markdown, KaTeX, chimie,
// code et tableaux. Le texte source reste du texte brut ; seul le DOM
// final est généré après sanitization DOMPurify.

(function () {
  "use strict";

  const SELECTEUR_RENDU = "[data-rendu]";

  function etatDependances() {
    return {
      marked: Boolean(window.marked),
      purify: Boolean(window.DOMPurify),
      katex: Boolean(window.katex && typeof window.katex.render === "function"),
    };
  }

  function verifierDependances() {
    const etat = etatDependances();
    if (!etat.marked || !etat.purify || !etat.katex) {
      console.warn("[Gasy Mahay] rendu IA en mode dégradé", etat);
    }
    return etat;
  }

  function signatureDependances(etat) {
    return [etat.marked ? "1" : "0", etat.purify ? "1" : "0", etat.katex ? "1" : "0"].join("");
  }

  // MODIF : Marked considère \\[ et \\( comme des échappements Markdown et
  // supprime donc le premier antislash. On protège les blocs mathématiques
  // ENTIEREMENT avant Markdown, puis on restaure leurs délimiteurs après
  // sanitization. Ainsi \\frac, \\begin, indices et underscores ne sont
  // pas interprétés comme du Markdown.
  const TOKEN_MATH = "\uE000GMATH_";
  const SOURCES_ORIGINALES = new WeakMap();

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
    // Compatibilité renforcée : beaucoup de sorties legacy du Quiz IA utilisent
    // encore $...$ ou $...$. Elles doivent être protégées avant Marked,
    // exactement comme \\( ... \\) et \\[ ... \\].
    const protection = source.replace(
      /\x60\x60\x60[\s\S]*?\x60\x60\x60|\x60[^\x60\n]*\x60|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$(?!\$)[^$\n]+?\$|\$\$|\\begin\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\}[\s\S]*?\\end\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\}/g,
      function (match) {
        // Un délimiteur $$ orphelin doit disparaître plutôt que devenir du
        // texte visible dans le quiz. Les blocs de code sont capturés avant
        // cette règle et restent donc intacts.
        if (match === "$$") return "";

        const estDollarDisplay = match.indexOf("$") === 0;
        const estMatriceDisplay = match.indexOf("\\begin{") === 0;
        const estDisplay =
          match.indexOf("\\[") === 0 ||
          estDollarDisplay ||
          estMatriceDisplay;
        const estInline =
          match.indexOf("\\(") === 0 ||
          (match.indexOf("$") === 0 && !estDollarDisplay);

        if (estDisplay || estInline) {
          const longueurDelimiteur =
            estMatriceDisplay
              ? 0
              : (
                  match.indexOf("\\[") === 0 ||
                  match.indexOf("\\(") === 0 ||
                  estDollarDisplay
                )
                ? 2
                : 1;
          const contenu = estMatriceDisplay
            ? match
            : match.slice(longueurDelimiteur, -longueurDelimiteur);
          const index = math.push({
            display: estDisplay,
            contenu: contenu,
          }) - 1;
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
            if (window.katex && typeof window.katex.render === "function") {
              window.katex.render(item.contenu, cible, {
                displayMode: Boolean(item.display),
                throwOnError: false,
                trust: false,
                strict: "ignore",
              });
              morceaux.push(cible);
            } else {
              morceaux.push(racine.createTextNode(item.contenu));
            }
          } catch (erreur) {
            morceaux.push(racine.createTextNode(item.contenu));
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

    if (enLigne) texte = texte.replace(/(\d)\*(?=\d)/g, "$1\\*");
    if (!window.marked) return { html: false, contenu: texte };
    if (enLigne && typeof window.marked.parseInline === "function") {
      return { html: true, contenu: window.marked.parseInline(texte) };
    }
    return {
      html: true,
      contenu: window.marked.parse(texte, { gfm: true, breaks: true, headerIds: false, mangle: false }),
    };
  }
  function fragmentSanitise(resultat) {
    if (!resultat.html || !window.DOMPurify) {
      const fragment = document.createDocumentFragment();
      fragment.appendChild(document.createTextNode(resultat.contenu));
      return fragment;
    }
    return window.DOMPurify.sanitize(resultat.contenu, {
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

  const MOTIFS_LATEX_NUS = [
    /\\begin\{(bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\}[\s\S]*?\\end\{\1\}/g,
    /\\(?:frac|dfrac|tfrac)\{[^{}\n]*\}\{[^{}\n]*\}/g,
    /\\sqrt(?:\[[^\]\n]*\])?\{[^{}\n]*\}/g,
    /\\(?:text|mathrm|mathbf|mathbb|mathcal|operatorname|vec)\{[^{}\n]*\}/g,
    /\\(?:det|ln|log|sin|cos|tan|cot|exp|lim|partial|nabla|alpha|beta|gamma|delta|theta|lambda|mu|nu|pi|rho|sigma|tau|phi|omega)(?:_\{[^{}\n]*\}|_[A-Za-z0-9]+|\^\{[^{}\n]*\}|\^[A-Za-z0-9]+)?(?:\([^)\n]{0,40}\))?/g,
    /[A-Za-z](?:_\{[^{}\n]*\}|_[A-Za-z0-9]+|\^\{[^{}\n]*\}|\^[A-Za-z0-9]+)/g,
    /\\(?:cdot|times|pm|leq|geq|neq|approx|infty|to|rightarrow|left|right|,|:|;|!)/g
  ];

  function trouverPremierLatexNu(valeur) {
    let meilleur = null;

    MOTIFS_LATEX_NUS.forEach(function (motif) {
      motif.lastIndex = 0;
      const match = motif.exec(valeur);
      if (!match) return;
      if (!meilleur || match.index < meilleur.index) {
        meilleur = { index: match.index, texte: match[0] };
      }
    });

    return meilleur;
  }

  function creerNoeudLatex(racine, formule, displayMode) {
    const cible = racine.createElement("span");
    cible.className = displayMode ? "gm-latex-fallback gm-latex-display" : "gm-latex-fallback";
    try {
      window.katex.render(formule, cible, {
        displayMode: Boolean(displayMode),
        throwOnError: false,
        trust: false,
        strict: "ignore"
      });
      return cible;
    } catch (erreur) {
      return null;
    }
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

      let position = 0;
      let modifie = false;
      const morceaux = [];

      while (position < valeur.length) {
        const reste = valeur.slice(position);
        const match = trouverPremierLatexNu(reste);
        if (!match) break;

        const debut = position + match.index;
        const fin = debut + match.texte.length;
        if (debut > position) morceaux.push(racine.createTextNode(valeur.slice(position, debut)));

        const displayMode = /^\\begin\{(?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|cases|aligned|array)\}/.test(match.texte);
        const noeudLatex = creerNoeudLatex(racine, match.texte, displayMode);

        if (!noeudLatex) {
          morceaux.length = 0;
          modifie = false;
          break;
        }

        morceaux.push(noeudLatex);
        position = fin;
        modifie = true;
      }

      if (!modifie) return;
      if (position < valeur.length) morceaux.push(racine.createTextNode(valeur.slice(position)));

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
    if (!cible) throw new Error("rendreReponseIA : élément cible manquant.");

    if ((cible.tagName === "CODE" || cible.tagName === "PRE") && !configuration.force) return cible;

    const etat = verifierDependances();
    const signature = signatureDependances(etat);
    if (cible.dataset.renduTraite === "1" && !configuration.force && cible.dataset.renduDeps === signature) {
      return cible;
    }

    const sourceOriginale = SOURCES_ORIGINALES.get(cible) || String(brut == null ? "" : brut);
    SOURCES_ORIGINALES.set(cible, sourceOriginale);

    const protection = protegerMath(sourceOriginale);
    const resultatMarkdown = parserMarkdown(protection.source, contexteEnLigne(cible, configuration));
    const fragment = fragmentSanitise(resultatMarkdown);
    restaurerMath(fragment, protection.math);

    cible.replaceChildren(fragment);
    cible.classList.add("ai-rendered-content");
    rendreLatexNu(cible);
    mettreEnFormeCode(cible);
    cible.dataset.renduTraite = "1";
    cible.dataset.renduVersion = "4";
    cible.dataset.renduDeps = signature;
    return cible;
  }
  function rendreTous(parent) {
    const racine = parent || document;
    racine.querySelectorAll(SELECTEUR_RENDU).forEach(function (element) {
      const enLigne = element.hasAttribute("data-rendu-ligne");
      const source = SOURCES_ORIGINALES.get(element) || element.textContent || "";
      rendreReponseIA(source, element, { enLigne: enLigne });
    });
  }
  function initialiser(tentative) {
    const numeroTentative = Number(tentative || 0);
    if (!document.querySelector(SELECTEUR_RENDU)) {
      return;
    }

    const etat = etatDependances();
    try {
      rendreTous(document);
    } catch (erreur) {
      console.warn("[Gasy Mahay] rendu IA partiel :", erreur);
    }

    if ((!etat.marked || !etat.purify || !etat.katex) && numeroTentative < 100) {
      window.setTimeout(function () {
        initialiser(numeroTentative + 1);
      }, 150);
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
