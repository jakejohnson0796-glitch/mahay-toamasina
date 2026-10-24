/* Bilan de reprise : reprise contextualisee, non intrusive et sans stockage du contenu pedagogique. */
(function (window, document) {
  "use strict";

  var root = document.getElementById("bilan-reprise-fond");
  if (!root) return;

  var userKey = String(root.dataset.userKey || "").trim();
  var endpoint = root.dataset.endpoint || "/api/apprentissage/bilan-reprise";
  if (!userKey) return;

  var dialog = document.getElementById("bilan-reprise-dialogue");
  var closeButton = document.getElementById("bilan-reprise-fermer");
  var continueButton = document.getElementById("bilan-reprise-continuer");
  var mainAction = document.getElementById("bilan-reprise-action");
  var mainActionText = document.getElementById("bilan-reprise-action-texte");
  var languageSelect = document.getElementById("select-langue");

  var QUIET_MS = 3 * 60 * 60 * 1000;
  var LOCK_MS = 5 * 60 * 1000;
  var ACTIVITY_WRITE_MS = 15 * 1000;
  var prefix = "mitaridala:bilan-reprise:v1:" + userKey + ":";
  var KEY_ACTIVITY = prefix + "derniere-activite";
  var KEY_SUMMARY = prefix + "dernier-bilan";
  var KEY_SUMMARY_FOR = prefix + "bilan-pour-activite";
  var KEY_LOCK = prefix + "verrou";
  var KEY_TAB = prefix + "onglet-actif";

  var ouvert = false;
  var tentativeOuverture = false;
  var donneesCourantes = null;
  var momentDepartCourant = 0;
  var aUnBilanPrecedentCourant = false;
  var focusAvantOuverture = null;
  var derniereEcritureActivite = 0;
  var jetonVerrou = "";

  var TEXTES = {
    fr: {
      eyebrow: "TON POINT DE REPRISE",
      title: "Content de te revoir",
      intro: "Retrouvons ce que tu as travaillé, ce qui devient plus solide et la meilleure prochaine étape.",
      closeLabel: "Fermer le bilan",
      activityTitle: "Ce que tu as fait",
      activitySub: "Les activités réellement enregistrées",
      learnedTitle: "Ce que tu as appris",
      learnedSub: "Les notions travaillées et leur état actuel",
      strengthenTitle: "À renforcer",
      strengthenSub: "Les priorités sorties de ta progression",
      missionTitle: "Ta prochaine mission",
      missionSub: "Une étape réaliste, adaptée à tes résultats",
      toolsLabel: "TES OUTILS",
      toolsTitle: "Comment MITARIDALA peut t'aider",
      toolsSub: "Choisis une méthode selon ce dont tu as besoin maintenant.",
      reassurance: "Pas besoin de tout faire d'un coup. Une petite étape bien comprise vaut mieux qu'une longue séance précipitée.",
      close: "Continuer plus tard",
      mainAction: "Commencer ma mission",
      periodLast: "Depuis ton dernier bilan",
      periodRecent: "Voici un aperçu de ton activité récente",
      statQuiz: "Quiz terminés",
      statDocs: "Documents consultés",
      statTuteur: "Séances avec le Tuteur IA",
      statGames: "Jeux cérébraux terminés",
      noActivity: "Aucune activité terminée n'a été enregistrée sur cette période. Tu peux reprendre à partir de la mission proposée ci-dessous.",
      noLearning: "Aucune nouvelle notion n'a été évaluée depuis ta dernière reprise. Les priorités existantes figurent dans la section « À renforcer ».",
      noProgress: "Tu n'as pas encore assez de résultats pour tirer une conclusion fiable. Un premier quiz aidera à repérer tes points forts et tes besoins.",
      noStrengthen: "Aucune priorité urgente ne ressort de tes données. Tu peux réviser une notion ou explorer un nouveau sujet.",
      mastery: "Maîtrise confirmée",
      solid: "Bon résultat, à confirmer",
      consolidate: "En consolidation",
      weak: "À renforcer",
      questions: "questions évaluées",
      activityQuiz: "Quiz",
      activityDocument: "Document consulté",
      activityTuteur: "Tuteur IA",
      activityGame: "Jeu cérébral",
      activityCircle: "Participation à un cercle",
      activityJoinedCircle: "Cercle rejoint",
      activityClass: "Classe virtuelle",
      activityShared: "Ressource partagée",
      quizScore: "{score}/{total} bonnes réponses · {percent} %",
      quizDone: "Quiz terminé",
      docDetail: "{subject} · consulté",
      tutorDetail: "Question : {question}",
      tutorUsed: "Explication consultée",
      gameScore: "Score : {score} %",
      gameDone: "Session terminée",
      point: "Point à travailler",
      reasonDue: "Révision prévue : c'est le bon moment pour réactiver cette notion.",
      reasonLow: "Score de maîtrise à {score} % : reprends la méthode avec un exemple guidé.",
      reasonErrors: "{errors} erreurs enregistrées : repère l'étape qui bloque avant de refaire un quiz.",
      reasonStabilize: "Score de maîtrise à {score} % : quelques questions ciblées aideront à stabiliser l'acquis.",
      missionActiveTitle: {
        comprendre: "Débloquer une difficulté",
        pratiquer: "Pratiquer la notion ciblée",
        verifier: "Vérifier la maîtrise",
        terminee: "Mission terminée"
      },
      missionAllTitle: "Toutes les notions suivies sont maîtrisées",
      missionNewTitle: "Préparer ta prochaine mission",
      objectiveUnderstand: "Commence par comprendre l'erreur prioritaire, puis entraîne-toi sur la même notion.",
      objectivePractice: "Réussis une courte série de questions ciblées sur cette notion.",
      objectiveVerify: "Obtiens une nouvelle preuve de réussite pour vérifier que la maîtrise tient dans le temps.",
      objectiveAll: "Tes notions suivies ont été confirmées. Tu peux en explorer une nouvelle.",
      objectiveNew: "Un premier quiz permettra d'identifier tes priorités et de préparer une mission guidée.",
      methodUnderstand: "Le Tuteur IA t'aide à comprendre la méthode et l'erreur à éviter; le quiz vérifie ensuite les acquis.",
      methodPractice: "Un quiz ciblé te permet de pratiquer la même notion avec de nouvelles questions.",
      methodVerify: "Le système cherche une nouvelle preuve, pas seulement un bon score isolé.",
      actionUnderstand: "Reprendre avec le Tuteur IA",
      actionPractice: "Lancer le quiz ciblé",
      actionVerify: "Vérifier ma maîtrise",
      actionAll: "Explorer une nouvelle notion",
      actionNew: "Lancer un quiz",
      accessAction: "Voir les options d'accès",
      methodTutorTitle: "Tuteur IA",
      methodTutorDesc: "Demande une explication progressive et un exemple sur ton erreur.",
      methodQuizTitle: "Quiz ciblé",
      methodQuizDesc: "Teste la même notion avec de nouvelles questions, sans te limiter à relire.",
      methodRevisionTitle: "Fiches de révision",
      methodRevisionDesc: "Reprends les notions et exemples de tes cours approuvés.",
      methodMapTitle: "Carte de connaissances",
      methodMapDesc: "Repère les notions à consolider et les prérequis déjà maîtrisés.",
      methodAccessTitle: "Accès aux outils IA",
      methodAccessDesc: "Consulte les options pour retrouver le Quiz ciblé et le Tuteur IA.",
      week: "jours",
      hours: "h",
      minute: "min",
      justNow: "à l'instant",
      closeError: "Impossible de charger ton bilan pour le moment."
    },
    mg: {
      eyebrow: "FAMINTINANA NY FIANARANA",
      title: "Faly mihaona aminao indray",
      intro: "Andeha hojerentsika izay nodinihinao, izay mihamafy ary ny dingana manaraka mety indrindra.",
      closeLabel: "Hanidy ny famintinana",
      activityTitle: "Izay nataonao",
      activitySub: "Asa voarakitra tokoa",
      learnedTitle: "Izay nianaranao",
      learnedSub: "Lohahevitra niasana sy ny toetrany ankehitriny",
      strengthenTitle: "Hohamafisina",
      strengthenSub: "Laharam-pahamehana hita amin'ny fandrosoanao",
      missionTitle: "Ny iraka manaraka",
      missionSub: "Dingana azo tanterahina araka ny valiny azonao",
      toolsLabel: "FITAOVANA",
      toolsTitle: "Ahoana no hanampian'i MITARIDALA anao",
      toolsSub: "Safidio ny fomba mifanaraka amin'izay ilainao izao.",
      reassurance: "Tsy voatery hatao indray mandeha ny zava-drehetra. Dingana kely iray takatra tsara dia tsara noho ny fianarana maika lava.",
      close: "Tohizo rehefa vonona",
      mainAction: "Hanomboka ny irako",
      periodLast: "Hatramin'ny famintinana farany",
      periodRecent: "Ity ny topi-maso momba ny fianaranao tato ho ato",
      statQuiz: "Quiz vita",
      statDocs: "Tahirin-kevitra nodinihina",
      statTuteur: "Fotoana niarahana tamin'ny Mpampianatra IA",
      statGames: "Lalao fanazaran-tsaina vita",
      noActivity: "Tsy misy asa vita voarakitra tamin'ity fotoana ity. Afaka manohy amin'ny iraka atolotra etsy ambany ianao.",
      noLearning: "Tsy nisy lohahevitra vaovao nodinihina hatramin'ny fiverenanao farany. Hita ao amin'ny fizarana « Hohamafisina » ireo laharam-pahamehana efa misy.",
      noProgress: "Mbola tsy ampy ny valiny hahazoana tsoa-kevitra azo antoka. Hanampy hamantatra ny tanjakao sy izay ilainao hamafisina ny quiz voalohany.",
      noStrengthen: "Tsy misy laharam-pahamehana maika hita amin'ny angona. Afaka mamerina lohahevitra iray na mianatra vaovao ianao.",
      mastery: "Voamarina ny fahaizana",
      solid: "Tsara ny valiny, mbola hamarinina",
      consolidate: "Mbola hamafisina",
      weak: "Hohamafisina",
      questions: "fanontaniana voadinika",
      activityQuiz: "Quiz",
      activityDocument: "Tahirin-kevitra nodinihina",
      activityTuteur: "Mpampianatra IA",
      activityGame: "Lalao fanazaran-tsaina",
      activityCircle: "Fandraisana anjara amin'ny vondrona",
      activityJoinedCircle: "Vondrona nidirana",
      activityClass: "Kilasy virtoaly",
      activityShared: "Loharano nozaraina",
      quizScore: "Valiny marina {score}/{total} · {percent} %",
      quizDone: "Vita ny quiz",
      docDetail: "{subject} · nodinihina",
      tutorDetail: "Fanontaniana: {question}",
      tutorUsed: "Fanazavana nodinihina",
      gameScore: "Isa: {score} %",
      gameDone: "Vita ny lalao",
      point: "Lohahevitra hiasana",
      reasonDue: "Fotoana famerenana izao: avereno ampiasaina ity fahalalana ity.",
      reasonLow: "Isa momba ny fahaizana {score} %: avereno ny fomba miaraka amin'ny ohatra tarihina.",
      reasonErrors: "Fahadisoana {errors} voarakitra: tadiavo ny dingana manakana alohan'ny hanaovana quiz indray.",
      reasonStabilize: "Isa momba ny fahaizana {score} %: hanamafy izany ny fanontaniana kendrena vitsivitsy.",
      missionActiveTitle: {
        comprendre: "Vahao ny olana iray",
        pratiquer: "Manaova fanazaran-tena amin'ilay lohahevitra",
        verifier: "Hamarino ny fahaizana",
        terminee: "Vita ny iraka"
      },
      missionAllTitle: "Voamarina ny lohahevitra narahina rehetra",
      missionNewTitle: "Manomàna ny iraka manaraka",
      objectiveUnderstand: "Atombohy amin'ny fahatakarana ny fahadisoana lehibe, avy eo manaova fanazaran-tena amin'ilay lohahevitra ihany.",
      objectivePractice: "Valio ny fanontaniana kendrena vitsivitsy momba ity lohahevitra ity.",
      objectiveVerify: "Mitadiava porofo vaovao fa maharitra ny fahaizanao.",
      objectiveAll: "Voamarina ireo lohahevitra narahinao. Afaka mianatra vaovao ianao.",
      objectiveNew: "Hanampy hamantatra ny laharam-pahamehanao sy hanomana iraka ny quiz voalohany.",
      methodUnderstand: "Manampy hahatakatra ny fomba sy ny fahadisoana tokony hialana ny Mpampianatra IA; ny quiz no manamarina avy eo.",
      methodPractice: "Ny quiz kendrena dia manampy anao hanao fanazaran-tena amin'ilay lohahevitra amin'ny fanontaniana vaovao.",
      methodVerify: "Mitady porofo vaovao ny rafitra fa tsy mijery isa tsara tokana fotsiny.",
      actionUnderstand: "Hanohy miaraka amin'ny Mpampianatra IA",
      actionPractice: "Hanomboka quiz kendrena",
      actionVerify: "Hamarino ny fahaizako",
      actionAll: "Hijery lohahevitra vaovao",
      actionNew: "Hanomboka quiz",
      accessAction: "Hijery ny safidy fidirana",
      methodTutorTitle: "Mpampianatra IA",
      methodTutorDesc: "Mangataha fanazavana miandalana sy ohatra momba ny fahadisoana.",
      methodQuizTitle: "Quiz kendrena",
      methodQuizDesc: "Andramo amin'ny fanontaniana vaovao ilay lohahevitra, fa aza mamerina mamaky fotsiny.",
      methodRevisionTitle: "Taratasy famerenana",
      methodRevisionDesc: "Avereno ny hevitra sy ohatra avy amin'ny lesona nekena.",
      methodMapTitle: "Sarintanin'ny fahalalana",
      methodMapDesc: "Fantaro ny lohahevitra mila hamafisina sy ny fototra efa voafehy.",
      methodAccessTitle: "Fidirana amin'ny fitaovana IA",
      methodAccessDesc: "Jereo ny safidy hahazoana indray ny Quiz sy ny Mpampianatra IA.",
      week: "andro",
      hours: "ora",
      minute: "min",
      justNow: "vao izao",
      closeError: "Tsy afaka naka ny famintinanao izahay izao."
    }
  };

  function language() {
    try { return window.localStorage.getItem("mahay-langue") === "mg" ? "mg" : "fr"; }
    catch (_erreur) { return "fr"; }
  }

  function text(key) {
    var lang = language();
    var value = TEXTES[lang][key];
    if (value == null) value = TEXTES.fr[key];
    return value == null ? key : value;
  }

  function format(template, values) {
    return String(template || "").replace(/\{([a-z_]+)\}/gi, function (_m, key) {
      return values && values[key] != null ? String(values[key]) : "";
    });
  }

  function appliquerTextesFixes() {
    root.querySelectorAll("[data-bilan-i18n]").forEach(function (element) {
      var key = element.getAttribute("data-bilan-i18n");
      var value = text(key);
      if (typeof value === "string") element.textContent = value;
    });
    root.querySelectorAll("[data-bilan-i18n-aria]").forEach(function (element) {
      element.setAttribute("aria-label", text(element.getAttribute("data-bilan-i18n-aria")));
    });
  }

  function lireNombre(cle) {
    try {
      var nombre = Number(window.localStorage.getItem(cle));
      return Number.isFinite(nombre) && nombre > 0 ? nombre : 0;
    } catch (_erreur) {
      return 0;
    }
  }

  function ecrire(cle, valeur) {
    try { window.localStorage.setItem(cle, String(valeur)); return true; }
    catch (_erreur) { return false; }
  }

  function dateLocaleKey(timestamp) {
    var d = new Date(timestamp);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function dateCourte(value) {
    if (!value) return "";
    var date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "";
    try {
      return new Intl.DateTimeFormat(language() === "mg" ? "mg-MG" : "fr-FR", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"
      }).format(date);
    } catch (_erreur) {
      return date.toLocaleString();
    }
  }

  function dureeDepuis(timestamp) {
    if (!timestamp) return text("periodRecent");
    var ecart = Math.max(0, Date.now() - timestamp);
    var heures = Math.floor(ecart / 3600000);
    var jours = Math.floor(heures / 24);
    if (jours >= 1) return text("periodLast") + " · " + jours + " " + text("week");
    if (heures >= 1) return text("periodLast") + " · " + heures + text("hours");
    var minutes = Math.floor(ecart / 60000);
    if (minutes >= 1) return text("periodLast") + " · " + minutes + " " + text("minute");
    return text("periodLast") + " · " + text("justNow");
  }

  function creerElement(tag, classe, contenu) {
    var element = document.createElement(tag);
    if (classe) element.className = classe;
    if (contenu != null) element.textContent = String(contenu);
    return element;
  }

  function afficherVide(conteneur, message) {
    conteneur.replaceChildren(creerElement("p", "bilan-reprise-vide", message));
  }

  function creerCarte(titre, detail, badge, etat, date, petit) {
    var carte = creerElement("article", "bilan-reprise-element");
    var entete = creerElement("div", "bilan-reprise-element-entete");
    entete.appendChild(creerElement("strong", "", titre || text("point")));
    if (badge) {
      var etiquette = creerElement("span", "bilan-reprise-etat", badge);
      if (etat) etiquette.dataset.etat = etat;
      entete.appendChild(etiquette);
    }
    carte.appendChild(entete);
    if (detail) carte.appendChild(creerElement("p", "", detail));
    if (petit) carte.appendChild(creerElement("small", "", petit));
    if (date) carte.appendChild(creerElement("small", "", dateCourte(date)));
    return carte;
  }

  function activiteFormatee(item) {
    var titre = "";
    var detail = "";
    var badge = "";
    switch (item.type) {
      case "quiz":
        titre = text("activityQuiz") + " · " + (item.matiere || "");
        detail = item.score == null
          ? text("quizDone")
          : format(text("quizScore"), { score: item.score, total: item.nb_questions || 0, percent: item.pourcentage || 0 });
        badge = item.score == null ? "" : String(item.pourcentage || 0) + " %";
        break;
      case "document":
        titre = item.titre || text("activityDocument");
        detail = format(text("docDetail"), { subject: item.matiere || "" });
        break;
      case "tuteur":
        titre = item.notion ? text("activityTuteur") + " · " + item.notion : text("activityTuteur");
        detail = item.question ? format(text("tutorDetail"), { question: item.question }) : text("tutorUsed");
        break;
      case "jeu":
        titre = text("activityGame") + (item.theme ? " · " + item.theme : "");
        detail = item.score == null ? text("gameDone") : format(text("gameScore"), { score: item.score });
        badge = item.score == null ? "" : String(item.score) + " %";
        break;
      case "collaboration":
        if (item.action === "cercle") titre = text("activityCircle");
        else if (item.action === "cercle_rejoint") titre = text("activityJoinedCircle");
        else if (item.action === "classe") titre = text("activityClass");
        else if (item.action === "document") titre = text("activityShared");
        else titre = text("activityCircle");
        break;
      default:
        titre = item.titre || text("activityDocument");
        detail = item.detail || "";
    }
    return creerCarte(titre, detail, badge, "", item.date, "");
  }

  function renderStats(stats) {
    var conteneur = document.getElementById("bilan-reprise-stats");
    conteneur.replaceChildren();
    var elements = [
      { cle: "quiz", label: "statQuiz", symbole: "Q" },
      { cle: "documents", label: "statDocs", symbole: "D" },
      { cle: "tuteur", label: "statTuteur", symbole: "IA" },
      { cle: "jeux", label: "statGames", symbole: "✦" }
    ];
    elements.forEach(function (element) {
      var carte = creerElement("div", "bilan-reprise-stat");
      carte.appendChild(creerElement("span", "bilan-reprise-stat-valeur", Number(stats[element.cle] || 0)));
      carte.appendChild(creerElement("span", "bilan-reprise-stat-libelle", text(element.label)));
      conteneur.appendChild(carte);
    });
  }

  function renderActivites(data) {
    var conteneur = document.getElementById("bilan-reprise-activites");
    conteneur.replaceChildren();
    if (!data.activites || !data.activites.length) {
      afficherVide(conteneur, text("noActivity"));
      return;
    }
    data.activites.forEach(function (item) { conteneur.appendChild(activiteFormatee(item)); });
  }

  function libelleEtatApprentissage(etat) {
    var map = {
      maitrise_confirmee: "mastery",
      solide_a_confirmer: "solid",
      en_consolidation: "consolidate",
      a_renforcer: "weak"
    };
    return text(map[etat] || "consolidate");
  }

  function renderApprentissages(data) {
    var conteneur = document.getElementById("bilan-reprise-apprentissages");
    conteneur.replaceChildren();
    if (!data.apprentissages || !data.apprentissages.length) {
      afficherVide(conteneur, data.has_learning_data ? text("noLearning") : text("noProgress"));
      return;
    }
    data.apprentissages.forEach(function (item) {
      var titre = [item.matiere, item.notion].filter(Boolean).join(" · ");
      var petit = format("{count} {label}", {
        count: Number(item.questions || 0),
        label: text("questions")
      });
      conteneur.appendChild(creerCarte(
        titre,
        "",
        libelleEtatApprentissage(item.etat),
        item.etat,
        item.date,
        petit
      ));
    });
  }

  function raisonRenforcement(item) {
    if (item.raison_code === "revision_due") return text("reasonDue");
    if (item.raison_code === "score_low") return format(text("reasonLow"), { score: item.score || 0 });
    if (item.raison_code === "repeated_errors") return format(text("reasonErrors"), { errors: item.erreurs || 0 });
    return format(text("reasonStabilize"), { score: item.score || 0 });
  }

  function renderRenforcer(data) {
    var conteneur = document.getElementById("bilan-reprise-renforcer");
    conteneur.replaceChildren();
    if (!data.renforcer || !data.renforcer.length) {
      afficherVide(conteneur, text("noStrengthen"));
      return;
    }
    data.renforcer.forEach(function (item) {
      var titre = [item.matiere, item.notion].filter(Boolean).join(" · ");
      conteneur.appendChild(creerCarte(
        titre,
        raisonRenforcement(item),
        String(item.score || 0) + " %",
        "a_renforcer",
        item.date,
        ""
      ));
    });
  }

  function objectifMission(mission) {
    if (mission.type === "toutes_confirmees") return text("objectiveAll");
    if (mission.type !== "active") return text("objectiveNew");
    if (mission.etape === "comprendre") return text("objectiveUnderstand");
    if (mission.etape === "verifier") return text("objectiveVerify");
    return text("objectivePractice");
  }

  function titreMission(mission) {
    if (mission.type === "toutes_confirmees") return text("missionAllTitle");
    if (mission.type !== "active") return text("missionNewTitle");
    return (TEXTES[language()].missionActiveTitle || TEXTES.fr.missionActiveTitle)[mission.etape] ||
      text("missionActiveTitle").pratiquer;
  }

  function methodeMission(mission) {
    if (mission.type === "toutes_confirmees") return text("objectiveAll");
    if (mission.type !== "active") return text("objectiveNew");
    if (mission.etape === "comprendre") return text("methodUnderstand");
    if (mission.etape === "verifier") return text("methodVerify");
    return text("methodPractice");
  }

  function libelleActionMission(mission, data) {
    if (!data.acces_ia || String(mission.lien || "").indexOf("/abonnement") === 0) return text("accessAction");
    if (mission.type === "toutes_confirmees") return text("actionAll");
    if (mission.type !== "active") return text("actionNew");
    if (mission.etape === "comprendre") return text("actionUnderstand");
    if (mission.etape === "verifier") return text("actionVerify");
    return text("actionPractice");
  }

  function renderMission(data) {
    var conteneur = document.getElementById("bilan-reprise-mission");
    conteneur.replaceChildren();
    var mission = data.mission || {};
    var carte = creerElement("div", "bilan-reprise-mission-carte");
    carte.appendChild(creerElement("h4", "", titreMission(mission)));

    var meta = creerElement("div", "bilan-reprise-mission-meta");
    if (mission.matiere) meta.appendChild(creerElement("span", "", mission.matiere));
    if (mission.notion) meta.appendChild(creerElement("span", "", mission.notion));
    if (mission.score != null) meta.appendChild(creerElement("span", "", String(mission.score) + " %"));
    if (meta.childNodes.length) carte.appendChild(meta);

    carte.appendChild(creerElement("p", "", objectifMission(mission)));
    carte.appendChild(creerElement("p", "", methodeMission(mission)));
    conteneur.appendChild(carte);

    mainAction.href = mission.lien || "/session-apprentissage";
    mainActionText.textContent = libelleActionMission(mission, data);
    mainAction.hidden = false;
  }

  function methodeFormatee(methode) {
    var mapping = {
      "Tuteur IA": ["methodTutorTitle", "methodTutorDesc"],
      "Quiz ciblé": ["methodQuizTitle", "methodQuizDesc"],
      "Fiches de révision": ["methodRevisionTitle", "methodRevisionDesc"],
      "Carte de connaissances": ["methodMapTitle", "methodMapDesc"],
      "Accès aux outils IA": ["methodAccessTitle", "methodAccessDesc"]
    };
    var cle = mapping[methode.titre] || [];
    var titre = cle[0] ? text(cle[0]) : (methode.titre || "");
    var description = cle[1] ? text(cle[1]) : (methode.description || "");
    var lien = creerElement("a", "bilan-reprise-outil");
    lien.href = methode.lien || "/mes-revisions";
    lien.appendChild(creerElement("strong", "", titre));
    lien.appendChild(creerElement("span", "", description));
    return lien;
  }

  function renderMethodes(data) {
    var conteneur = document.getElementById("bilan-reprise-methodes");
    conteneur.replaceChildren();
    (data.methodes || []).forEach(function (item) {
      conteneur.appendChild(methodeFormatee(item));
    });
  }

  function renderBilan(data, depart) {
    donneesCourantes = data;
    momentDepartCourant = depart || 0;
    aUnBilanPrecedentCourant = Boolean(data._a_un_bilan_precedent);
    appliquerTextesFixes();
    document.getElementById("bilan-reprise-periode").textContent = aUnBilanPrecedentCourant
      ? dureeDepuis(momentDepartCourant)
      : text("periodRecent");
    renderStats(data.stats || {});
    renderActivites(data);
    renderApprentissages(data);
    renderRenforcer(data);
    renderMission(data);
    renderMethodes(data);
  }

  function supprimerVerrouSiProprietaire(jeton) {
    try {
      if (window.localStorage.getItem(KEY_LOCK) === jeton) window.localStorage.removeItem(KEY_LOCK);
    } catch (_erreur) {}
  }

  function tenterOuvrirBilan(snapshotActivite, raison, lastSummary) {
    if (ouvert || tentativeOuverture || document.visibilityState === "prerender") return;
    var maintenant = Date.now();
    var recapPour = snapshotActivite > 0 ? String(snapshotActivite) : "0";

    if (raison === "nouvel-onglet" && lireNombre(KEY_SUMMARY_FOR) === snapshotActivite) return;
    var verrou = lireNombre(KEY_LOCK);
    if (verrou > maintenant) return;

    tentativeOuverture = true;
    jetonVerrou = String(maintenant + LOCK_MS);
    ecrire(KEY_LOCK, jetonVerrou);
    var depart = lastSummary || (snapshotActivite ? snapshotActivite - 24 * 60 * 60 * 1000 : maintenant - 24 * 60 * 60 * 1000);
    var url = endpoint + "?depuis=" + encodeURIComponent(String(depart));

    window.fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" }
    }).then(function (reponse) {
      if (!reponse.ok) throw new Error("bilan indisponible");
      return reponse.json();
    }).then(function (data) {
      if (!data || !data.stats || !data.mission) throw new Error("bilan incomplet");
      data._a_un_bilan_precedent = Boolean(lastSummary);
      renderBilan(data, depart);
      focusAvantOuverture = document.activeElement;
      ouvert = true;
      // Le bilan n'est marqué comme vu qu'à la fermeture explicite. Si
      // l'onglet est rechargé/fermé pendant son affichage, il sera reproposé.
      jetonVerrou = String(Date.now() + LOCK_MS);
      ecrire(KEY_LOCK, jetonVerrou);
      root.hidden = false;
      root.setAttribute("aria-hidden", "false");
      document.body.classList.add("bilan-reprise-ouvert");
      closeButton.focus({ preventScroll: true });
    }).catch(function () {
      // Le bilan reste réessayable au prochain affichage si l'API échoue.
      try { window.sessionStorage.removeItem(KEY_TAB); } catch (_erreur) {}
    }).finally(function () {
      tentativeOuverture = false;
      if (!ouvert) supprimerVerrouSiProprietaire(jetonVerrou);
    });
  }

  function fermerBilan() {
    if (!ouvert) return;
    ouvert = false;
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
    document.body.classList.remove("bilan-reprise-ouvert");
    var maintenant = Date.now();
    ecrire(KEY_ACTIVITY, maintenant);
    ecrire(KEY_SUMMARY, maintenant);
    ecrire(KEY_SUMMARY_FOR, maintenant);
    derniereEcritureActivite = maintenant;
    supprimerVerrouSiProprietaire(jetonVerrou);
    jetonVerrou = "";
    if (focusAvantOuverture && typeof focusAvantOuverture.focus === "function") {
      focusAvantOuverture.focus({ preventScroll: true });
    }
    focusAvantOuverture = null;
  }

  function enregistrerActivite(force) {
    if (ouvert || tentativeOuverture) return;
    var maintenant = Date.now();
    if (!force && maintenant - derniereEcritureActivite < ACTIVITY_WRITE_MS) return;
    ecrire(KEY_ACTIVITY, maintenant);
    derniereEcritureActivite = maintenant;
  }

  function verifierRetour(source) {
    if (ouvert || tentativeOuverture) return;
    var maintenant = Date.now();
    var derniere = lireNombre(KEY_ACTIVITY);
    if (!derniere) {
      enregistrerActivite(true);
      return;
    }
    var longuePause = maintenant - derniere >= QUIET_MS;
    var nouveauJour = dateLocaleKey(derniere) !== dateLocaleKey(maintenant);
    var nouvelleSessionOnglet = source === "chargement" && !ongletDejaActif;
    var bilanDepuisActivite = lireNombre(KEY_SUMMARY_FOR);
    var fermetureOuNouvelOnglet = nouvelleSessionOnglet && bilanDepuisActivite !== derniere;

    if (longuePause || nouveauJour || fermetureOuNouvelOnglet) {
      var raison = nouveauJour ? "nouveau-jour" : (longuePause ? "longue-pause" : "nouvel-onglet");
      tenterOuvrirBilan(derniere, raison, lireNombre(KEY_SUMMARY));
      return;
    }
    enregistrerActivite(true);
  }

  function evenementActivite() {
    if (ouvert) {
      // Maintient le verrou pendant que l'utilisateur lit/interagit avec le bilan.
      jetonVerrou = String(Date.now() + LOCK_MS);
      ecrire(KEY_LOCK, jetonVerrou);
      return;
    }
    if (tentativeOuverture || document.visibilityState !== "visible") return;
    verifierRetour("interaction");
    if (!ouvert && !tentativeOuverture) enregistrerActivite(false);
  }

  function lienActionClique(event) {
    var lien = event.target && event.target.closest ? event.target.closest("a[href]") : null;
    if (!lien || !root.contains(lien) || lien.hidden || !lien.href) return;
    event.preventDefault();
    var destination = lien.href;
    if (ouvert) fermerBilan();
    window.location.assign(destination);
  }

  function gererClavier(event) {
    if (!ouvert) return;
    if (event.key === "Escape") {
      event.preventDefault();
      fermerBilan();
      return;
    }
    if (event.key !== "Tab") return;
    var elements = Array.prototype.slice.call(dialog.querySelectorAll(
      'a[href]:not([hidden]), button:not([disabled]):not([hidden]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (element) { return element.offsetParent !== null; });
    if (!elements.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    var premier = elements[0];
    var dernier = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === premier) {
      event.preventDefault();
      dernier.focus();
    } else if (!event.shiftKey && document.activeElement === dernier) {
      event.preventDefault();
      premier.focus();
    }
  }

  var ongletDejaActif = false;
  try {
    ongletDejaActif = window.sessionStorage.getItem(KEY_TAB) === "1";
    window.sessionStorage.setItem(KEY_TAB, "1");
  } catch (_erreur) {}

  appliquerTextesFixes();
  if (closeButton) closeButton.addEventListener("click", fermerBilan);
  if (continueButton) continueButton.addEventListener("click", fermerBilan);
  root.addEventListener("click", function (event) {
    if (event.target && event.target.matches && event.target.matches("[data-bilan-fermer]")) fermerBilan();
    lienActionClique(event);
  });
  if (dialog) dialog.addEventListener("keydown", gererClavier);

  ["pointerdown", "keydown", "touchstart", "scroll"].forEach(function (nom) {
    document.addEventListener(nom, evenementActivite, { passive: true, capture: true });
  });
  window.addEventListener("pagehide", function () {
    if (!ouvert) return;
    // Fermer la page sans bouton de fermeture n'achève pas le bilan.
    ouvert = false;
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
    document.body.classList.remove("bilan-reprise-ouvert");
    supprimerVerrouSiProprietaire(jetonVerrou);
    jetonVerrou = "";
    try { window.sessionStorage.removeItem(KEY_TAB); } catch (_erreur) {}
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") verifierRetour("visibilite");
  });
  window.addEventListener("pageshow", function () {
    if (!ongletDejaActif) verifierRetour("chargement");
    else verifierRetour("visibilite");
  });
  if (languageSelect) {
    languageSelect.addEventListener("change", function () {
      if (donneesCourantes) renderBilan(donneesCourantes, momentDepartCourant);
      else appliquerTextesFixes();
    });
  }
  window.addEventListener("storage", function (event) {
    if (event.key === "mahay-langue" && donneesCourantes) renderBilan(donneesCourantes, momentDepartCourant);
  });

  // Premier chargement : initialise une trace locale. La première visite ne
  // déclenche pas de bilan; le retour suivant pourra comparer cette trace.
  if (!lireNombre(KEY_ACTIVITY)) {
    enregistrerActivite(true);
  } else {
    verifierRetour("chargement");
  }
})(window, document);
