/* Internationalisation progressive de Gasy Mahay : français + malagasy.
   La préférence reste locale au navigateur ; aucun service tiers ne reçoit de données.
   Les textes IA, les blocs de code et les contenus utilisateurs marqués comme tels
   ne sont jamais traduits automatiquement. */
(function (window, document) {
  "use strict";

  var CLE_LANGUE = "mahay-langue";
  var SELECTEUR = "#select-langue";
  var ATTRIBUTS_TRADUCTIBLES = ["aria-label", "title", "placeholder", "alt"];
  var ELEMENTS_PROTEGES = [
    "script", "style", "noscript", "pre", "code", "textarea",
    "[data-rendu]", ".ai-rendered-content", ".katex", ".gm-katex",
    ".gm-latex-fallback", "[data-no-translate]", "[contenteditable='true']"
  ].join(",");
  var TRADUCTIONS_MG = Object.freeze({
    "Langue": "Fiteny",
    "Choisir la langue": "Safidio ny fiteny",
    "Français": "Frantsay",
    "Tableau de bord": "Fijerena ankapobeny",
    "Apprendre": "Hianatra",
    "Documents": "Tahirin-kevitra",
    "Quiz IA": "Fanadinana IA",
    "Tuteur IA": "Mpampianatra IA",
    "Collaborer": "Hiara-miasa",
    "Mes cercles": "Vondrona ianarako",
    "Cercles d’étude": "Vondrona fianarana",
    "Classe virtuelle": "Kilasy virtoaly",
    "Compte": "Kaonty",
    "Notifications": "Fampandrenesana",
    "Mes révisions": "Famerenana lesona",
    "Défis & récompenses": "Fanamby sy valisoa",
    "Sécurité": "Fiarovana",
    "Securite": "Fiarovana",
    "Administration": "Fitantanana",
    "Premium": "Premium",
    "Abonnement": "Famandrihana",
    "Sponsoring": "Fanohanana",
    "Ressources": "Loharano",
    "Aide & Avis": "Fanampiana sy hevitra",
    "Mode d'emploi": "Torolalana",
    "Universités": "Oniversite",
    "Universites": "Oniversite",
    "À propos": "Momba anay",
    "A propos": "Momba anay",
    "Contact": "Fifandraisana",
    "Connexion": "Fidirana",
    "Inscription": "Fisoratana anarana",
    "Administrateur": "Mpandrindra",
    "Mon compte": "Kaontiko",
    "Actions rapides": "Hetsika haingana",
    "Mon espace": "Ny sehatra",
    "Mes documents": "Tahirin-kevitro",
    "Compte & aide": "Kaonty sy fanampiana",
    "Contacter Gasy Mahay": "Hifandray amin'i Gasy Mahay",
    "Se déconnecter": "Hivoaka",
    "Changer d'apparence": "Hanova endrika",
    "Agrandir la barre latérale": "Hanitatra ny bara",
    "Réduire la barre latérale": "Hampihena ny bara",
    "Apparence": "Endrika",
    "Clair": "Mazava",
    "Accueil": "Fandraisana",
    "Docs": "Tahiry",
    "Un mot a nous dire ?": "Misy hafatra ho anay?",
    "Un mot à nous dire ?": "Misy hafatra ho anay?",
    "Nous contacter": "Hifandray aminay",
    "Donner mon avis": "Hanome hevitra",
    "FAQ": "FAQ",
    "Bienvenue de retour": "Faly miarahaba anao indray",
    "Installer Gasy Mahay": "Hametraka an'i Gasy Mahay",
    "Un accès plus rapide depuis l’écran d’accueil de ton téléphone.": "Fidirana haingana kokoa avy amin'ny efijerin'ny findainao.",
    "Plus tard": "Amin'ny manaraka",
    "Installer": "Hametraka",
    "Confirmer": "Hamarino",
    "Annuler": "Hanafoana",
    "Retour": "Hiverina",
    "Continuer": "Tohizo",
    "Précédent": "Aloha",
    "Suivant": "Manaraka",
    "Fermer": "Hidio",
    "Ouvrir": "Sokafy",
    "Voir": "Asehoy",
    "Masquer": "Afeno",
    "Afficher": "Asehoy",
    "Enregistrer": "Tehirizo",
    "Modifier": "Hanova",
    "Supprimer": "Fafao",
    "Ajouter": "Hanampy",
    "Créer": "Hamorona",
    "Envoyer": "Alefaso",
    "Rechercher": "Hikaroka",
    "Filtrer": "Sivanina",
    "Télécharger": "Hisintona",
    "Partager": "Hizara",
    "Valider": "Hamarino",
    "Accepter": "Ekena",
    "Refuser": "Lavina",
    "Approuver": "Ankasitrahana",
    "Rejeter": "Lavina",
    "En attente": "Miandry",
    "Chargement…": "Eo am-pamaranana…",
    "Chargement...": "Eo am-pamaranana...",
    "Aucun résultat": "Tsy misy valiny",
    "Aucune donnée disponible": "Tsy misy angona",
    "Une erreur est survenue.": "Nisy hadisoana.",
    "Connexion — Gasy Mahay": "Fidirana — Gasy Mahay",
    "Inscription — Gasy Mahay": "Fisoratana anarana — Gasy Mahay",
    "Ton espace d’apprentissage": "Sehatra fianaranao",
    "Espace membre": "Sehatra ho an'ny mpikambana",
    "Retrouve ton rythme. Apprends avec les autres.": "Avereno ny gadonao. Mianara miaraka amin'ny hafa.",
    "Accède à tes documents, quiz, cercles d’étude et outils d’apprentissage depuis un espace pensé pour les étudiants malgaches.": "Midira amin'ny tahirin-kevitra, fanontaniana, vondrona fianarana ary fitaovana natao ho an'ny mpianatra malagasy.",
    "Documents et ressources pour réviser plus efficacement.": "Tahirin-kevitra sy loharano hanamora ny famerenana lesona.",
    "Quiz et accompagnement IA pour progresser étape par étape.": "Fanontaniana sy fanampiana IA handrosoana tsikelikely.",
    "Cercles d’étude et espaces de collaboration.": "Vondrona fianarana sy sehatra iaraha-miasa.",
    "Bienvenue à nouveau.": "Tongasoa indray.",
    "Connectez-vous avec votre numéro de téléphone et votre mot de passe.": "Midira amin'ny laharan-telefaoninao sy ny tenimiafinao.",
    "Mot de passe réinitialisé. Vous pouvez maintenant vous connecter.": "Naverina ny tenimiafina. Afaka miditra ianao izao.",
    "Numéro de téléphone": "Laharana finday",
    "Afficher le mot de passe": "Asehoy ny tenimiafina",
    "Masquer le mot de passe": "Afeno ny tenimiafina",
    "Utilisez le mot de passe associé à votre compte.": "Ampiasao ny tenimiafina mifandray amin'ny kaontinao.",
    "Mot de passe oublié ?": "Adino ny tenimiafina?",
    "Protection anti-abus active": "Mavitrika ny fiarovana amin'ny fanararaotana",
    "Pas encore de compte ?": "Tsy mbola manana kaonty?",
    "Créer mon espace Gasy Mahay": "Hamorona ny sehatra Gasy Mahay-ko",
    "Créer ton espace d’étude": "Hamorona ny sehatra fianaranao",
    "Un seul espace pour apprendre, réviser et collaborer.": "Sehatra iray hianarana, hamerenana lesona ary hiaraha-miasa.",
    "Crée ton compte en quelques étapes. Ton profil académique aide ensuite à organiser les ressources et les cercles autour de ton parcours.": "Mamoròna kaonty amin'ny dingana vitsivitsy. Ny mombamomba anao ara-pianarana dia hanampy handamina ireo loharano sy vondrona mifanaraka amin'ny fianaranao.",
    "Création de compte": "Famoronana kaonty",
    "Créer votre espace.": "Hamorona ny sehatrao.",
    "Quelques informations pour préparer votre compte et votre parcours.": "Antsipiriany vitsivitsy hanomanana ny kaontinao sy ny fianaranao.",
    "Progression de l’inscription": "Fandrosoan'ny fisoratana anarana",
    "Parcours": "Lalana",
    "Finaliser": "Hamita",
    "Votre compte": "Ny kaontinao",
    "Les informations de base pour vous identifier.": "Antsipiriany fototra hamantarana anao.",
    "Nom complet": "Anarana feno",
    "Ex. Rakoto Jean": "Ohatra: Rakoto Jean",
    "Utilisez le nom que vous souhaitez voir apparaître dans votre espace.": "Ampiasao ny anarana tianao hiseho ao amin'ny kaontinao.",
    "Saisissez 034 12 345 67, ou 34 12 345 67 si vous utilisez l’ancien format. Le serveur vérifie et normalise toujours le numéro.": "Ampidiro ny 034 12 345 67, na 34 12 345 67 raha ilay endrika taloha no ampiasainao. Hamarinin'ny rafitra foana ny laharana.",
    "Mot de passe": "Tenimiafina",
    "Commencez à saisir votre mot de passe.": "Atombohy ny fanoratana tenimiafina.",
    "Faible — ajoutez au moins 8 caractères.": "Malemy — ampio tarehintsoratra 8 farafahakeliny.",
    "Correct — ajoutez encore un peu de variété.": "Antonony — ampio karazana tarehintsoratra hafa.",
    "Solide — votre mot de passe est plus robuste.": "Matanjaka — azo antoka kokoa ny tenimiafina.",
    "Très solide.": "Tena matanjaka.",
    "8 à 72 caractères. Le contrôle visuel est indicatif ; la validation définitive reste côté serveur.": "Tarehintsoratra 8 ka hatramin'ny 72. Fanombanana fotsiny ity famantarana ity; ny mpizara no manao ny fanamarinana farany.",
    "Vous êtes": "Ianao dia",
    "Étudiant(e)": "Mpianatra",
    "Répétiteur / sponsor": "Mpampianatra fanampiny / mpanohana",
    "Les étudiants renseignent leur parcours académique. Les répétiteurs / sponsors créent un compte sans ces informations.": "Ny mpianatra no mameno ny mombamomba ny fianarany. Afaka mamorona kaonty tsy misy izany ny mpampianatra fanampiny sy ny mpanohana.",
    "Votre parcours académique": "Ny lalan'ny fianaranao",
    "Ces informations organisent les ressources et les cercles proposés.": "Ireo antsipiriany ireo dia mandamina ny loharano sy ny vondrona atolotra.",
    "Université": "Oniversite",
    "— Choisissez votre université —": "— Safidio ny oniversite —",
    "Composante / établissement": "Sampam-pianarana / toeram-pianarana",
    "— Choisissez d’abord votre université —": "— Safidio aloha ny oniversite —",
    "Mention": "Mention",
    "— Choisissez d’abord votre composante —": "— Safidio aloha ny sampam-pianarana —",
    "Niveau": "Ambaratonga",
    "— Choisissez d’abord votre mention —": "— Safidio aloha ny mention —",
    "Parcours / Filière": "Sampam-pianarana",
    "— Choisissez d’abord votre niveau —": "— Safidio aloha ny ambaratonga —",
    "Aucun parcours spécifique n’est nécessaire à ce niveau pour cette mention : vous êtes en tronc commun.": "Tsy mila sampam-pianarana manokana amin'ity ambaratonga ity; tronc commun ianao.",
    "Créer mon compte": "Hamorona kaonty",
    "Création protégée contre les abus automatisés": "Voaaro amin'ny fanararaotana mandeha ho azy ny fisoratana anarana",
    "Déjà inscrit(e) ?": "Efa manana kaonty?",
    "Se connecter": "Hiditra",
    "Les champs du parcours académique sont nécessaires uniquement pour les étudiants.": "Ny mombamomba ny fianarana dia takiana amin'ny mpianatra ihany.",
    "Ouvrir mon profil": "Sokafy ny mombamomba ahy",
    "Votre profil academique doit etre actualise pour utiliser correctement les cercles d'etudes.": "Mila havaozina ny mombamomba anao ara-pianarana mba hampiasana tsara ny vondrona fianarana.",
    "Actualiser maintenant": "Havaozy izao",
    "J'ai compris": "Azoko",
    "Un hub de revision imagine pour les étudiants à Madagascar.": "Sehatra famerenana lesona natao ho an'ny mpianatra eto Madagasikara.",
    "Mon profil & sécurité": "Ny mombamomba ahy sy ny fiarovana",
    "Profil académique": "Mombamomba ny fianarana",
    "Tableau blanc": "Solaitrabe",
    "Mon profil": "Ny mombamomba ahy",
    "Mot de passe actuel": "Tenimiafina ankehitriny",
    "Nouveau mot de passe": "Tenimiafina vaovao",
    "Confirmer le mot de passe": "Hamafiso ny tenimiafina",
    "Type de document": "Karazan-tahirin-kevitra",
    "Matière": "Taranja",
    "Année": "Taona",
    "Titre": "Lohateny",
    "Description": "Fanazavana",
    "Catégorie": "Sokajy",
    "Toutes les matières": "Ny taranja rehetra",
    "Tous les niveaux": "Ny ambaratonga rehetra",
    "Aucun document trouvé.": "Tsy nahitana tahirin-kevitra.",
    "Déposer un document": "Handefa tahirin-kevitra",
    "Glisser-déposer un document ici": "Apetraho eto ny tahirin-kevitra",
    "Approuver le document": "Ankasitraho ny tahirin-kevitra",
    "Rejeter le document": "Lavao ny tahirin-kevitra",
    "Rafraîchir": "Havaozy",
    "Actualiser": "Havaozy",
    "Aucun élément pour le moment.": "Tsy misy singa amin'izao fotoana izao.",
    "Voir le compte": "Hijery ny kaonty",
    "Nouveaux arrivants": "Mpikambana vaovao",
    "Abonnements étudiants": "Famandrihana ho an'ny mpianatra",
    "Statistiques": "Antontan'isa",
    "Diagnostics système": "Fizahana ny rafitra",
    "Centre de contrôle · Administration": "Foibe fanaraha-maso · Fitantanana",
    "Piloter Gasy Mahay sans perdre le fil.": "Tantano i Gasy Mahay nefa tsy very làlana.",
    "Référentiel académique": "Tahirin-kevitra momba ny fianarana",
    "Modération": "Fanaraha-maso",
    "Feedbacks": "Hevitra sy fanehoan-kevitra",
    "Mon espace d'apprentissage": "Ny sehatra fianarako",
    "Nouveau sur Gasy Mahay": "Vaovao amin'i Gasy Mahay",
    "Découvre le Tuteur IA, fais un quiz et rejoins ton cercle. En quelques minutes, tu auras déjà commencé ton parcours.": "Fantaro ny Mpampianatra IA, manaova quiz ary midira amin'ny vondrona fianaranao. Afaka minitra vitsy dia efa manomboka ny dianao ianao.",
    "Continuer mon parcours →": "Hanohy ny diako →",
    "Prêt à continuer ton apprentissage ?": "Vonona hanohy ny fianaranao ve ianao?",
    "Pret a continuer ton apprentissage ?": "Vonona hanohy ny fianaranao ve ianao?",
    "Chaque session te rapproche de ton objectif.": "Ny fotoana fianarana tsirairay dia mampanakaiky anao amin'ny tanjonao.",
    "Ta routine du jour": "Ny fandaharam-pianaranao anio",
    "Une petite session régulière vaut mieux qu'une longue session rare.": "Tsara kokoa ny mianatra kely nefa tsy tapaka, toy izay mianatra ela indraindray.",
    "2–5 min · Un mini quiz": "2–5 min · Quiz fohy",
    "Teste ce que tu sais déjà.": "Andramo izay efa fantatrao.",
    "Commencer →": "Hanomboka →",
    "5 min · Une ressource": "5 min · Loharano iray",
    "Relis une annale, une fiche ou un cours.": "Avereno vakina ny fanadinana taloha, ny famintinana na ny lesona iray.",
    "Voir les documents →": "Hijery ny tahirin-kevitra →",
    "3 min · Une interaction": "3 min · Fifandraisana iray",
    "Pose une question ou lis les échanges d’un cercle.": "Mametraha fanontaniana na vakio ny resaka ao amin'ny vondrona fianarana.",
    "Ouvrir mes cercles →": "Hanokatra ny vondrona ianarako →",
    "Marquer cette étape comme terminée": "Mariho fa vita ity dingana ity",
    "Routine terminée aujourd’hui. Bravo pour la régularité — à demain pour la prochaine session.": "Vita ny fandaharam-pianarana androany. Arahabaina amin'ny faharetana — mandra-pihaona rahampitso.",
    "Prochaine action recommandée": "Dingana manaraka atolotra",
    "Cette notion arrive à son échéance de révision espacée.": "Tonga ny fotoana hamerenana indray ity lesona ity.",
    "M'entraîner": "Hanao fanazaran-tena",
    "Transforme chaque session en progression : Tuteur, quiz, cercles et ressources partagées.": "Ataovy fandrosoana ny fotoana fianarana tsirairay: Mpampianatra IA, quiz, vondrona ary loharano ifampizarana.",
    "Carte des illusions": "Sarintanin'ny fahatsapana diso fa voafehy ny lesona",
    "Elle repère les notions où tu étais très sûr de toi alors que tes réponses étaient encore fragiles. C'est un signal de révision, pas un jugement sur tes capacités.": "Izy io dia mamantatra ny lesona natokisanao tena nefa mbola nisy fahadisoana ny valinteninao. Famantarana tokony hamerenana lesona izany, fa tsy fitsarana ny fahaizanao.",
    "Confiance ≠ maîtrise": "Fitokisana ≠ fahaizana",
    "signal de risque": "famantarana loza",
    "erreurs parmi les réponses très sûres": "fahadisoana tamin'ny valiny tena natokisana",
    "Déconstruire avec le Tuteur IA": "Handinika miaraka amin'ny Mpampianatra IA",
    "Vérifier avec un quiz": "Hanamarina amin'ny quiz",
    "Déconstruire la notion": "Handinika lalina ny lesona",
    "Vérifier avant de conclure": "Hanamarina alohan'ny hanapahana hevitra",
    "Tester le transfert": "Hitsapa ny fampiharana amin'ny toe-javatra hafa",
    "Une note élevée ne suffit pas : cette carte repère les notions où tu étais très sûr de toi alors que tes réponses étaient encore fragiles.": "Tsy ampy ny naoty ambony: fantarin'ity sarintany ity ny lesona natokisanao tena nefa mbola marefo ny valinteninao.",
    "Ce qui s'est passé pendant que tu n'étais pas là.": "Ireto ny zava-nitranga nandritra ny tsy naha-teo anao.",
    "Retrouve ici les événements importants liés à ton apprentissage et à tes cercles.": "Jereo eto ny zava-dehibe momba ny fianaranao sy ny vondrona ianaranao.",
    "Tout marquer comme lu": "Asio marika ho voavaky daholo",
    "Marquer comme lu": "Asio marika ho voavaky",
    "Tu es à jour": "Tsy misy lesona miandry",
    "Tu es à jour 🎉": "Tsy misy lesona miandry 🎉",
    "Aucune notification à afficher pour le moment.": "Tsy misy fampandrenesana aseho amin'izao fotoana izao.",
    "Centre de notifications": "Foiben'ny fampandrenesana",
    "Bibliothèque": "Tranombokin'ny loharano",
    "Bibliotheque": "Tranombokin'ny loharano",
    "Documents du cercle": "Tahirin-kevitry ny vondrona",
    "Deposer un document": "Handefa tahirin-kevitra",
    "Retour au salon": "Hiverina any amin'ny vondrona",
    "Document envoye — il sera visible ici une fois valide par un moderateur.": "Nalefa ny tahirin-kevitra — hiseho eto izy rehefa neken'ny mpandrindra.",
    "Document envoyé — il sera visible ici une fois validé par un modérateur.": "Nalefa ny tahirin-kevitra — hiseho eto izy rehefa neken'ny mpandrindra.",
    "Détection automatique appliquée : titre, matière, type, année et filière ont été analysés à partir du fichier. Le modérateur garde le dernier mot avant publication.": "Natao ny fanavahana mandeha ho azy: nodinihina ny lohateny, taranja, karazana, taona ary sampam-pianarana. Ny mpandrindra no manapa-kevitra farany alohan'ny hamoahana azy.",
    "Toutes les filières": "Ny sampam-pianarana rehetra",
    "Toutes les filieres": "Ny sampam-pianarana rehetra",
    "Toutes les matieres": "Ny taranja rehetra",
    "ex: Droit civil": "ohatra: Lalàna sivily",
    "Annales": "Fanadinana taloha",
    "Corriges": "Fanitsiana",
    "Corrige": "Fanitsiana",
    "Aucune ressource ici pour le moment": "Tsy mbola misy loharano eto",
    "La bibliothèque se construit avec les étudiants. Tu peux être le premier à partager une ressource que tu as le droit de diffuser.": "Miara-manorina ny tranombokin'ny loharano ny mpianatra. Afaka ianao no voalohany mizara loharano azonao zaraina ara-dalàna.",
    "Explorer les documents": "Hijery ny tahirin-kevitra",
    "Decouvrir les cercles": "Hahafantatra ny vondrona fianarana",
    "Découvrir les cercles": "Hahafantatra ny vondrona fianarana",
    "documents valides": "tahirin-kevitra nekena",
    "universites partenaires": "oniversite mpiara-miasa",
    "universités partenaires": "oniversite mpiara-miasa",
    "cercles actifs": "vondrona mavitrika",
    "quiz completes": "quiz vita",
    "quiz complétés": "quiz vita",
    "Dernieres entrees au registre": "Fampidirana farany tao amin'ny rejisitra",
    "Dernières entrées au registre": "Fampidirana farany tao amin'ny rejisitra",
    "Reference": "Laharana fanondroana",
    "Référence": "Laharana fanondroana",
    "Matiere": "Taranja",
    "Annee": "Taona",
    "Le registre est encore vide — soyez les premiers a deposer un document.": "Mbola foana ny rejisitra — aoka ianareo ho voalohany handefa tahirin-kevitra.",
    "Le registre est encore vide — soyez les premiers à déposer un document.": "Mbola foana ny rejisitra — aoka ianareo ho voalohany handefa tahirin-kevitra.",
    "Ne reste pas bloqué sur une notion.": "Aza mijanona rehefa misy lesona tsy azonao.",
    "Pose ta question avec ton contexte. Le Tuteur IA transforme ensuite la question en explication, exemple, exercice et correction pour t'aider à progresser.": "Lazao miaraka amin'ny toe-javatra misy anao ny fanontaniana. Avy eo ny Mpampianatra IA dia manome fanazavana, ohatra, fanazaran-tena ary fanitsiana hanampy anao handroso.",
    "Poser une question": "Hametraka fanontaniana",
    "Voir mes questions": "Hijery ny fanontaniako",
    "Faire un quiz": "Hanao quiz",
    "comprendre l'explication": "mahatakatra ny fanazavana",
    "voir un exemple concret": "mahita ohatra azo tsapain-tanana",
    "faire un exercice": "manao fanazaran-tena",
    "vérifier avec la correction": "manamarina amin'ny fanitsiana",
    "Ton parcours personnalisé": "Ny lalan'ny fianaranao manokana",
    "Commence par une notion qui te résiste": "Atombohy amin'ny lesona sarotra aminao",
    "Le Tuteur IA et le Quiz IA travaillent ici sur les mêmes difficultés détectées dans tes réponses.": "Ny Mpampianatra IA sy ny Quiz IA dia mifantoka eto amin'ireo fahasarotana hita tamin'ny valinteninao.",
    "Ton espace de question": "Sehatra hametrahana fanontaniana",
    "Décris ton blocage comme tu le ferais à un professeur. Plus le contexte est précis, plus la réponse peut être exploitable.": "Hazavao toy ny amin'ny mpampianatra ny olana sedrainao. Arakaraka ny maha-mazava ny toe-javatra dia vao mainka azo ampiasaina ny valiny.",
    "Expliquer une notion simplement": "Manazava lesona amin'ny fomba tsotra",
    "Comparer deux concepts": "Mampitaha hevitra roa",
    "Créer un exercice": "Mamorona fanazaran-tena",
    "Comprendre une erreur": "Mahatakatra fahadisoana",
    "Écris une question avant d'envoyer.": "Soraty aloha ny fanontaniana alohan'ny handefasana.",
    "Trop de questions rapprochées. Attends quelques instants avant de continuer.": "Betsaka loatra ny fanontaniana nalefa nifanesy. Miandrasa kely vao manohy.",
    "Ex. Explique-moi la comptabilité analytique et montre-moi comment raisonner sur un exercice de coûts complets.": "Ohatra: Hazavao ny kaonty analitika ary asehoy ny fomba famahana fanazaran-tena momba ny sanda feno.",
    "Évite les mots de passe, codes de sécurité ou informations personnelles sensibles. Utilise plutôt le nom du cours, le chapitre et la difficulté rencontrée.": "Aza manoratra tenimiafina, kaody fiarovana na mombamomba manokana saro-pady. Ampiasao kosa ny anaran'ny taranja, ny toko ary ny olana sedrainao.",
    "Apprendre avec les outils IA": "Mianatra amin'ny fitaovana IA",
    "Voir mon accès": "Hijery ny fahafahako miditra",
    "Générer mon quiz": "Hamorona quiz-ko",
    "Les matières proposées viennent des documents approuvés disponibles sur la plateforme.": "Avy amin'ny tahirin-kevitra nekena ato amin'ny sehatra ireo taranja atolotra.",
    "Ou préciser un autre sujet": "Na manorata lohahevitra hafa",
    "La matière libre prend la priorité lorsqu'elle est renseignée.": "Io taranja nosoratanao io no atao lohalaharana raha feno.",
    "Aucun quiz disponible.": "Tsy misy quiz azo ampiasaina.",
    "Aucun résultat pour le moment.": "Tsy mbola misy valiny.",
    "Réessayer": "Andramo indray",
    "Une réponse à la fois. Les corrections apparaissent après validation.": "Valiny iray isaky ny mandeha. Hiseho aorian'ny fanamarinana ny fanitsiana.",
    "Voir la correction": "Hijery ny fanitsiana",
    "Résultat": "Vokatra",
    "Historique": "Tantara",
    "Mon parcours": "Ny lalam-pianarako",
    "Prochaine mission": "Iraka manaraka"
  });

  var noeudsOriginaux = new WeakMap();
  var attributsOriginaux = new WeakMap();
  var langueActuelle = "fr";
  var initialise = false;

  function normaliser(texte) {
    return String(texte == null ? "" : texte)
      .normalize("NFC")
      .replace(/[\u00A0\u202F]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function traduireChaine(source, langue) {
    if (langue !== "mg") return source;
    var cle = normaliser(source);
    if (Object.prototype.hasOwnProperty.call(TRADUCTIONS_MG, cle)) {
      return TRADUCTIONS_MG[cle];
    }

    var match = cle.match(/^Tu n['’]as pas utilisé Gasy Mahay depuis (\d+) jours?\. Reprends ton apprentissage quand tu le souhaites\.?$/i);
    if (match) {
      return "Tsy nampiasa an'i Gasy Mahay nandritra ny " + match[1] + " andro ianao. Tohizo ny fianaranao rehefa vonona ianao.";
    }
    match = cle.match(/^Notifications\s*[·-]\s*(\d+)\s*non lues$/i);
    if (match) return "Fampandrenesana · " + match[1] + " mbola tsy novakiana";
    match = cle.match(/^Administration\s*[·-]\s*(\d+)\s*nouvelles?$/i);
    if (match) return "Fitantanana · " + match[1] + " vaovao";
    match = cle.match(/^(\d+)\s*j\.\s*inactif$/i);
    if (match) return match[1] + " andro tsy niasana";
    match = cle.match(/^(\d+)\s+jour(s?)\s+d'ancienneté$/i);
    if (match) return match[1] + " andro naha-mpikambana";

    // Les libellés qui contiennent une donnée dynamique gardent cette donnée
    // telle quelle (nom de l'étudiant, compteur ou score).
    match = cle.match(/^Bonjour,\\s+(.+?)\\s*👋$/i);
    if (match) return "Manao ahoana, " + match[1] + " 👋";
    match = cle.match(/^Ton démarrage est à (\\d+)\\/3\\.$/i);
    if (match) return "Efa vita ny dingana " + match[1] + " amin'ny 3.";
    match = cle.match(/^(\\d+)\\/3 aujourd'hui$/i);
    if (match) return match[1] + "/3 androany";
    match = cle.match(/^Cette notion a encore (\\d+) erreurs? à consolider\\.$/i);
    if (match) return "Mbola misy fahadisoana " + match[1] + " mila hamafisina amin'ity lesona ity.";
    match = cle.match(/^Prochaine action : (Déconstruire la notion|Vérifier avant de conclure|Tester le transfert)$/i);
    if (match) {
      var actions = {
        "déconstruire la notion": "Handinika lalina ny lesona",
        "vérifier avant de conclure": "Hanamarina alohan'ny hanapahana hevitra",
        "tester le transfert": "Hitsapa ny fampiharana amin'ny toe-javatra hafa"
      };
      return "Dingana manaraka: " + actions[match[1].toLowerCase()];
    }
    match = cle.match(/^maîtrise actuelle · (\\d+)%$/i);
    if (match) return "Fahaizana ankehitriny · " + match[1] + "%";
    match = cle.match(/^(\\d+)\\s+documents consultés$/i);
    if (match) return match[1] + " tahirin-kevitra nojerena";
    match = cle.match(/^(\\d+)\\s+quiz récents$/i);
    if (match) return match[1] + " quiz vao haingana";
    match = cle.match(/^(\\d+)\\s+sessions? tuteur$/i);
    if (match) return match[1] + " fotoam-pianarana niaraka tamin'ny Mpampianatra IA";
    match = cle.match(/^(\\d+) erreurs? avec une forte confiance sur (\\d+) questions? très sûres?\\.$/i);
    if (match) {
      return match[1] + " valiny diso nefa natokisana, tamin'ny fanontaniana " + match[2] + " tena natokisana.";
    }
    match = cle.match(/^(\\d+) réponses? très sûres?$/i);
    if (match) return "Valiny " + match[1] + " tena natokisana";
    match = cle.match(/^(\\d+) observations? au total$/i);
    if (match) return "Fanamarihana " + match[1] + " amin'ny fitambarany";
    return source;
  }

  function estProtege(element) {
    return Boolean(element && element.closest && element.closest(ELEMENTS_PROTEGES));
  }

  function traduireNoeudTexte(noeud, langue) {
    if (!noeud || noeud.nodeType !== 3 || estProtege(noeud.parentElement)) return;
    if (!noeudsOriginaux.has(noeud)) noeudsOriginaux.set(noeud, noeud.nodeValue || "");
    var source = noeudsOriginaux.get(noeud);
    var traduction = traduireChaine(source, langue);
    if (noeud.nodeValue !== traduction) noeud.nodeValue = traduction;
  }

  function traduireAttributs(element, langue) {
    if (!element || element.nodeType !== 1 || estProtege(element)) return;
    var originaux = attributsOriginaux.get(element);
    if (!originaux) {
      originaux = Object.create(null);
      attributsOriginaux.set(element, originaux);
    }
    ATTRIBUTS_TRADUCTIBLES.forEach(function (nom) {
      if (!element.hasAttribute(nom)) return;
      if (!Object.prototype.hasOwnProperty.call(originaux, nom)) {
        originaux[nom] = element.getAttribute(nom);
      }
      var source = originaux[nom];
      var traduction = traduireChaine(source, langue);
      if (element.getAttribute(nom) !== traduction) element.setAttribute(nom, traduction);
    });
  }

  function traduireSousArbre(racine, langue) {
    if (!racine) return;
    if (racine.nodeType === 3) {
      traduireNoeudTexte(racine, langue);
      return;
    }
    if (racine.nodeType === 1 && estProtege(racine)) return;

    if (racine.nodeType === 1) traduireAttributs(racine, langue);
    if (racine.querySelectorAll) {
      racine.querySelectorAll("*").forEach(function (element) {
        traduireAttributs(element, langue);
      });
    }

    var walker = document.createTreeWalker(racine, window.NodeFilter.SHOW_TEXT);
    var noeud;
    while ((noeud = walker.nextNode())) traduireNoeudTexte(noeud, langue);
  }

  function lireLangue() {
    try {
      return window.localStorage.getItem(CLE_LANGUE) === "mg" ? "mg" : "fr";
    } catch (_erreur) {
      return "fr";
    }
  }

  function appliquerLangue(langue, memoriser) {
    langueActuelle = langue === "mg" ? "mg" : "fr";
    document.documentElement.setAttribute("lang", langueActuelle);
    var selecteur = document.querySelector(SELECTEUR);
    if (selecteur && selecteur.value !== langueActuelle) selecteur.value = langueActuelle;
    if (memoriser) {
      try {
        window.localStorage.setItem(CLE_LANGUE, langueActuelle);
      } catch (_erreur) {
        // Le sélecteur reste utilisable si le stockage est désactivé.
      }
    }
    traduireSousArbre(document.documentElement, langueActuelle);
  }

  function initialiser() {
    if (initialise) return;
    initialise = true;
    var selecteur = document.querySelector(SELECTEUR);
    if (selecteur) {
      selecteur.addEventListener("change", function () {
        appliquerLangue(selecteur.value, true);
      });
    }

    appliquerLangue(lireLangue(), false);

    if (typeof window.MutationObserver === "function" && document.body) {
      var observateur = new window.MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
          mutation.addedNodes.forEach(function (ajoute) {
            traduireSousArbre(ajoute, langueActuelle);
          });
        });
      });
      observateur.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser, { once: true });
  } else {
    initialiser();
  }
})(window, document);
