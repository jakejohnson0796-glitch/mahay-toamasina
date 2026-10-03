"""
Jeu initial et maintenance légère de la FAQ publique.

La FAQ est volontairement alimentée par le code afin qu'une nouvelle
installation ne démarre pas avec une page vide. Le synchroniseur reste
prudent : il ajoute les nouvelles questions et corrige uniquement quelques
réponses historiques connues comme obsolètes. Il ne remplace jamais une
réponse modifiée par un administrateur.
"""
from __future__ import annotations

from sqlmodel import Session, select

from .models import FAQ, CategorieFAQ


FAQ_INITIALE: list[dict] = [
    # --- Général ---
    {
        "question": "Qu'est-ce que Gasy Mahay ?",
        "reponse": (
            "Gasy Mahay est une plateforme d'apprentissage et d'entraide "
            "pensée pour les étudiants de Madagascar. Elle réunit des "
            "ressources académiques, des quiz, un Tuteur IA, des cercles "
            "d'étude, une classe virtuelle et des outils de suivi."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    {
        "question": "À qui s'adresse Gasy Mahay ?",
        "reponse": (
            "La plateforme est principalement pensée pour les étudiants et "
            "communautés académiques couvertes par son référentiel. Le module "
            "Classe virtuelle permet également à des professeurs d'animer "
            "des séances selon les droits prévus par la plateforme."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    {
        "question": "Que puis-je faire sur Gasy Mahay ?",
        "reponse": (
            "Vous pouvez rechercher des ressources, déposer des documents, "
            "vous entraîner avec des quiz, utiliser le Tuteur IA, rejoindre "
            "des cercles d'étude, suivre vos activités et participer à une "
            "classe virtuelle lorsque vous y avez accès."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    {
        "question": "Gasy Mahay remplace-t-il mon enseignant ou mon cours ?",
        "reponse": (
            "Non. Gasy Mahay est un outil d'appui à l'apprentissage. Les "
            "supports officiels, les enseignants et les règles de votre "
            "établissement restent les références à privilégier."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },

    # --- Compte et inscription ---
    {
        "question": "Comment créer un compte ?",
        "reponse": (
            "Ouvrez la page Inscription, renseignez votre nom, votre numéro "
            "de téléphone et votre mot de passe, puis complétez les "
            "informations académiques demandées pour votre profil."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Comment me connecter ?",
        "reponse": (
            "Utilisez le même numéro de téléphone et le mot de passe associés "
            "à votre compte. Certains comptes peuvent demander une étape "
            "supplémentaire avec la double authentification (2FA)."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Que faire si j'oublie mon mot de passe ?",
        "reponse": (
            "Utilisez la page « Mot de passe oublié ». Si votre compte dispose "
            "d'une adresse email et que l'envoi SMTP est configuré, un code "
            "temporaire vous est envoyé. Vous pouvez ensuite choisir un "
            "nouveau mot de passe."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Pourquoi la récupération du mot de passe peut-elle ne pas fonctionner ?",
        "reponse": (
            "Le parcours automatique dépend d'une adresse email enregistrée "
            "sur le compte et d'un service SMTP correctement configuré. Sans "
            "ces éléments, l'administration peut encore aider à réinitialiser "
            "le compte."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Combien de temps dure l'essai gratuit étudiant ?",
        "reponse": (
            "Un nouvel étudiant reçoit un essai gratuit de 60 jours pour les "
            "fonctionnalités Premium prévues par le projet. Le Quiz IA et le "
            "Tuteur IA sont inclus gratuitement pendant les 14 premiers jours "
            "de cet essai ; le reste des fonctionnalités Premium reste "
            "accessible pendant les 60 jours."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },

    # --- Profil ---
    {
        "question": "Comment modifier mon profil académique ?",
        "reponse": (
            "La page Sécurité / profil académique permet d'actualiser les "
            "informations autorisées. Certaines modifications de mention ou "
            "de filière passent par une demande qui doit être validée par "
            "l'administration."
        ),
        "categorie": CategorieFAQ.PROFIL,
    },
    {
        "question": "Pourquoi vois-je un rappel d'inactivité ?",
        "reponse": (
            "Si votre dernière utilisation remonte à au moins trois jours, "
            "Gasy Mahay peut afficher une notification lors de votre retour "
            "pour vous signaler la période d'inactivité."
        ),
        "categorie": CategorieFAQ.PROFIL,
    },

    # --- Cours et documents ---
    {
        "question": "Comment trouver un cours ou une annale ?",
        "reponse": (
            "La page Documents permet de parcourir les ressources publiées et "
            "de les filtrer selon le contexte académique et les informations "
            "disponibles dans le référentiel."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    {
        "question": "Comment déposer un document ?",
        "reponse": (
            "Depuis le parcours de dépôt, envoyez votre fichier, renseignez "
            "les informations demandées et laissez le système analyser le "
            "document lorsque la détection automatique est disponible. Le "
            "document reste soumis à la modération avant publication."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    {
        "question": "Le système peut-il détecter automatiquement le type d'un document ?",
        "reponse": (
            "Oui. La plateforme dispose d'un endpoint de détection qui peut "
            "examiner le nom et le contenu temporaire du fichier afin de "
            "proposer un type et une matière. Cette détection ne publie pas "
            "le document à elle seule."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    {
        "question": "Que se passe-t-il après le dépôt d'un document ?",
        "reponse": (
            "Le document entre dans le flux de modération. Un administrateur "
            "peut le consulter, l'approuver, le rejeter ou le désactiver. "
            "Les événements importants peuvent générer des notifications."
        ),
        "categorie": CategorieFAQ.COURS,
    },

    # --- Quiz ---
    {
        "question": "Combien de temps puis-je utiliser le Quiz IA et le Tuteur IA gratuitement ?",
        "reponse": (
            "Le Quiz IA et le Tuteur IA sont accessibles pendant les 14 "
            "premiers jours de l'essai gratuit. Les autres fonctionnalités "
            "Premium prévues par le projet restent accessibles pendant 60 "
            "jours. Un abonnement payant actif redonne l'accès aux "
            "fonctionnalités IA pendant sa période de validité."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },
    {
        "question": "Comment fonctionne un quiz IA ?",
        "reponse": (
            "Le Quiz IA génère des questions à partir d'un contexte "
            "d'apprentissage ou d'une ressource selon le parcours choisi. "
            "Une tentative est conservée pour permettre la correction, le "
            "score et l'historique."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },
    {
        "question": "Puis-je voir la correction après avoir répondu ?",
        "reponse": (
            "Oui. Après la soumission, la page du quiz peut afficher le "
            "résultat, la réponse sélectionnée, la bonne réponse et "
            "l'explication prévue pour la question."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },
    {
        "question": "Comment retrouver mes anciens quiz ?",
        "reponse": (
            "L'historique des quiz conserve les tentatives précédentes et "
            "leurs résultats depuis l'espace prévu dans le menu IA."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },

    # --- Cercles ---
    {
        "question": "Qu'est-ce qu'un cercle d'étude ?",
        "reponse": (
            "Un cercle est un espace de collaboration entre membres pour "
            "réviser, discuter, partager des ressources et travailler autour "
            "d'un contexte académique ou d'un groupe libre."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },
    {
        "question": "Comment rechercher un cercle ?",
        "reponse": (
            "La recherche des cercles permet de retrouver des espaces à "
            "partir de mots-clés et du niveau lorsqu'ils sont renseignés."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },
    {
        "question": "Comment rejoindre un cercle ?",
        "reponse": (
            "Depuis la liste des cercles, ouvrez le cercle correspondant puis "
            "utilisez le parcours d'adhésion prévu. Selon le cercle, une "
            "demande peut devoir être validée par son créateur ou un "
            "administrateur."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },

    # --- IA ---
    {
        "question": "Que fait le Tuteur IA ?",
        "reponse": (
            "Le Tuteur IA peut expliquer une notion, donner un exemple, "
            "proposer un exercice puis fournir une correction structurée."
        ),
        "categorie": CategorieFAQ.IA,
    },
    {
        "question": "Les réponses de l'IA sont-elles vérifiées ?",
        "reponse": (
            "Selon la fonctionnalité, les réponses passent par des "
            "normalisations locales et des contrôles supplémentaires, y "
            "compris des vérifications multi-modèles pour certains scénarios. "
            "Cela réduit les erreurs mais ne garantit pas une exactitude "
            "absolue."
        ),
        "categorie": CategorieFAQ.IA,
    },
    {
        "question": "Comment utiliser l'IA efficacement pour apprendre ?",
        "reponse": (
            "Posez une question précise, essayez l'exercice proposé avant de "
            "consulter sa correction et comparez les points importants avec "
            "votre cours ou une source officielle."
        ),
        "categorie": CategorieFAQ.IA,
    },

    # --- Sécurité ---
    {
        "question": "Comment mon compte est-il protégé ?",
        "reponse": (
            "Les mots de passe sont hachés, les sessions sont signées et "
            "protégées en production, les formulaires d'état utilisent une "
            "protection CSRF et plusieurs limites anti-abus réduisent les "
            "tentatives automatisées."
        ),
        "categorie": CategorieFAQ.SECURITE,
    },
    {
        "question": "Comment activer la double authentification ?",
        "reponse": (
            "Ouvrez la page Sécurité lorsque vous êtes connecté, puis suivez "
            "le parcours de configuration 2FA/TOTP. Des codes de secours "
            "peuvent également être générés."
        ),
        "categorie": CategorieFAQ.SECURITE,
    },
    {
        "question": "Qui peut voir mon numéro de téléphone ?",
        "reponse": (
            "Le numéro utilisé pour la connexion reste une donnée de compte "
            "privée. Les avis rendus publics n'affichent pas ce numéro."
        ),
        "categorie": CategorieFAQ.SECURITE,
    },

    # --- Feedback ---
    {
        "question": "Comment donner mon avis ?",
        "reponse": (
            "Dans la partie Aide et Avis, connectez-vous, choisissez une note "
            "et écrivez votre commentaire. Vous pouvez choisir de rendre "
            "l'avis public ou de le garder privé."
        ),
        "categorie": CategorieFAQ.FEEDBACK,
    },
    {
        "question": "Les avis publics sont-ils modérés ?",
        "reponse": (
            "Oui. Les avis visibles publiquement sont soumis aux règles de "
            "modération et les informations privées ne sont pas exposées."
        ),
        "categorie": CategorieFAQ.FEEDBACK,
    },
]


# Cette ancienne réponse était livrée dans une version où le parcours de
# récupération n'était pas encore disponible. Elle est remplacée uniquement
# si la FAQ n'a pas été personnalisée depuis.
ANCIEN_MESSAGE_MOT_DE_PASSE_OUBLIE = (
    "La reinitialisation automatique du mot de passe n'est pas "
    "encore disponible sur Mahay. En attendant, contactez-nous via "
    "la page Contact ou le numero WhatsApp indique en bas de page "
    "pour obtenir de l'aide."
)


def _normaliser_question(texte: str) -> str:
    return " ".join((texte or "").casefold().split())


def peupler_faq_initiale(session: Session) -> None:
    """Ajoute les nouvelles entrées et corrige seulement les seedings
    historiques explicitement connus comme obsolètes.

    Une FAQ existante créée/modifiée par un administrateur n'est jamais
    écrasée automatiquement.
    """
    existantes = {
        _normaliser_question(item.question): item
        for item in session.exec(select(FAQ)).all()
    }

    modifications = False

    for ordre, item in enumerate(FAQ_INITIALE):
        cle = _normaliser_question(item["question"])
        faq = existantes.get(cle)

        if faq is None:
            session.add(
                FAQ(
                    question=item["question"],
                    reponse=item["reponse"],
                    categorie=item["categorie"],
                    ordre_affichage=ordre,
                )
            )
            modifications = True
            continue

        # Correction ciblée d'un texte de seed historique.
        if faq.reponse == ANCIEN_MESSAGE_MOT_DE_PASSE_OUBLIE and "mot de passe" in cle:
            faq.reponse = item["reponse"]
            faq.categorie = item["categorie"]
            session.add(faq)
            modifications = True

    if modifications:
        session.commit()
