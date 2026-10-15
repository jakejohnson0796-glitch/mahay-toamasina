/* Lecture vocale du Tuteur IA — utilise les voix disponibles dans le navigateur/appareil.
   La synthèse est pilotée côté client, sans endpoint audio ajouté au serveur. */
(function () {
  "use strict";

  const racine = document.querySelector("[data-tuteur-lecture]");
  if (!racine) return;

  const boutonLireTout = racine.querySelector("[data-lecture-tout]");
  const boutonsCibles = Array.from(document.querySelectorAll("[data-lecture-cible]"));
  const boutonPause = racine.querySelector("[data-lecture-pause]");
  const boutonReprendre = racine.querySelector("[data-lecture-reprendre]");
  const boutonArreter = racine.querySelector("[data-lecture-arreter]");
  const selectVoix = racine.querySelector("[data-lecture-voix]");
  const selectVitesse = racine.querySelector("[data-lecture-vitesse]");
  const statut = racine.querySelector("[data-lecture-statut]");
  const synthese = "speechSynthesis" in window ? window.speechSynthesis : null;
  const Utterance = window.SpeechSynthesisUtterance;

  let voixDisponibles = [];
  let morceaux = [];
  let indexMorceau = 0;
  let generation = 0;
  let enCours = false;
  let enPause = false;

  function direStatut(message) {
    if (statut) statut.textContent = message;
  }

  function basculerCommandes() {
    const supporte = Boolean(synthese && Utterance);
    if (boutonLireTout) boutonLireTout.disabled = !supporte;
    boutonsCibles.forEach((bouton) => { bouton.disabled = !supporte; });
    if (boutonPause) boutonPause.disabled = !supporte || !enCours || enPause;
    if (boutonReprendre) boutonReprendre.disabled = !supporte || !enCours || !enPause;
    if (boutonArreter) boutonArreter.disabled = !supporte || !enCours;
  }

  function contenuVisible(element) {
    if (!element || !element.isConnected) return false;
    const details = element.closest("details");
    if (details && !details.open) return false;
    if (element.closest("[hidden], [aria-hidden='true']")) return false;
    return true;
  }

  function mathEnParoles(latex) {
    let texte = String(latex || "")
      .replace(/\\(?:left|right|displaystyle|textstyle|scriptstyle|mathrm|mathbf|mathit|boldsymbol)\b/g, " ")
      .replace(/\\(?:text|textrm|textbf|operatorname|mbox)\s*\{([^{}]*)\}/g, "$1")
      .replace(/\\sqrt\s*\{([^{}]*)\}/g, " racine carrée de $1 ");

    // Réduit les fractions de l'intérieur vers l'extérieur, y compris les cas imbriqués.
    for (let tentative = 0; tentative < 6; tentative += 1) {
      const suivante = texte.replace(
        /\\(?:dfrac|tfrac|frac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g,
        " fraction $1 sur $2 "
      );
      if (suivante === texte) break;
      texte = suivante;
    }

    texte = texte
      .replace(/\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}/g, " racine $1 de $2 ")
      .replace(/\\(?:times|cdot|ast)\b/g, " multiplié par ")
      .replace(/\\(?:div)\b/g, " divisé par ")
      .replace(/\\(?:leq|le)\b/g, " inférieur ou égal à ")
      .replace(/\\(?:geq|ge)\b/g, " supérieur ou égal à ")
      .replace(/\\(?:neq|ne)\b/g, " différent de ")
      .replace(/\\(?:approx|simeq)\b/g, " environ égal à ")
      .replace(/\\(?:equiv)\b/g, " équivalent à ")
      .replace(/\\(?:pm)\b/g, " plus ou moins ")
      .replace(/\\(?:infty)\b/g, " infini ")
      .replace(/\\(?:pi)\b/g, " pi ")
      .replace(/\\(?:alpha)\b/g, " alpha ")
      .replace(/\\(?:beta)\b/g, " bêta ")
      .replace(/\\(?:gamma)\b/g, " gamma ")
      .replace(/\\(?:theta)\b/g, " thêta ")
      .replace(/\\(?:lambda)\b/g, " lambda ")
      .replace(/\\(?:mu)\b/g, " mu ")
      .replace(/\\(?:sigma)\b/g, " sigma ")
      .replace(/\\(?:omega)\b/g, " oméga ")
      .replace(/\\(?:sum)\b/g, " somme ")
      .replace(/\\(?:int)\b/g, " intégrale ")
      .replace(/\\(?:lim)\b/g, " limite ")
      .replace(/\\(?:to|rightarrow|longrightarrow)\b/g, " tend vers ")
      .replace(/\\(?:in)\b/g, " appartient à ")
      .replace(/\\(?:notin)\b/g, " n'appartient pas à ")
      .replace(/\\(?:cdots|ldots|dots)\b/g, " et ainsi de suite ")
      .replace(/\^\{([^{}]*)\}/g, " puissance $1 ")
      .replace(/_\{([^{}]*)\}/g, " indice $1 ")
      .replace(/\^([A-Za-z0-9])/g, " puissance $1 ")
      .replace(/_([A-Za-z0-9])/g, " indice $1 ")
      .replace(/\\[a-zA-Z]+\*?/g, " ")
      .replace(/[{}]/g, " ")
      .replace(/&/g, " et ")
      .replace(/\\\\/g, ". ")
      .replace(/[=]/g, " égal à ")
      .replace(/[+]/g, " plus ")
      .replace(/(?<![eE])[−-](?!\d{2,})/g, " moins ")
      .replace(/[<>]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    return texte;
  }

  function htmlEnTexte(element) {
    const clone = element.cloneNode(true);

    // Remplace KaTeX par son annotation LaTeX pour éviter de lire deux fois une formule.
    clone.querySelectorAll(".katex").forEach((noeud) => {
      const annotation = noeud.querySelector('annotation[encoding="application/x-tex"]');
      const formule = annotation ? mathEnParoles(annotation.textContent) : mathEnParoles(noeud.textContent);
      noeud.replaceWith(document.createTextNode(" " + formule + " "));
    });

    // Convertit les tableaux en lignes parlées plutôt qu'en suite de colonnes.
    clone.querySelectorAll("table").forEach((table) => {
      const lignes = Array.from(table.querySelectorAll("tr")).map((ligne) => {
        return Array.from(ligne.querySelectorAll("th, td"))
          .map((cellule) => cellule.textContent.replace(/\s+/g, " ").trim())
          .filter(Boolean)
          .join(" ; ");
      }).filter(Boolean);
      table.replaceWith(document.createTextNode(" " + lignes.join(". ") + " "));
    });

    // N'énonce pas un bloc de code syntaxique ni des éléments masqués.
    clone.querySelectorAll("pre, script, style, button, .lecture-vocale-exclue, [hidden], [aria-hidden='true']").forEach((noeud) => noeud.remove());
    clone.querySelectorAll("p, h1, h2, h3, h4, h5, h6, li, blockquote, br").forEach((noeud) => {
      noeud.appendChild(document.createTextNode(". "));
    });

    let texte = clone.textContent || "";
    texte = texte
      .replace(/\[\[DISPLAY\]\]([\s\S]*?)\[\[\/DISPLAY\]\]/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\[\[MATH\]\]([\s\S]*?)\[\[\/MATH\]\]/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\\\[([\s\S]*?)\\\]/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\\\(([\s\S]*?)\\\)/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\$\$([\s\S]*?)\$\$/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\$(?!\$)([^$\n]+)\$/g, (_tout, formule) => mathEnParoles(formule))
      .replace(/\\(?:text|textrm|textbf|operatorname)\s*\{([^{}]*)\}/g, "$1")
      .replace(/\\(?:emph|textit)\s*\{([^{}]*)\}/g, "$1")
      .replace(/\\(?:begin|end)\s*\{[^{}]*\}/g, " ")
      .replace(/\x60([^\x60]+)\x60/g, "$1")
      .replace(/^\s{0,3}#{1,6}\s+/gm, "")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/(^|\s)\*(.*?)\*(?=\s|$)/g, "$1$2")
      .replace(/^\s*[-*+]\s+/gm, "")
      .replace(/^\s*\d+[.)]\s+/gm, "")
      .replace(/\|/g, " ; ")
      .replace(/\n{2,}/g, ". ")
      .replace(/\s+/g, " ")
      .trim();

    return texte;
  }

  function decouperEnMorceaux(texte, limite) {
    const max = limite || 620;
    const phrases = texte.split(/(?<=[.!?;:])\s+/u).filter(Boolean);
    const resultat = [];
    let bloc = "";

    phrases.forEach((phrase) => {
      if (phrase.length > max) {
        if (bloc) {
          resultat.push(bloc.trim());
          bloc = "";
        }
        let reste = phrase;
        while (reste.length > max) {
          let coupe = reste.lastIndexOf(" ", max);
          if (coupe < Math.floor(max * 0.55)) coupe = max;
          resultat.push(reste.slice(0, coupe).trim());
          reste = reste.slice(coupe).trim();
        }
        if (reste) resultat.push(reste);
      } else if (!bloc) {
        bloc = phrase;
      } else if ((bloc + " " + phrase).length <= max) {
        bloc += " " + phrase;
      } else {
        resultat.push(bloc.trim());
        bloc = phrase;
      }
    });
    if (bloc.trim()) resultat.push(bloc.trim());
    return resultat;
  }

  function sectionsPourLire() {
    return Array.from(document.querySelectorAll("[data-tuteur-content]")).filter(contenuVisible);
  }

  function prendreTexte(elements) {
    return elements.map(htmlEnTexte).filter(Boolean).join(". ")
      .replace(/(?:\.\s*){2,}/g, ". ")
      .replace(/\s+([,.!?;:])/g, "$1")
      .trim();
  }

  function chargerVoix() {
    if (!synthese || !selectVoix) return;
    voixDisponibles = synthese.getVoices ? synthese.getVoices() : [];
    const choixActuel = selectVoix.value;
    selectVoix.replaceChildren();

    const automatique = document.createElement("option");
    automatique.value = "";
    automatique.textContent = "Voix automatique";
    automatique.setAttribute("data-no-translate", "");
    selectVoix.appendChild(automatique);

    voixDisponibles.forEach((voix, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = voix.name + " (" + voix.lang + ")";
      option.setAttribute("data-no-translate", "");
      selectVoix.appendChild(option);
    });

    selectVoix.value = choixActuel && Number(choixActuel) < voixDisponibles.length ? choixActuel : "";
    selectVoix.disabled = voixDisponibles.length === 0;
  }

  function annulerLecture(message) {
    generation += 1;
    if (synthese) synthese.cancel();
    morceaux = [];
    indexMorceau = 0;
    enCours = false;
    enPause = false;
    basculerCommandes();
    if (message) direStatut(message);
  }

  function terminerLecture(token) {
    if (token !== generation) return;
    morceaux = [];
    indexMorceau = 0;
    enCours = false;
    enPause = false;
    basculerCommandes();
    direStatut("Lecture terminée.");
  }

  function lireMorceau(token) {
    if (token !== generation || !enCours || enPause) return;
    if (indexMorceau >= morceaux.length) {
      terminerLecture(token);
      return;
    }

    const utterance = new Utterance(morceaux[indexMorceau]);
    const indexVoix = selectVoix && selectVoix.value !== "" ? Number(selectVoix.value) : -1;
    const voix = indexVoix >= 0 ? voixDisponibles[indexVoix] : null;
    if (voix) {
      utterance.voice = voix;
      utterance.lang = voix.lang || "fr-FR";
    } else {
      utterance.lang = "fr-FR";
    }
    utterance.rate = selectVitesse ? Number(selectVitesse.value || 1) : 1;
    utterance.pitch = 1;

    utterance.onend = () => {
      if (token !== generation) return;
      indexMorceau += 1;
      lireMorceau(token);
    };
    utterance.onerror = (event) => {
      if (token !== generation) return;
      if (event && (event.error === "canceled" || event.error === "interrupted")) return;
      annulerLecture("La lecture vocale a rencontré un problème. Essaie une autre voix ou réessaie.");
    };

    try {
      synthese.speak(utterance);
    } catch (_erreur) {
      annulerLecture("La lecture vocale n'est pas disponible sur cet appareil.");
    }
  }

  function demarrerLecture(elements, message) {
    if (!synthese || !Utterance) {
      direStatut("La lecture vocale n'est pas prise en charge par ce navigateur.");
      return;
    }
    const texte = prendreTexte(elements);
    if (!texte) {
      direStatut("Aucun texte lisible dans cette partie.");
      return;
    }

    annulerLecture("");
    const token = generation;
    morceaux = decouperEnMorceaux(texte);
    indexMorceau = 0;
    enCours = true;
    enPause = false;
    basculerCommandes();
    direStatut(message);
    lireMorceau(token);
  }

  if (!synthese || !Utterance) {
    direStatut("La lecture vocale n'est pas prise en charge par ce navigateur.");
    basculerCommandes();
  } else {
    chargerVoix();
    if (typeof synthese.addEventListener === "function") {
      synthese.addEventListener("voiceschanged", chargerVoix);
    } else {
      synthese.onvoiceschanged = chargerVoix;
    }
    window.setTimeout(chargerVoix, 250);
    basculerCommandes();
  }

  if (boutonLireTout) {
    boutonLireTout.addEventListener("click", () => {
      demarrerLecture(sectionsPourLire(), "Lecture de la réponse en cours…");
    });
  }

  boutonsCibles.forEach((bouton) => {
    bouton.addEventListener("click", () => {
      const cible = bouton.getAttribute("data-lecture-cible");
      const element = document.querySelector('[data-tuteur-content="' + cible + '"]');
      if (!element || !contenuVisible(element)) {
        direStatut("Ouvre d'abord cette partie pour la lire.");
        return;
      }
      demarrerLecture([element], "Lecture de cette partie en cours…");
    });
  });

  if (boutonPause) {
    boutonPause.addEventListener("click", () => {
      if (!synthese || !enCours || enPause) return;
      synthese.pause();
      enPause = true;
      basculerCommandes();
      direStatut("Lecture en pause.");
    });
  }

  if (boutonReprendre) {
    boutonReprendre.addEventListener("click", () => {
      if (!synthese || !enCours || !enPause) return;
      synthese.resume();
      enPause = false;
      basculerCommandes();
      direStatut("Lecture reprise.");
    });
  }

  if (boutonArreter) {
    boutonArreter.addEventListener("click", () => annulerLecture("Lecture arrêtée."));
  }

  window.addEventListener("pagehide", () => {
    if (synthese) synthese.cancel();
  });
})();