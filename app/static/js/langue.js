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
    "Accès Premium · étudiant": "Fidirana Premium · mpianatra",
    "Ton abonnement, ton état d'accès, ton prochain pas.": "Ny famandrihanao, ny satan'ny fidiranao ary ny dingana manaraka.",
    "Visualise ton essai, ton abonnement actuel et envoie une demande de paiement depuis un espace unique.": "Jereo eto ny fotoam-pitsapanao sy ny famandrihanao ankehitriny, ary alefaso eto ny fangatahana fandoavam-bola.",
    "Sécurité du compte": "Fiarovana ny kaonty",
    "jours Premium restants": "andro Premium sisa",
    "jours d'IA restants": "andro sisa ahafahana mampiasa ny IA",
    "état actuel de l'accès": "satan'ny fidirana ankehitriny",
    "Demande envoyée. Un administrateur vérifiera ton paiement.": "Nalefa ny fangatahanao. Hamarinin'ny mpitantana ny fandoavam-bola.",
    "Cette fonctionnalité nécessite Premium. Vérifie ton abonnement ou envoie une demande ci-dessous.": "Mila Premium ity fampiasa ity. Jereo ny famandrihanao na mandefasa fangatahana etsy ambany.",
    "Le Quiz IA et le Tuteur IA sont inclus pendant les": "Tafiditra ao anatin'ny",
    "premiers jours de l'essai. Le reste des fonctionnalités Premium reste accessible pendant": "andro voalohan'ny andrana ny Quiz IA sy ny Tuteur IA. Mbola azo ampiasaina mandritra ny",
    "jours.": "andro ny fampiasa Premium hafa.",
    "État de ton compte": "Satan'ny kaontinao",
    "Essai gratuit": "Andrana maimaim-poana",
    "terminé": "tapitra",
    "Il te reste": "Mbola manana",
    "d'accès Premium.": "andro ahafahana miditra amin'ny Premium.",
    "La période d'essai IA est terminée ; les autres fonctionnalités Premium restent accessibles pendant l'essai de 60 jours. Ton essai est terminé. Tu peux souscrire ci-dessous.": "Tapitra ny andrana IA; mbola azo ampiasaina mandritra ny 60 andro ny fampiasa Premium hafa. Tapitra ny andranao. Afaka misoratra anarana etsy ambany ianao.",
    "Demande en cours de vérification": "Eo am-panamarinana ny fangatahana",
    "La demande a bien été reçue.": "Voaray tsara ny fangatahanao.",
    "Ton accès Premium reste actif pendant la vérification (": "Mbola mandeha ny fidiranao Premium mandritra ny fanamarinana ( ",
    "L'accès IA reste ouvert pendant": "Mbola azo ampiasaina ny IA mandritra ny",
    "Abonnement expiré": "Tapitra ny famandrihana",
    "Ton accès Premium peut être réactivé avec une nouvelle demande.": "Afaka averina alefa ny fidiranao Premium amin'ny alalan'ny fangatahana vaovao.",
    "Demande refusée": "Nolavina ny fangatahana",
    "Motif :": "Antony :",
    "Tu peux envoyer une nouvelle demande.": "Afaka mandefa fangatahana vaovao ianao.",
    "jours restants": "andro sisa",
    "Tarif actuel": "Sarany ankehitriny",
    "Premium étudiant": "Premium ho an'ny mpianatra",
    "Une demande correspond à un mois d'accès. Le montant actuel de la plateforme est affiché ci-dessous.": "Ny fangatahana iray dia mifanaraka amin'ny fidirana mandritra ny iray volana. Aseho etsy ambany ny sarany ankehitriny.",
    "Ar / mois": "Ar / volana",
    "Après paiement": "Rehefa avy nandoa",
    "Choisis le moyen utilisé, ajoute la référence si disponible et joins la preuve si tu en as une.": "Safidio ny fomba fandoavam-bola nampiasainao, ampio ny laharana fanondroana raha misy, ary apetaho ny porofo raha anananao.",
    "Nouvelle demande": "Fangatahana vaovao",
    "Envoyer mon paiement": "Handefa ny fandoavako",
    "Moyen de paiement": "Fomba fandoavam-bola",
    "Virement bancaire": "Famindram-bola amin'ny banky",
    "Référence de transaction": "Laharan'ny fifampiraharahana",
    "Preuve de paiement": "Porofo momba ny fandoavam-bola",
    "Capture ou PDF selon les formats autorisés.": "Pikantsary na PDF araka ny endrika ekena.",
    "Envoyer ma demande": "Handefa ny fangatahako",
    "Compte · sécurité & profil": "Kaonty · fiarovana sy mombamomba",
    "Protéger ton compte sans chercher les réglages.": "Arovy ny kaontinao nefa tsy mila mikaroka ny fanovana.",
    "Gère ton mot de passe, ton email de récupération, la double authentification, ta photo et ton parcours académique depuis une seule page.": "Tantano amin'ny pejy iray ny tenimiafinao, ny mailaka fanarenana, ny fanamarinana indroa, ny sarinao ary ny mombamomba ny fianaranao.",
    "Écran de connexion": "Ecran fidirana",
    "Le score est un repère visuel basé sur les protections configurées, pas une garantie absolue.": "Famantarana hita maso mifototra amin'ny fiarovana napetraka ny isa, fa tsy antoka tanteraka.",
    "Email de récupération": "Mailaka fanarenana",
    "Double authentification": "Fanamarinana indroa",
    "Profil personnalisé": "Mombamomba manokana",
    "Double authentification désactivée.": "Tsy mandeha ny fanamarinana indroa.",
    "Modification enregistrée.": "Voatahiry ny fanovana.",
    "Ton identité": "Ny mombamomba anao",
    "Ces éléments servent à identifier ton compte et à personnaliser les espaces collaboratifs.": "Ireo antsipiriany ireo dia ampiasaina hamantarana ny kaontinao sy hanamboarana ny sehatra iarahana.",
    "Aucune adresse configurée": "Tsy mbola misy adiresy napetraka",
    "Adresse email": "Adiresy mailaka",
    "Activité du compte": "Hetsika ao amin'ny kaonty",
    "Le compteur mesure le nombre de jours complets depuis ta dernière utilisation du site.": "Manisa ny andro feno hatramin'ny nampiasanao farany ny tranonkala ity kaontera ity.",
    "jour d'inactivité": "andro tsy nampiasana",
    "Ton compte est actuellement utilisé. Une notification est créée lors de la prochaine connexion après 3 jours ou plus d'absence.": "Ampiasaina amin'izao fotoana izao ny kaontinao. Hisy fampandrenesana rehefa miditra indray ianao rehefa tsy nampiasa azy nandritra ny 3 andro na mihoatra.",
    "Dernière activité :": "Hetsika farany :",
    "Un code supplémentaire est demandé à la connexion lorsque la 2FA est active.": "Hangatahana kaody fanampiny rehefa miditra raha mandeha ny 2FA.",
    "2FA active": "Mandeha ny 2FA",
    "code de secours restant": "kaody famonjena sisa",
    "Régénérer les codes": "Mamorona kaody vaovao",
    "Mot de passe pour confirmer la désactivation": "Tenimiafina hanamafisana ny fanafoanana",
    "Désactiver la 2FA": "Atsaharo ny 2FA",
    "2FA désactivée": "Tsy mandeha ny 2FA",
    "Active-la pour renforcer la connexion.": "Alefaso izany mba hanamafisana ny fiarovana amin'ny fidirana.",
    "Activer la 2FA": "Alefaso ny 2FA",
    "Photo de profil": "Sarin'ny mombamomba",
    "La photo est visible dans les espaces où ton profil apparaît.": "Hita amin'ireo sehatra isehoan'ny mombamomba anao ny sary.",
    "Choisir une photo · JPG, PNG ou WEBP · 5 Mo max": "Misafidiana sary · JPG, PNG na WEBP · 5 Mo fara-fahabetsany",
    "Mettre à jour la photo": "Havaozy ny sary",
    "Supprimer la photo": "Fafao ny sary",
    "Le mot de passe est votre première ligne de défense. Un nouveau mot de passe invalide aussi les anciennes sessions lorsque le système le détecte.": "Ny tenimiafina no fiarovana voalohany amin'ny kaontinao. Raha ovaina izy dia foanana koa ireo fidirana taloha rehefa hitan'ny rafitra izany.",
    "Ce compte utilise un mot de passe temporaire. Il doit être remplacé.": "Mampiasa tenimiafina vonjimaika ity kaonty ity. Tsy maintsy soloina izany.",
    "Changer le mot de passe": "Hanova ny tenimiafina",
    "À propos de moi": "Momba ahy",
    "Une courte présentation affichée dans certains espaces collaboratifs.": "Fampahafantarana fohy aseho amin'ny sehatra iarahana sasany.",
    "Parcours académique": "Mombamomba ny fianarana",
    "Ton parcours sert à contextualiser les ressources et les cercles.": "Ny mombamomba ny fianaranao dia manampy hampifanaraka ny loharano sy ny vondrona amin'ny fianaranao.",
    "Ton profil académique doit être actualisé pour correspondre correctement aux cercles.": "Tokony havaozina ny mombamomba ny fianaranao mba hifanaraka tsara amin'ny vondrona.",
    "Composante": "Sampam-pianarana",
    "Actualisation": "Fanavaozana",
    "La mention et le parcours se changent via une demande administrateur lorsque c'est requis.": "Ovaina amin'ny alalan'ny fangatahana amin'ny mpitantana ny sampana sy ny lalam-pianarana rehefa ilaina izany.",
    "Choisir mon université": "Hisafidy ny oniversitako",
    "Modifier mon niveau": "Hanova ny ambaratongam-pianarako",
    "Actualiser mon parcours académique": "Havaozy ny mombamomba ny fianarako",
    "Partenariat · visibilité étudiante": "Fiaraha-miasa · fahitana eo amin'ny mpianatra",
    "Présente ton activité à la communauté Gasy Mahay.": "Ampahafantaro ny vondrom-piarahamonina Gasy Mahay ny asanao.",
    "L'espace sponsor permet aux répétiteurs, commerces et services de proposer un partenariat. Le prix n'est pas affiché publiquement : la demande est étudiée puis négociée.": "Ny sehatra mpanohana dia ahafahan'ny mpampianatra mpanampy, ny fivarotana ary ny tolotra mangataka fiaraha-miasa. Tsy aseho ampahibemaso ny vidiny: dinihina ary ifampiraharahana ny fangatahana.",
    "Comprendre la plateforme": "Fantaro ny sehatra",
    "durée d'un partenariat activé": "faharetan'ny fiaraha-miasa mavitrika",
    "demande de contact avant négociation": "fangatahana fifandraisana alohan'ny fifampiraharahana",
    "Demande envoyée. Nous te recontacterons pour discuter du partenariat.": "Nalefa ny fangatahanao. Hifandray aminao indray izahay hiresaka momba ny fiaraha-miasa.",
    "Ce que le partenariat apporte": "Tombontsoa azo avy amin'ny fiaraha-miasa",
    "Une visibilité mieux structurée.": "Fahitana voalamina kokoa.",
    "Vérifié": "Voamarina",
    "Présence auprès des étudiants": "Fisiana eo anivon'ny mpianatra",
    "Ton activité peut être mise en avant dans les espaces prévus par la plateforme.": "Azo asongadina amin'ireo sehatra natokana amin'izany ny asanao.",
    "Badge et mise en avant": "Marika sy fampisongadinana",
    "Selon les fonctionnalités actives du partenariat, un badge vérifié et une meilleure visibilité peuvent être appliqués.": "Arakaraka ny fampiasa tafiditra amin'ny fiaraha-miasa dia mety hisy marika voamarina sy fahitana tsara kokoa.",
    "Tarif négocié": "Sarany nifampiraharahana",
    "Le prix et le moyen de paiement sont définis avec l'équipe, puis saisis par un administrateur.": "Faritana miaraka amin'ny ekipa ny vidiny sy ny fomba fandoavam-bola, ary ampidirin'ny mpitantana.",
    "Premier contact": "Fifandraisana voalohany",
    "Parler de ton activité": "Hiresaka momba ny asanao",
    "Présente ton activité et ton besoin": "Lazao ny asanao sy izay ilainao",
    "2 000 caractères maximum.": "Tarehintsoratra 2 000 farafahabetsany.",
    "Connecte-toi pour enregistrer une demande de contact sponsor.": "Midira mba handefasana fangatahana fifandraisana momba ny fanohanana.",
    "Comment ça se passe ?": "Ahoana ny fizotrany?",
    "Tu présentes ton activité et ce que tu recherches.": "Lazao ny asanao sy izay tadiavinao.",
    "L'équipe prend contact avec toi et définit les modalités.": "Hifandray aminao ny ekipa ary hamaritra ny fepetra.",
    "L'activation": "Ny fampandehanana",
    "Le partenariat est activé par un administrateur après accord.": "Alefan'ny mpitantana ny fiaraha-miasa rehefa vita ny fifanarahana.",
    "Guide officiel · Gasy Mahay": "Torolalana ofisialy · Gasy Mahay",
    "Apprendre à utiliser le site, étape par étape.": "Ianaro tsikelikely ny fomba fampiasana ny tranonkala.",
    "Ce guide te montre le chemin le plus simple dans Gasy Mahay : créer ton compte, retrouver une ressource, pratiquer, utiliser l'IA, travailler en groupe et sécuriser ton compte. Il précise aussi les durées d'accès de l'essai gratuit pour éviter toute mauvaise surprise.": "Ity torolalana ity dia mampiseho ny fomba mora indrindra hampiasana an'i Gasy Mahay: mamorona kaonty, mitady loharano, manao fanazaran-tena, mampiasa IA, miara-mianatra ary miaro kaonty. Hazavainy koa ny faharetan'ny fidirana amin'ny andrana maimaim-poana.",
    "Commencer le parcours": "Hanomboka ny fianarana",
    "Voir la carte du site": "Hijery ny sarin'ny tranonkala",
    "Questions fréquentes": "Fanontaniana apetraka matetika",
    "grandes étapes expliquées": "dingana lehibe hazavaina",
    "parcours fonctionnels visualisés": "fizotran'ny fampiasana aseho",
    "essai gratuit pour les autres fonctions Premium": "fotoana andrana maimaim-poana ho an'ny fampiasa Premium hafa",
    "Démarrage express": "Fanombohana haingana",
    "Tu ne sais pas par où commencer ?": "Tsy fantatrao izay hanombohana?",
    "Choisis ton objectif et suis seulement le parcours dont tu as besoin.": "Safidio ny tanjonao ary araho ny dingana mifanaraka amin'izay ilainao.",
    "Je cherche un cours": "Mitady lesona aho",
    "Documents → filtres → ressource → révision.": "Tahirin-kevitra → sivana → loharano → famerenana lesona.",
    "Je veux m'entraîner": "Te hanao fanazaran-tena aho",
    "Quiz IA pour pratiquer, Tuteur IA pour débloquer une notion.": "Quiz IA hanaovana fanazaran-tena, Tuteur IA hanampy amin'ny lesona sarotra.",
    "Je veux travailler en groupe": "Te hiara-miasa amin'ny vondrona aho",
    "Cercles d'étude, messages et partage de ressources.": "Vondrona fianarana, hafatra ary fifampizarana loharano.",
    "Je veux sécuriser mon compte": "Te hiaro ny kaontiko aho",
    "Mot de passe, récupération, 2FA et accès Premium.": "Tenimiafina, fanarenana, 2FA ary fidirana Premium.",
    "Démarrer": "Hanomboka",
    "Naviguer": "Hivezivezy",
    "Chercher, consulter et déposer des ressources.": "Mitady, mijery ary mametraka loharano.",
    "Quiz IA et Tuteur IA.": "Quiz IA sy Tuteur IA.",
    "Rejoindre, participer et partager.": "Miditra, mandray anjara ary mizara.",
    "Cours, séances, devoirs et tableau blanc.": "Lesona, fivoriana, enti-mody ary takelaka fotsy.",
    "Profil, 2FA et mot de passe oublié.": "Mombamomba, 2FA ary tenimiafina hadino.",
    "Diagnostic rapide et solutions.": "Fanamarinana haingana sy vahaolana.",
    "Créer ton compte et démarrer": "Mamorona kaonty ary manomboka",
    "Le premier parcours est volontairement simple : tu crées ton identité, puis ton profil académique si tu es étudiant.": "Natao ho tsotra ny dingana voalohany: mamorona ny mombamomba anao ianao, ary mameno ny mombamomba ny fianarana raha mpianatra.",
    "Ouvre": "Sokafy",
    "choisis ton rôle et renseigne ton nom, ton numéro et ton mot de passe.": "safidio ny anjara asanao ary ampidiro ny anaranao, ny laharan-telefaoninao ary ny tenimiafinao.",
    "Utilise le numéro associé à ton compte, dans le format accepté par la page de connexion.": "Ampiasao ny laharana mifandray amin'ny kaontinao, amin'ny endrika eken'ny pejy fidirana.",
    "Retourne sur": "Miverena any amin'ny",
    "Si le 2FA est activé, un deuxième écran demande le code.": "Raha mandeha ny 2FA, dia mangataka kaody ny efijery faharoa.",
    "Important pour les anciens comptes": "Zava-dehibe ho an'ny kaonty taloha",
    "Les anciens comptes peuvent conserver leur format historique ; la page de connexion normalise le numéro avant la vérification.": "Mety mbola hampiasa ny endrika laharana taloha ny kaonty tranainy; ahitsy amin'ny endrika ekena ny laharana alohan'ny fanamarinana rehefa miditra.",
    "Comprendre la navigation": "Mahafantatra ny fitetezana",
    "Le menu de gauche regroupe les fonctions par objectif. Sur mobile, le menu est adapté à un écran plus petit.": "Manangona ny fampiasa araka ny tanjona ny menio eo ankavia. Ahitsy amin'ny efijery kely kokoa ny menio amin'ny finday.",
    "reprendre une activité": "hanohy hetsika",
    "voir ses documents": "hijery ny tahirin-kevitra",
    "suivre ses quiz": "hanaraka ny quiz",
    "Documents, Quiz IA et Tuteur IA sont regroupés ici. Commence par les documents si tu veux travailler à partir de tes supports de cours.": "Eto no misy ny Documents, Quiz IA ary Tuteur IA. Atombohy amin'ny tahirin-kevitra raha te hianatra amin'ny lesona anananao ianao.",
    "Cercles d'étude et Classe virtuelle servent à travailler avec d'autres étudiants ou avec un professeur.": "Ny vondrona fianarana sy ny kilasy virtoaly dia ahafahana miara-miasa amin'ny mpianatra hafa na mpampianatra.",
    "Sécurité, abonnement, sponsoring, universités, FAQ, contact et ce mode d'emploi sont accessibles depuis le menu.": "Azo sokafana avy amin'ny menio ny fiarovana, famandrihana, fanohanana, oniversite, FAQ, fifandraisana ary ity torolalana ity.",
    "Utiliser les documents": "Fampiasana ny tahirin-kevitra",
    "Les documents approuvés constituent la bibliothèque de ressources. Un document en attente de modération n'est pas encore public.": "Ireo tahirin-kevitra nekena no mamorona ny tranombokin'ny loharano. Tsy mbola ampahibemaso ny tahirin-kevitra miandry fanamarinana.",
    "Pour chercher une ressource": "Hitady loharano",
    "Utilise la filière, la matière, le type de document ou le cercle pour affiner.": "Ampiasao ny lalam-pianarana, taranja, karazana tahirin-kevitra na vondrona mba hanivanana ny valiny.",
    "Ouvre le document voulu pour le consulter.": "Sokafy ilay tahirin-kevitra tianao hojerena.",
    "Un document approuvé peut être téléchargé selon les règles d'accès de son cercle.": "Azo sintonina ny tahirin-kevitra nekena arakaraka ny fitsipiky ny vondrona misy azy.",
    "Pour déposer un document": "Hametraka tahirin-kevitra",
    "Ouvre la page de dépôt de documents.": "Sokafy ny pejy fametrahana tahirin-kevitra.",
    "Renseigne le titre, la matière, l'année et la filière.": "Fenoy ny lohateny, taranja, taona ary lalam-pianarana.",
    "Choisis éventuellement un cercle.": "Safidio koa ny vondrona raha ilaina.",
    "Ajoute le fichier autorisé puis envoie-le.": "Ampidiro ny rakitra ekena ary alefaso.",
    "Le document passe ensuite par la modération avant d'être public.": "Hamarinin'ny mpandrindra aloha ilay tahirin-kevitra vao aseho ampahibemaso.",
    "Un support PDF ou un autre format autorisé par la plateforme.": "Rakitra PDF na endrika hafa eken'ny sehatra.",
    "Ajoute les informations pédagogiques pour que la ressource soit facilement retrouvée.": "Ampio ny antsipirian'ny fianarana mba ho mora hita ilay loharano.",
    "Le document reste en attente tant qu'un administrateur ne l'a pas approuvé.": "Miandry ilay tahirin-kevitra mandra-pankatoavan'ny mpitantana azy.",
    "Une fois approuvé, il rejoint la bibliothèque publique ou le cercle concerné.": "Rehefa nekena dia tafiditra ao amin'ny tranomboky ampahibemaso na ny vondrona mifandraika aminy.",
    "Quiz IA et Tuteur IA sont deux usages différents : l'un mesure et entraîne tes connaissances, l'autre t'accompagne dans ton raisonnement.": "Samy hafa ny fampiasana ny Quiz IA sy Tuteur IA: ny iray mandrefy sy mampiofana ny fahalalanao, ny iray kosa manampy anao handinika.",
    "Choisis un quiz ou génère un quiz à partir d'un document disponible.": "Misafidiana quiz na mamoròna quiz avy amin'ny tahirin-kevitra misy.",
    "Réponds aux questions une par une.": "Valio tsirairay ny fanontaniana.",
    "Soumets la tentative pour obtenir le résultat.": "Alefaso ny valinao mba hahazoana ny vokatra.",
    "Le tableau de bord peut ensuite afficher les quiz réellement terminés.": "Asehon'ny tabilao ankapobeny avy eo ireo quiz tena vita.",
    "Pose une question liée à ton travail.": "Mametraha fanontaniana mifandray amin'ny fianaranao.",
    "Donne suffisamment de contexte pour obtenir une réponse utile.": "Omeo fanazavana ampy mba hahazoana valiny mahasoa.",
    "Utilise l'explication pour comprendre, puis vérifie avec ton cours.": "Ampiasao ny fanazavana mba hahatakatra, ary hamarino amin'ny lesonao.",
    "Évite d'utiliser l'IA comme seule source pour une décision académique importante.": "Aza miantehitra amin'ny IA irery amin'ny fanapahan-kevitra lehibe momba ny fianarana.",
    "À retenir sur l'essai gratuit": "Tsarovy momba ny andrana maimaim-poana",
    "pour un nouvel étudiant. Les autres fonctionnalités Premium restent accessibles pendant": "ho an'ny mpianatra vaovao. Mbola azo ampiasaina mandritra ny",
    "Un abonnement payant actif réouvre l'accès IA pendant sa période de validité.": "Ny famandrihana voaloa sy mbola manan-kery dia mamerina ny fidirana amin'ny IA mandritra ny fe-potoana.",
    "Un tableau de bord pensé pour répondre à une question simple :": "Tabilao natao hamaliana fanontaniana tsotra:",
    "qu'est-ce que je dois travailler maintenant ?": "inona no tokony hianarako izao?",
    "Priorité du jour": "Laharam-pahamehana androany",
    "notion à revoir": "lesona tokony haverina",
    "Commence par tes points faibles, puis consolide ce que tu maîtrises déjà.": "Atomboy amin'ireo mbola sarotra aminao, ary hamafiso izay efa hainao.",
    "Aucune notion prioritaire pour l'instant. Continue à pratiquer régulièrement.": "Tsy mbola misy lesona tokony hatao laharam-pahamehana. Tohizo tsy tapaka ny fanazaran-tena.",
    "Faire un quiz →": "Hanao quiz →",
    "Métacognition": "Fahafantarana ny fomba ianaranao",
    "réponse très sûre": "valiny tena natokisana",
    "observation au total": "fanamarihana amin'ny fitambarany",
    "maîtrise actuelle · %": "fahaizana ankehitriny · %",
    "Identifier la prochaine priorité": "Fantaro ny laharam-pahamehana manaraka",
    "Pratiquer": "Manao fanazaran-tena",
    "Tester une notion ciblée": "Hitsapa lesona iray manokana",
    "Comprendre": "Mahazo ny heviny",
    "Débloquer ton raisonnement": "Manampy amin'ny fisainanao",
    "Nouveau · Mode Mission": "Vaovao · Fomba Iraka",
    "Une notion à la fois, jusqu'à la prochaine preuve.": "Lesona iray isaky ny mandeha, mandra-pahazoana porofo manaraka.",
    "Le moteur choisit la priorité depuis ta carte de connaissances.": "Misafidy izay tokony hatao laharam-pahamehana araka ny sarintanin'ny fahalalanao ny rafitra.",
    "Voir ma mission →": "Hijery ny irakako →",
    "matières suivies": "taranja arahina",
    "Comprendre tes résultats": "Mahazo ny vokatrao",
    "Progression par matière": "Fandrosoana isaky ny taranja",
    "Repère en un coup d'œil ce qui est solide, en cours d'acquisition ou à renforcer.": "Jereo indray mipi-maso izay efa mafy orina, mbola ianarana na mila hamafisina.",
    "Solide": "Mafy orina",
    "En bonne voie": "Mandroso tsara",
    "À renforcer": "Mila hamafisina",
    "Pas encore assez de données": "Mbola tsy ampy ny angona",
    "Termine ton premier quiz pour voir apparaître ta progression par matière.": "Vitao ny quiz voalohany mba hahitanao ny fandrosoanao isaky ny taranja.",
    "Commencer un quiz": "Hanomboka quiz",
    "Comprendre l'ordre des notions": "Mahafantatra ny filaharan'ny lesona",
    "Le moteur de maîtrise sait déjà mesurer chaque notion. Cette carte ajoute maintenant les liens entre elles pour repérer les prérequis qui bloquent la suite.": "Efa mahay mandrefy ny lesona tsirairay ny rafitra. Asehony eto koa ny fifandraisan'izy ireo mba hahitana ny lesona fototra manakana ny fandrosoana.",
    "Ouvrir ma carte →": "Hanokatra ny sarintaniko →",
    "Prérequis fragile": "Lesona fototra mbola marefo",
    "Aucun blocage de prérequis détecté.": "Tsy nahitana sakana avy amin'ny lesona fototra.",
    "Continue à pratiquer pour que la carte affine progressivement ton parcours.": "Tohizo ny fanazaran-tena mba hanatsaran'ilay sarintany tsikelikely ny lalam-pianaranao.",
    "Nouveau moteur de décision": "Rafitra fanapahan-kevitra vaovao",
    "Passeport de maîtrise": "Pasipaoron'ny fahaizana",
    "Gasy Mahay ne considère plus qu'une notion est maîtrisée sur un simple score : il cherche une preuve répétée, sur plusieurs séances et niveaux de difficulté.": "Tsy mihevitra intsony i Gasy Mahay fa voafehy ny lesona noho ny isa fotsiny: mitady porofo miverimberina amin'ny fivoriana sy ambaratonga fahasarotana samihafa izy.",
    "Score ≠ preuve": "Ny isa ≠ porofo",
    "maîtrise estimée": "fahaizana tombanana",
    "confiance": "fahatokisana",
    "questions": "fanontaniana",
    "séances": "fivoriana",
    "réussites d'affilée": "valiny marina misesy",
    "Preuve obtenue.": "Voaray ny porofo.",
    "Les critères de preuve sont actuellement remplis.": "Feno amin'izao fotoana izao ny fepetra ilaina hahazoana porofo.",
    "Tu es proche.": "Efa akaiky ianao.",
    "preuve à sécuriser avant de déclarer la maîtrise.": "porofo mila hamafisina alohan'ny hanambarana fa voafehy ilay lesona.",
    "Prochaine meilleure action :": "Dingana tsara indrindra manaraka:",
    "Prouver ma maîtrise": "Hanaporofo ny fahaizako",
    "Entraîner cette notion": "Hanao fanazaran-tena amin'ity lesona ity",
    "Parcours personnalisé": "Lalam-pianarana manokana",
    "Notions à revoir": "Lesona tokony haverina",
    "Le système combine tes résultats et les dates de révision pour prioriser ce qui mérite ton attention aujourd'hui.": "Ampiarahin'ny rafitra ny vokatrao sy ny datin'ny famerenana lesona mba hamaritana izay tokony hifantohanao androany.",
    "Ouvrir le Tuteur IA": "Hanokatra ny Tuteur IA",
    "Niveau du prochain entraînement ·": "Ambaratongan'ny fanazaran-tena manaraka ·",
    "Prochaine révision ·": "Famerenana manaraka ·",
    "Avec le Tuteur": "Miaraka amin'ny Tuteur",
    "Quiz ciblé": "Quiz manokana",
    "Documents récents": "Tahirin-kevitra vao haingana",
    "Aucun document consulté.": "Tsy mbola nisy tahirin-kevitra nojerena.",
    "Explorer les documents →": "Hijery ny tahirin-kevitra →",
    "Résultats": "Vokatra",
    "Derniers quiz": "Quiz farany",
    "Aucun quiz terminé.": "Tsy mbola misy quiz vita.",
    "Ton moteur de progression": "Rafitra mampandroso anao",
    "Apprends, participe, gagne des points.": "Mianara, mandray anjara ary mahazo isa.",
    "Chaque action utile sur Gasy Mahay fait avancer ton parcours : Tuteur IA, quiz, cercles et partage de ressources.": "Mampandroso ny fianaranao ny hetsika mahasoa rehetra ao amin'ny Gasy Mahay: Tuteur IA, quiz, vondrona ary fifampizarana loharano.",
    "Objectif du jour": "Tanjona androany",
    "Mission du jour": "Iraka androany",
    "Quatre petites actions pour découvrir toute la plateforme.": "Hetsika kely efatra hahafantarana ny sehatra manontolo.",
    "Mission terminée · +25 XP": "Vita ny iraka · +25 XP",
    "Fait": "Vita",
    "Tes 7 premiers jours": "Ny 7 andro voalohany",
    "Jour /7 · chaque étape t'emmène vers une fonctionnalité différente.": "Andro /7 · mitondra anao hahafantatra fampiasa hafa ny dingana tsirairay.",
    "Tes badges": "Ireo mari-boninahitrao",
    "Les badges récompensent les habitudes que tu construis.": "Manome valisoa ireo fahazarana tsara amboarinao ny mari-boninahitra.",
    "Obtenu": "Efa azo",
    "À débloquer": "Mbola hosokafana",
    "Comment gagner des XP": "Ahoana no hahazoana XP",
    "par question": "isaky ny fanontaniana",
    "par quiz": "isaky ny quiz",
    "par participation": "isaky ny fandraisana anjara",
    "par dépôt": "isaky ny fametrahana",
    "Classement": "Filaharana",
    "Ta position": "Ny toerana misy anao",
    "Le classement commence avec toi. 🚀": "Manomboka aminao ny filaharana. 🚀",
    "Prochaine étape": "Dingana manaraka",
    "Complète ta mission du jour.": "Vitao ny iraka androany.",
    "En quelques minutes, tu découvriras les quatre fonctions qui rendent Gasy Mahay utile au quotidien.": "Ao anatin'ny minitra vitsy dia hahafantatra ireo fampiasa efatra mahasoa ao amin'ny Gasy Mahay ianao.",
    "Mission terminée 🎉": "Vita ny iraka 🎉",
    "Reviens demain pour construire ta série et continuer à faire progresser ton niveau.": "Miverena rahampitso mba hanohy ny andiany sy hampiakatra ny ambaratonganao.",
    "Retour au tableau de bord": "Hiverina any amin'ny tabilao ankapobeny",
    "Base de connaissances": "Tahirin'ny fahalalana",
    "Trouver une réponse sans parcourir tout le site.": "Mitadiava valiny nefa tsy mila mijery ny tranonkala manontolo.",
    "Recherche une question, filtre par sujet, consulte les réponses détaillées et découvre les retours de la communauté. Pour un problème personnel, le contact direct reste disponible.": "Mitadiava fanontaniana, sivano araka ny lohahevitra, vakio ny valiny feno ary jereo ny hevitry ny vondrom-piarahamonina. Raha olana manokana, mbola azo atao ny mifandray mivantana.",
    "Chercher une réponse": "Hitady valiny",
    "Voir le mode d'emploi": "Hijery ny torolalana",
    "Contacter l'équipe": "Hifandray amin'ny ekipa",
    "résultat dans la sélection actuelle.": "valiny amin'ny safidy ankehitriny.",
    "avis publics après modération.": "hevitra ampahibemaso rehefa avy nohamarinina.",
    "Inscription, connexion et récupération.": "Fisoratana anarana, fidirana ary fanarenana.",
    "Bibliothèque, dépôts et ressources.": "Tranomboky, fametrahana ary loharano.",
    "Création, examen et résultats.": "Famoronana, famaliana ary vokatra.",
    "Tuteur, réponses et bonnes pratiques.": "Tuteur, valiny ary fomba fampiasana tsara.",
    "Accès, messages et partage.": "Fidirana, hafatra ary fifampizarana.",
    "Sessions, 2FA et confidentialité.": "Fidirana, 2FA ary tsiambaratelo.",
    "Séances, vidéo, devoirs et tableau blanc.": "Fivoriana, horonan-tsary, enti-mody ary takelaka fotsy.",
    "Quand la FAQ ne suffit pas.": "Rehefa tsy ampy ny FAQ.",
    "Choisis ton chemin": "Safidio ny lalana",
    "Besoin d'aide maintenant ?": "Mila fanampiana izao?",
    "Commence par le parcours qui correspond à ton problème. Tu arriveras plus vite à la bonne page.": "Atombohy amin'ny dingana mifanaraka amin'ny olanao. Ho tonga haingana kokoa amin'ny pejy ilaina ianao.",
    "Je n'arrive plus à me connecter": "Tsy afaka miditra intsony aho",
    "Récupération du mot de passe et compte.": "Fanarenana ny tenimiafina sy kaonty.",
    "Je ne sais pas utiliser l'IA": "Tsy haiko ny mampiasa IA",
    "Différence entre Quiz IA et Tuteur IA.": "Ny maha-samy hafa ny Quiz IA sy Tuteur IA.",
    "Je cherche une ressource": "Mitady loharano aho",
    "Donne le contexte avant de contacter l'équipe.": "Hazavao ny toe-javatra alohan'ny hifandraisana amin'ny ekipa.",
    "Base de réponses": "Tahirin'ny valiny",
    "Recherche un mot-clé ou choisis une catégorie.": "Mitadiava teny fototra na mifidiana sokajy.",
    "Toutes les catégories": "Ny sokajy rehetra",
    "Filtre actuel :": "Sivana ankehitriny:",
    "Effacer les filtres": "Esory ny sivana",
    "Un problème avec ton compte ?": "Misy olana amin'ny kaontinao?",
    "Utilise directement la récupération du mot de passe ou ouvre la page Sécurité pour les réglages du compte.": "Ampiasao ny fanarenana tenimiafina na sokafy ny pejy Fiarovana hanovana ny kaontinao.",
    "Ouvrir Sécurité": "Hanokatra ny Fiarovana",
    "Tu veux apprendre à utiliser le site ?": "Te hianatra hampiasa ny tranonkala ve ianao?",
    "Le mode d'emploi détaille la navigation, les documents, les quiz, le Tuteur IA, les cercles et la classe virtuelle.": "Hazavain'ny torolalana ny fitetezana, tahirin-kevitra, quiz, Tuteur IA, vondrona ary kilasy virtoaly.",
    "Lire le guide": "Hamaky ny torolalana",
    "Besoin d'un humain ?": "Mila miresaka amin'olona?",
    "Pour un cas personnel ou un problème technique non couvert par la FAQ, passe directement par le contact.": "Raha olana manokana na teknika tsy voavaly ao amin'ny FAQ, ampiasao ny pejy fifandraisana.",
    "À propos de l'accès IA": "Momba ny fidirana amin'ny IA",
    "d'essai. Les autres fonctionnalités Premium restent accessibles pendant": "amin'ny andrana. Mbola azo ampiasaina mandritra ny",
    "Utilise le Quiz IA pour pratiquer et le Tuteur IA pour comprendre une difficulté. Vérifie toujours les notions importantes avec ton cours.": "Ampiasao ny Quiz IA hanaovana fanazaran-tena ary ny Tuteur IA hahatakarana olana. Hamarino amin'ny lesonao foana ireo hevitra lehibe.",
    "Avis des étudiants": "Hevitry ny mpianatra",
    "Les avis visibles publiquement passent par la modération.": "Hamarinina aloha ny hevitra aseho ampahibemaso.",
    "Pas encore de note publique": "Mbola tsy misy naoty ampahibemaso",
    "Ton retour peut aider à identifier ce qui doit être amélioré.": "Afaka manampy hamantatra izay tokony hatsaraina ny hevitrao.",
    "Merci pour ton feedback. Ton avis sera traité selon les règles de modération.": "Misaotra nizara hevitra. Hojerena araka ny fitsipika momba ny fanamarinana izany.",
    "La note doit être comprise entre 1 et 5.": "Tokony ho eo anelanelan'ny 1 sy 5 ny naoty.",
    "Merci de laisser un commentaire.": "Mba manorata hevitra.",
    "Trop d'avis envoyés récemment. Réessaie plus tard.": "Be loatra ny hevitra nalefa tato ho ato. Andramo indray afaka kelikely.",
    "Pour un retour utile": "Mba hahasoa ny hevitrao",
    "Décris ce que tu faisais, ce que tu attendais et ce qui s'est réellement passé. Pour un bug, indique la page concernée et, si possible, les étapes pour reproduire le problème.": "Lazao izay nataonao, izay nampoizinao ary izay tena nitranga. Raha misy olana amin'ny rafitra, lazao ny pejy voakasika sy ny dingana ahafahana mamerina ilay olana raha azo atao.",
    "Ta note": "Ny naoty omenao",
    "Visibilité": "Fahitana",
    "Ne pas afficher publiquement": "Aza aseho ampahibemaso",
    "Afficher mon avis": "Asehoy ampahibemaso ny hevitro",
    "Commentaire": "Hevitra",
    "Ton avis doit respecter les règles de respect et de confidentialité.": "Tsy maintsy manaja ny fitsipika momba ny fanajana sy ny tsiambaratelo ny hevitrao.",
    "Envoyer mon avis": "Handefa ny hevitro",
    "Ton dernier avis": "Ny hevitrao farany",
    "Voir la réponse de l'équipe →": "Hijery ny valin'ny ekipa →",
    "En attente de réponse de l'équipe.": "Miandry ny valin'ny ekipa.",
    "pour laisser un avis.": "mba hamela hevitra.",
    "Filtrer les avis": "Hanivana hevitra",
    "Réponse de l'équipe Mahay": "Valin'ny ekipa Mahay",
    "La réponse que tu cherches n'est pas encore dans la FAQ ?": "Tsy mbola ao amin'ny FAQ ve ny valiny tadiavinao?",
    "Le mode d'emploi couvre les parcours complets ; pour un cas personnel, contacte-nous directement.": "Manazava ny dingana rehetra ny torolalana; raha olana manokana, mifandraisa mivantana aminay.",
    "Conseil pour les outils IA": "Torohevitra momba ny fitaovana IA",
    "question à la fois": "fanontaniana isaky ny mandeha",
    "Transforme chaque session en progression": "Avadiho ho fandrosoana ny fianarana tsirairay",
    "Une note élevée ne suffit pas à prouver la maîtrise.": "Tsy ampy hanaporofoana fahaizana ny naoty ambony fotsiny.",
    "Aucune activité récente": "Tsy misy hetsika vao haingana",
    "Commence à explorer Gasy Mahay.": "Atombohy ny fikarohana ao amin'ny Gasy Mahay.",
    "Tu n'as encore rejoint aucun cercle d'étude": "Mbola tsy niditra vondrona fianarana ianao",
    "Révise à plusieurs, par filière ou en groupe libre.": "Miaraha mamerina lesona araka ny lalam-pianarana na vondrona malalaka.",
    "Compléter mon profil": "Hameno ny mombamomba ahy",
    "Aucune échéance à venir": "Tsy misy fe-potoana ho avy",
    "Les devoirs avec une date limite de tes cours apparaîtront ici.": "Hiseho eto ny enti-mody misy fe-potoana farany.",
    "Votre abonnement est actif pour encore": "Mbola mavitrika mandritra ny",
    "Votre demande est en cours de validation par un administrateur.": "Eo am-panamarinana ataon'ny mpitantana ny fangatahanao.",
    "Votre acces Premium n'est plus actif.": "Tsy mandeha intsony ny fidiranao Premium.",
    "Souscrivez ou renouvelez": "Misorata na havaozy ny famandrihana",
    "Aucune ressource pour le moment": "Mbola tsy misy loharano",
    "Les documents les plus téléchargés apparaîtront ici.": "Hiseho eto ireo tahirin-kevitra tena sintonina.",
    "Ton démarrage est à": "Efa vitanao ny dingana",
    "/3 aujourd'hui": "/3 androany",
    "Cette notion a encore": "Mbola misy",
    "erreurs à consolider.": "fahadisoana mila hamafisina.",
    "Maîtrise actuelle ·": "Fahaizana ankehitriny ·",
    "Prochaine mission": "Iraka manaraka"
  });

  var noeudsOriginaux = new WeakMap();
  var derniersRendus = new WeakMap();
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
    match = cle.match(/^Bonjour,\s+(.+?)\s*👋$/i);
    if (match) return "Manao ahoana, " + match[1] + " 👋";
    match = cle.match(/^Ton démarrage est à (\d+)\/3\.$/i);
    if (match) return "Efa vita ny dingana " + match[1] + " amin'ny 3.";
    match = cle.match(/^(\d+)\/3 aujourd'hui$/i);
    if (match) return match[1] + "/3 androany";
    match = cle.match(/^Cette notion a encore (\d+) erreurs? à consolider\.$/i);
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
    match = cle.match(/^maîtrise actuelle · (\d+)%$/i);
    if (match) return "Fahaizana ankehitriny · " + match[1] + "%";
    match = cle.match(/^(\d+)\s+documents consultés$/i);
    if (match) return match[1] + " tahirin-kevitra nojerena";
    match = cle.match(/^(\d+)\s+quiz récents$/i);
    if (match) return match[1] + " quiz vao haingana";
    match = cle.match(/^(\d+)\s+sessions? tuteur$/i);
    if (match) return match[1] + " fotoam-pianarana niaraka tamin'ny Mpampianatra IA";
    match = cle.match(/^(\d+) erreurs? avec une forte confiance sur (\d+) questions? très sûres?\.$/i);
    if (match) {
      return match[1] + " valiny diso nefa natokisana, tamin'ny fanontaniana " + match[2] + " tena natokisana.";
    }
    match = cle.match(/^(\d+) réponses? très sûres?$/i);
    if (match) return "Valiny " + match[1] + " tena natokisana";
    match = cle.match(/^(\d+) observations? au total$/i);
    if (match) return "Fanamarihana " + match[1] + " amin'ny fitambarany";
    return source;
  }

  function estProtege(element) {
    return Boolean(element && element.closest && element.closest(ELEMENTS_PROTEGES));
  }

  function traduireNoeudTexte(noeud, langue) {
    if (!noeud || noeud.nodeType !== 3 || estProtege(noeud.parentElement)) return;

    var contenuActuel = noeud.nodeValue || "";
    if (!noeudsOriginaux.has(noeud)) {
      noeudsOriginaux.set(noeud, contenuActuel);
    } else if (
      derniersRendus.has(noeud) &&
      contenuActuel !== derniersRendus.get(noeud)
    ) {
      // Un composant a modifié le texte d'origine depuis le dernier rendu.
      // Conserver cette nouvelle source, plutôt que de réappliquer l'ancienne
      // traduction à une valeur dynamique différente.
      noeudsOriginaux.set(noeud, contenuActuel);
    }

    var source = noeudsOriginaux.get(noeud);
    var traduction = traduireChaine(source, langue);

    if (langue === "mg" && traduction !== source) {
      // La clé est normalisée pour la recherche, mais les espaces aux bords
      // sont gardés pour les phrases coupées par des nombres ou des balises
      // (ex. « Il te reste <strong>5</strong> jours Premium »).
      var espacesInitiaux = (String(source).match(/^\\s*/) || [""])[0];
      var espacesFinaux = (String(source).match(/\\s*$/) || [""])[0];
      traduction = espacesInitiaux + traduction.replace(/^\\s+|\\s+$/g, "") + espacesFinaux;
    }

    if (noeud.nodeValue !== traduction) noeud.nodeValue = traduction;
    derniersRendus.set(noeud, traduction);
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
          if (mutation.type === "characterData") {
            traduireNoeudTexte(mutation.target, langueActuelle);
            return;
          }
          mutation.addedNodes.forEach(function (ajoute) {
            traduireSousArbre(ajoute, langueActuelle);
          });
        });
      });
      observateur.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser, { once: true });
  } else {
    initialiser();
  }
})(window, document);
