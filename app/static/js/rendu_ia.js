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

  function normaliserSourceRendu(source) {
    let texte = String(source == null ? "" : source);
    try { texte = texte.normalize("NFC"); } catch (_) {}
    // Reprise du principe du moteur riche : supprimer uniquement les marqueurs
    // invisibles connus qui peuvent perturber les délimiteurs sans modifier
    // les caractères pédagogiques visibles.
    texte = texte.replace(/\uFEFF/g, "").replace(/[\u200B\u200C\u200D\u2060]/g, "");
    return texte.replace(/\r\n?/g, "\n");
  }

  function antislashEchappe(texte, index) {
    let nombre = 0;
    for (let i = index - 1; i >= 0 && texte[i] === "\\\\"; i -= 1) nombre += 1;
    return (nombre % 2) === 1;
  }

  function trouverFinDelimiteur(texte, debut, delimiteur) {
    for (let i = debut; i <= texte.length - delimiteur.length; i += 1) {
      if (texte.slice(i, i + delimiteur.length) === delimiteur && !antislashEchappe(texte, i)) {
        return i;
      }
    }
    return -1;
  }

  const ENVIRONNEMENTS_MATH = new Set([
    "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix",
    "cases", "aligned", "alignedat", "gathered", "smallmatrix", "array",
    "align", "align*", "gather", "gather*", "equation", "equation*", "split"
  ]);

  function protegerMath(brut) {
    const math = [];
    const source = normaliserSourceRendu(convertirMarqueursTransport(brut));
    let protection = "";
    let i = 0;

    function ajouterMath(contenu, display, longueur) {
      const index = math.push({ display: Boolean(display), contenu: contenu }) - 1;
      protection += TOKEN_MATH + index + "\uE001";
      i += longueur;
    }

    while (i < source.length) {
      // Les blocs de code sont prioritaires : une formule contenue dans du code
      // reste du code, jamais une formule rendue.
      if (source.slice(i, i + 3) === "\x60\x60\x60") {
        const fin = source.indexOf("\x60\x60\x60", i + 3);
        if (fin < 0) {
          protection += source.slice(i);
          break;
        }
        const limite = fin + 3;
        protection += source.slice(i, limite);
        i = limite;
        continue;
      }

      if (source[i] === "\x60") {
        const fin = trouverFinDelimiteur(source, i + 1, "\x60");
        if (fin >= 0) {
          const limite = fin + 1;
          protection += source.slice(i, limite);
          i = limite;
          continue;
        }
      }

      if (source.slice(i, i + 2) === "\\[") {
        const fin = trouverFinDelimiteur(source, i + 2, "\\]");
        if (fin >= 0) {
          ajouterMath(source.slice(i + 2, fin), true, fin + 2 - i);
          continue;
        }
      }

      if (source.slice(i, i + 2) === "\\(") {
        const fin = trouverFinDelimiteur(source, i + 2, "\\)");
        if (fin >= 0) {
          ajouterMath(source.slice(i + 2, fin), false, fin + 2 - i);
          continue;
        }
      }

      if (source.slice(i, i + 2) === "$$") {
        const fin = trouverFinDelimiteur(source, i + 2, "$$");
        if (fin >= 0) {
          ajouterMath(source.slice(i + 2, fin), true, fin + 2 - i);
          continue;
        }
        // Cas observé dans le Quiz : un $$ isolé ne doit jamais rester visible.
        i += 2;
        continue;
      }

      if (source[i] === "$" && source[i + 1] !== "$" && !antislashEchappe(source, i)) {
        const fin = trouverFinDelimiteur(source, i + 1, "$");
        if (fin > i + 1) {
          const contenu = source.slice(i + 1, fin);
          // Un montant monétaire pur ne devient pas une formule.
          if (!/^\s*[\d,.]+\s*$/.test(contenu)) {
            ajouterMath(contenu, false, fin + 1 - i);
            continue;
          }
        }
      }

      // Compatibilité avec les sorties historiques contenant un environnement
      // LaTeX nu sans \[...\].
      if (source.slice(i, i + 7) === "\\begin{") {
        const finNom = source.indexOf("}", i + 7);
        if (finNom > 0) {
          const env = source.slice(i + 7, finNom);
          if (ENVIRONNEMENTS_MATH.has(env)) {
            const finEnv = trouverFinDelimiteur(source, finNom + 1, "\\end{" + env + "}");
            if (finEnv >= 0) {
              const limite = finEnv + ("\\end{" + env + "}").length;
              ajouterMath(source.slice(i, limite), true, limite - i);
              continue;
            }
          }
        }
      }

      protection += source[i];
      i += 1;
    }

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
              let formule = String(item.contenu == null ? "" : item.contenu);
              formule = formule.replace(/\u00A0|\u202F/g, " ");
              // Répare uniquement un double échappement typique du transport
              // JSON/tool lorsqu'aucune commande correctement échappée n'est
              // déjà présente dans la même formule.
              const commandes = /\\(?:frac|dfrac|tfrac|sqrt|begin|end|mathrm|text|det|sum|prod|int|cdot|times|mathbb|mathbf)\b/;
              if (!commandes.test(formule) && /\\\\(?:frac|dfrac|tfrac|sqrt|begin|end|mathrm|text|det|sum|prod|int|cdot|times|mathbb|mathbf)\b/.test(formule)) {
                formule = formule.replace(/\\\\(?=[A-Za-z])/g, "\\");
              }
              formule = formule.replace(/\\label\{[^{}]*\}/g, "");
              window.katex.render(formule, cible, {
                displayMode: Boolean(item.display),
                throwOnError: false,
                trust: false,
                strict: "ignore",
                maxExpand: 1000,
                maxSize: 30,
                output: "htmlAndMathml",
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

  function normaliserTexteMarkdownLegacy(texte) {
    let resultat = String(texte == null ? "" : texte);

    // Certaines réponses IA arrivent encore avec les deux caractères
    // « \\n » au lieu d'un vrai saut de ligne. On les décode uniquement
    // lorsqu'ils introduisent une structure Markdown évidente (liste,
    // numérotation ou section), pour ne jamais casser une commande LaTeX
    // légitime comme \\nabla.
    resultat = resultat
      .replace(/\\n(?=\\s*[-*•]\\s+)/g, "\n")
      .replace(/\\n(?=\\s*\\d+[.)]\\s+)/g, "\n")
      .replace(/\\n(?=\\s*(?:Correction|Exercice|Réponse|Solution|Notion)\\s*:)/gi, "\n")
      .replace(/\\n\\s*\\n(?=\\s*[A-ZÀ-ÖØ-Þ][^\\n]{0,80}:)/g, "\n\n");

    // Les anciens modèles produisent parfois \\textit{...}/\\emph{...}
    // hors d'un délimiteur mathématique. Dans Markdown, l'équivalent sûr
    // est l'italique texte ; on le convertit avant le parsing Marked.
    resultat = resultat
      .replace(/\\(?:textit|emph)\\{([^{}]*)\\}/g, "*$1*")
      .replace(/\\textbf\\{([^{}]*)\\}/g, "**$1**");

    return resultat;
  }

  function parserMarkdown(brut, enLigne) {
    let texte = normaliserTexteMarkdownLegacy(brut);

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
      let ancetre = noeud.parentElement;
      let protege = false;
      while (ancetre) {
        // Ne jamais repasser sur le DOM produit par KaTeX ni sur un bloc de
        // code. On marche toute la chaîne d'ancêtres car certains parseurs
        // peuvent ajouter un wrapper intermédiaire autour du texte.
        if (
          /^(CODE|PRE|MATH|ANNOTATION)$/i.test(ancetre.tagName) ||
          ancetre.classList.contains("katex") ||
          ancetre.classList.contains("gm-katex") ||
          ancetre.classList.contains("gm-latex-fallback")
        ) {
          protege = true;
          break;
        }
        ancetre = ancetre.parentElement;
      }
      if (protege) continue;
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
    cible.dataset.renduVersion = "5";
    cible.dataset.renduDeps = signature;
    return cible;
  }
  function rendreTous(parent) {
    const racine = parent || document;
    const elements = [];
    if (racine.nodeType === 1 && racine.matches && racine.matches(SELECTEUR_RENDU)) {
      elements.push(racine);
    }
    racine.querySelectorAll(SELECTEUR_RENDU).forEach(function (element) {
      if (!elements.includes(element)) elements.push(element);
    });
    elements.forEach(function (element) {
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

  // Les contenus IA peuvent être remplacés après un fetch/AJAX/WebSocket.
  // On re-rend uniquement les nouveaux sous-arbres, sans toucher à la source
  // brute mémorisée dans SOURCES_ORIGINALES.
  if (window.MutationObserver) {
    const observer = new window.MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        Array.from(mutation.addedNodes || []).forEach(function (node) {
          if (node.nodeType === 1) {
            try { rendreTous(node); } catch (_) {}
          }
        });
      });
    });
    const demarrerObserver = function () {
      if (document.body) observer.observe(document.body, { childList: true, subtree: true });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", demarrerObserver, { once: true });
    } else {
      demarrerObserver();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser, { once: true });
  } else {
    initialiser();
  }
})();
