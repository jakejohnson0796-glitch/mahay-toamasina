(function () {
  "use strict";

  const root = document.getElementById("salle-virtuelle");
  if (!root) return;

  const seanceId = root.dataset.seanceId;
  const csrf = root.dataset.csrfToken;
  const peutGerer = root.dataset.peutGerer === "true";
  const base = "/classe/seances/" + encodeURIComponent(seanceId);
  const panels = {
    sondages: document.getElementById("panneau-sondages"),
    groupes: document.getElementById("panneau-groupes"),
    documents: document.getElementById("panneau-documents"),
    transcription: document.getElementById("panneau-transcription")
  };
  const buttons = {
    sondages: document.getElementById("btn-sondages"),
    groupes: document.getElementById("btn-groupes"),
    documents: document.getElementById("btn-documents"),
    transcription: document.getElementById("btn-transcription")
  };
  const notifications = document.getElementById("notifications-salle");

  function notifier(texte) {
    if (typeof window.mahayNotifier === "function") {
      window.mahayNotifier(texte);
      return;
    }
    if (!notifications) return;
    const element = document.createElement("div");
    element.className = "notification-salle";
    element.textContent = texte;
    notifications.appendChild(element);
    window.setTimeout(function () { element.remove(); }, 5000);
  }

  async function obtenirJson(url, options) {
    const response = await fetch(url, Object.assign({
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" }
    }, options || {}));
    let data = {};
    try { data = await response.json(); } catch (_erreur) { /* réponse non JSON */ }
    if (!response.ok) {
      throw new Error(data.erreur || "L'opération n'a pas pu être effectuée.");
    }
    return data;
  }

  function envoyerFormulaire(url, valeurs) {
    const donnees = new URLSearchParams();
    donnees.set("_csrf", csrf);
    Object.keys(valeurs || {}).forEach(function (cle) {
      const valeur = valeurs[cle];
      if (valeur !== undefined && valeur !== null) donnees.set(cle, String(valeur));
    });
    return obtenirJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: donnees.toString()
    });
  }

  function ouvrirPanneau(nom) {
    Object.keys(panels).forEach(function (cle) {
      const actif = cle === nom && panels[cle].hidden;
      panels[cle].hidden = !actif;
      buttons[cle].setAttribute("aria-pressed", String(actif));
      buttons[cle].classList.toggle("bouton-controle-actif", actif);
    });
    if (nom === "sondages" && !panels.sondages.hidden) actualiserSondages();
    if (nom === "groupes" && !panels.groupes.hidden) actualiserGroupes();
    if (nom === "documents" && !panels.documents.hidden) actualiserDocuments();
    if (nom === "transcription" && !panels.transcription.hidden) actualiserTranscription();
  }

  Object.keys(buttons).forEach(function (nom) {
    buttons[nom].addEventListener("click", function () { ouvrirPanneau(nom); });
  });

  function creerElement(parent, tag, texte, classe) {
    const element = document.createElement(tag);
    if (texte !== undefined && texte !== null) element.textContent = texte;
    if (classe) element.className = classe;
    parent.appendChild(element);
    return element;
  }

  // --- Quiz et sondages : les réponses sont validées et enregistrées côté serveur.
  const listeSondages = document.getElementById("liste-sondages");

  function afficherSondage(sondage) {
    const carte = document.createElement("article");
    carte.className = "classe-interaction-carte";
    creerElement(carte, "h3", sondage.question);
    creerElement(carte, "p",
      (sondage.type === "quiz" ? "Quiz" : "Sondage") +
      (sondage.ouvert ? " · en cours" : " · terminé"),
      "stat-label");

    const choix = document.createElement("div");
    choix.className = "classe-interaction-choix";
    const groupe = "sondage-" + sondage.id;
    sondage.options.forEach(function (option, index) {
      const ligne = document.createElement("label");
      ligne.className = "classe-interaction-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = groupe;
      radio.value = String(index);
      radio.checked = sondage.ma_reponse === index;
      radio.disabled = !sondage.ouvert;
      ligne.appendChild(radio);
      creerElement(ligne, "span", option);
      if (sondage.comptes) {
        const nombre = sondage.comptes[index] || 0;
        creerElement(ligne, "span", nombre + " vote(s)", "classe-interaction-votes");
      }
      choix.appendChild(ligne);
    });
    carte.appendChild(choix);

    if (sondage.ouvert) {
      const voter = creerElement(carte, "button", sondage.a_repondu ? "Modifier ma réponse" : "Répondre", "bouton bouton-secondaire");
      voter.type = "button";
      voter.addEventListener("click", async function () {
        const selection = carte.querySelector("input[name='" + groupe + "']:checked");
        if (!selection) { notifier("Choisis une réponse avant de valider."); return; }
        try {
          await envoyerFormulaire(base + "/sondages/" + sondage.id + "/repondre", {
            option_index: selection.value
          });
          await actualiserSondages();
          notifier("Réponse enregistrée.");
        } catch (erreur) { notifier(erreur.message); }
      });
      if (peutGerer) {
        const fermer = creerElement(carte, "button", "Clôturer", "bouton bouton-secondaire");
        fermer.type = "button";
        fermer.addEventListener("click", async function () {
          try {
            await envoyerFormulaire(base + "/sondages/" + sondage.id + "/cloturer", {});
            await actualiserSondages();
          } catch (erreur) { notifier(erreur.message); }
        });
      }
    } else if (sondage.type === "quiz" && sondage.bonne_option !== null) {
      const reponse = sondage.ma_reponse === sondage.bonne_option
        ? "Ta réponse était correcte."
        : "La bonne réponse était : " + (sondage.options[sondage.bonne_option] || "à vérifier") + ".";
      creerElement(carte, "p", reponse, "classe-interaction-correction");
    }
    creerElement(carte, "p", sondage.nombre_reponses + " réponse(s)", "stat-label");
    return carte;
  }

  async function actualiserSondages() {
    if (!listeSondages) return;
    try {
      const data = await obtenirJson(base + "/sondages");
      listeSondages.replaceChildren();
      if (!data.sondages.length) {
        creerElement(listeSondages, "p", "Aucun quiz ou sondage pour le moment.", "stat-label");
      } else {
        data.sondages.forEach(function (sondage) {
          listeSondages.appendChild(afficherSondage(sondage));
        });
      }
    } catch (erreur) {
      listeSondages.replaceChildren();
      creerElement(listeSondages, "p", erreur.message, "erreur");
    }
  }

  const formSondage = document.getElementById("form-creer-sondage");
  if (formSondage) {
    const type = document.getElementById("sondage-type");
    const bonneWrap = document.getElementById("sondage-bonne-reponse-wrap");
    type.addEventListener("change", function () {
      bonneWrap.hidden = type.value !== "quiz";
    });
    formSondage.addEventListener("submit", async function (event) {
      event.preventDefault();
      const valeurs = new FormData(formSondage);
      const donnees = {
        question: valeurs.get("question"),
        options: valeurs.get("options"),
        type_sondage: valeurs.get("type_sondage")
      };
      if (donnees.type_sondage === "quiz") {
        const numero = Number(valeurs.get("bonne_option_numero"));
        donnees.bonne_option = Number.isInteger(numero) ? numero - 1 : -1;
      }
      try {
        await envoyerFormulaire(base + "/sondages", donnees);
        formSondage.reset();
        bonneWrap.hidden = true;
        await actualiserSondages();
        notifier("Le quiz ou sondage est lancé.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }

  // --- Répartition en sous-salles : seul le serveur choisit les affectations.
  const listeGroupes = document.getElementById("liste-groupes");
  async function actualiserGroupes() {
    if (!listeGroupes) return;
    try {
      const data = await obtenirJson(base + "/groupes");
      listeGroupes.replaceChildren();
      if (!data.groupes.length) {
        creerElement(listeGroupes, "p", "Aucune sous-salle n'a été créée.", "stat-label");
        return;
      }
      data.groupes.forEach(function (groupe) {
        const carte = creerElement(listeGroupes, "article", null, "classe-interaction-carte");
        creerElement(carte, "h3", groupe.nom);
        creerElement(carte, "p", groupe.nombre_membres + " élève(s)", "stat-label");
        if (groupe.membres && groupe.membres.length) {
          creerElement(carte, "p", groupe.membres.join(", "));
        }
        const lien = creerElement(carte, "a", "Ouvrir la sous-salle", "bouton bouton-secondaire");
        lien.href = groupe.rejoindre_url;
        lien.target = "_blank";
        lien.rel = "noopener";
      });
    } catch (erreur) {
      listeGroupes.replaceChildren();
      creerElement(listeGroupes, "p", erreur.message, "erreur");
    }
  }

  const formGroupes = document.getElementById("form-creer-groupes");
  if (formGroupes) {
    formGroupes.addEventListener("submit", async function (event) {
      event.preventDefault();
      const nombre = Number(new FormData(formGroupes).get("nombre_groupes"));
      try {
        await envoyerFormulaire(base + "/groupes", { nombre_groupes: nombre });
        await actualiserGroupes();
        notifier("Les élèves ont été répartis dans les sous-salles.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }

  // --- Partage de documents : le serveur ne propose que des documents approuvés.
  const listeDocuments = document.getElementById("liste-documents-partages");
  const selectDocument = document.getElementById("document-a-partager");
  async function actualiserDocuments() {
    if (!listeDocuments) return;
    try {
      const data = await obtenirJson(base + "/documents");
      listeDocuments.replaceChildren();
      if (!data.partages.length) {
        creerElement(listeDocuments, "p", "Aucun document partagé.", "stat-label");
      }
      data.partages.forEach(function (documentPartage) {
        const ligne = creerElement(listeDocuments, "div", null, "classe-interaction-lien");
        const lien = creerElement(ligne, "a", documentPartage.titre);
        lien.href = documentPartage.ouvrir_url;
        lien.target = "_blank";
        lien.rel = "noopener";

        if (peutGerer) {
          const retirer = creerElement(ligne, "button", "Retirer", "bouton bouton-secondaire");
          retirer.type = "button";
          retirer.addEventListener("click", async function () {
            if (!window.confirm("Retirer ce document de la séance ? Les participants ne pourront plus l'ouvrir depuis cette salle.")) {
              return;
            }
            try {
              await envoyerFormulaire(
                base + "/documents/" + encodeURIComponent(documentPartage.id) + "/retirer",
                {}
              );
              await actualiserDocuments();
              notifier("Document retiré de la séance.");
            } catch (erreur) {
              notifier(erreur.message);
            }
          });
        }
      });
      if (selectDocument) {
        selectDocument.replaceChildren();
        if (!data.disponibles.length) {
          const vide = creerElement(selectDocument, "option", "Aucun nouveau document approuvé");
          vide.value = "";
        } else {
          data.disponibles.forEach(function (doc) {
            const option = creerElement(selectDocument, "option", doc.titre + " · " + doc.type);
            option.value = String(doc.id);
          });
        }
      }
    } catch (erreur) {
      listeDocuments.replaceChildren();
      creerElement(listeDocuments, "p", erreur.message, "erreur");
    }
  }

  const formDocument = document.getElementById("form-partager-document");
  if (formDocument) {
    formDocument.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (!selectDocument || !selectDocument.value) {
        notifier("Aucun document à partager.");
        return;
      }
      try {
        await envoyerFormulaire(base + "/documents/partager", { document_id: selectDocument.value });
        await actualiserDocuments();
        notifier("Document partagé avec les participants.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }

  // --- Transcription : chaque segment est affiché en direct, mais rien n'est sauvegardé
  // automatiquement. Le professeur choisit explicitement d'enregistrer le texte après l'arrêt.
  const transcriptionStatut = document.getElementById("transcription-statut");
  const transcriptionLive = document.getElementById("transcription-live");
  const transcriptionResume = document.getElementById("transcription-resume");
  const btnConsentir = document.getElementById("btn-consentir-transcription");
  const btnRetirer = document.getElementById("btn-retirer-consentement");
  const btnDemarrer = document.getElementById("btn-demarrer-transcription");
  const btnArreter = document.getElementById("btn-arreter-transcription");
  const btnEnregistrer = document.getElementById("btn-enregistrer-transcription");
  const btnResumer = document.getElementById("btn-resumer-transcription");
  const segments = new Map();
  let etatTranscription = null;

  function texteTranscription() {
    return Array.from(segments.values())
      .filter(function (segment) { return segment.final; })
      .map(function (segment) { return segment.nom + " : " + segment.texte; })
      .join("\n");
  }

  function afficherSegments() {
    if (!transcriptionLive) return;
    const lignes = Array.from(segments.values()).map(function (segment) {
      return segment.nom + " : " + segment.texte + (segment.final ? "" : " …");
    });
    transcriptionLive.textContent = lignes.length
      ? lignes.join("\n")
      : "Les sous-titres apparaîtront ici lorsque la transcription sera démarrée.";
    if (btnEnregistrer) {
      btnEnregistrer.disabled = !peutGerer || !texteTranscription().trim() ||
        Boolean(etatTranscription && etatTranscription.active);
    }
  }

  function recevoirSegment(reader, participantInfo, message) {
    const attributes = (reader && reader.info && reader.info.attributes) || {};
    if (!attributes["lk.transcribed_track_id"]) return;
    const identite = (participantInfo && participantInfo.identity) || "participant";
    const segmentId = identite + "-" + (attributes["lk.segment_id"] || Date.now());
    const room = window.mahayTranscriptionRoom;
    const participant = room && identite ? room.remoteParticipants.get(identite) : null;
    const nom = (participant && participant.name) || (participantInfo && participantInfo.name) || "Participant";
    const final = attributes["lk.transcription_final"] === "true";
    segments.set(segmentId, { nom: nom, texte: String(message || "").trim(), final: final });
    while (segments.size > 300) {
      segments.delete(segments.keys().next().value);
    }
    afficherSegments();
  }

  const room = window.mahayTranscriptionRoom;
  if (room && typeof room.registerTextStreamHandler === "function") {
    room.registerTextStreamHandler("lk.transcription", async function (reader, participantInfo) {
      try {
        const message = await reader.readAll();
        recevoirSegment(reader, participantInfo, message);
      } catch (_erreur) {
        notifier("Impossible de lire un segment de transcription.");
      }
    });
  } else if (transcriptionStatut) {
    transcriptionStatut.textContent = "La réception des sous-titres n'est pas disponible dans cette version du client LiveKit.";
  }

  async function actualiserTranscription() {
    if (!transcriptionStatut) return;
    try {
      etatTranscription = await obtenirJson(base + "/transcription");
      const consent = etatTranscription.consenti;
      transcriptionStatut.textContent = etatTranscription.active
        ? "Transcription active — les participants présents ont donné leur accord."
        : (consent ? "Ton accord est enregistré pour cette séance." : "Transcription inactive. Ton accord est demandé avant tout démarrage.");
      if (btnConsentir) btnConsentir.hidden = consent;
      if (btnRetirer) btnRetirer.hidden = !consent;
      if (btnDemarrer) {
        btnDemarrer.hidden = !peutGerer || etatTranscription.active;
        btnDemarrer.disabled = !etatTranscription.agent_configure;
        btnDemarrer.title = etatTranscription.agent_configure
          ? ""
          : "Le worker LiveKit STT doit être déployé et configuré séparément.";
      }
      if (btnArreter) btnArreter.hidden = !peutGerer || !etatTranscription.active;
      if (btnEnregistrer) {
        btnEnregistrer.disabled = !peutGerer || !texteTranscription().trim() || etatTranscription.active;
      }
      if (btnResumer) {
        btnResumer.disabled = !peutGerer || !etatTranscription.contenu;
      }
      if (transcriptionResume) {
        transcriptionResume.hidden = !etatTranscription.resume;
        transcriptionResume.textContent = etatTranscription.resume || "";
      }
      if (etatTranscription.contenu && !segments.size && transcriptionLive) {
        transcriptionLive.textContent = etatTranscription.contenu;
      }
    } catch (erreur) {
      transcriptionStatut.textContent = erreur.message;
    }
  }

  if (btnConsentir) {
    btnConsentir.addEventListener("click", async function () {
      try {
        await envoyerFormulaire(base + "/transcription/consentir", { consenti: "oui" });
        notifier("Ton accord est enregistré. Le professeur pourra démarrer uniquement lorsque tous les participants auront accepté.");
        await actualiserTranscription();
      } catch (erreur) { notifier(erreur.message); }
    });
  }
  if (btnRetirer) {
    btnRetirer.addEventListener("click", async function () {
      // Si la transcription est active, couper d'abord le microphone local :
      // la demande d'arrêt au serveur peut échouer ou prendre du temps.
      let microCoupe = false;
      if (etatTranscription && etatTranscription.active) {
        const room = window.mahayTranscriptionRoom;
        try {
          if (room && room.localParticipant) {
            await room.localParticipant.setMicrophoneEnabled(false);
            microCoupe = true;
            const boutonMicro = document.getElementById("btn-micro");
            if (boutonMicro) boutonMicro.textContent = "Activer le micro";
          }
        } catch (_erreur) {
          notifier("Coupe immédiatement ton micro dans la barre de commandes avant de continuer.");
        }
      }
      try {
        await envoyerFormulaire(base + "/transcription/consentir", { consenti: "non" });
        notifier(microCoupe
          ? "Ton accord est retiré, ton micro est coupé et la transcription a été arrêtée."
          : "Ton accord est retiré. La transcription en cours a été arrêtée.");
        await actualiserTranscription();
      } catch (erreur) {
        notifier((etatTranscription && etatTranscription.active
          ? "Le retrait n'a pas pu être confirmé. Garde ton micro coupé. "
          : "") + erreur.message);
      }
    });
  }
  if (btnDemarrer) {
    btnDemarrer.addEventListener("click", async function () {
      try {
        await envoyerFormulaire(base + "/transcription/demarrer", {});
        segments.clear();
        afficherSegments();
        await actualiserTranscription();
        notifier("Transcription démarrée.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }
  if (btnArreter) {
    btnArreter.addEventListener("click", async function () {
      try {
        await envoyerFormulaire(base + "/transcription/arreter", {});
        await actualiserTranscription();
        notifier("Transcription arrêtée. Le texte n'est pas encore enregistré.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }
  if (btnEnregistrer) {
    btnEnregistrer.addEventListener("click", async function () {
      const contenu = texteTranscription().trim();
      if (!contenu) { notifier("Aucun segment final à enregistrer."); return; }
      try {
        await envoyerFormulaire(base + "/transcription/enregistrer", { contenu: contenu });
        await actualiserTranscription();
        notifier("Compte rendu enregistré. L'audio et la vidéo ne sont pas conservés.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }
  if (btnResumer) {
    btnResumer.addEventListener("click", async function () {
      try {
        const resultat = await envoyerFormulaire(base + "/transcription/resumer", {});
        if (transcriptionResume) {
          transcriptionResume.hidden = false;
          transcriptionResume.textContent = resultat.resume || "";
        }
        notifier("Résumé IA préparé à partir du texte enregistré.");
      } catch (erreur) { notifier(erreur.message); }
    });
  }

  // Rafraîchissement léger des éléments réellement en temps réel.
  window.setInterval(function () {
    if (panels.sondages && !panels.sondages.hidden) actualiserSondages();
  }, 5000);

  afficherSegments();
})();