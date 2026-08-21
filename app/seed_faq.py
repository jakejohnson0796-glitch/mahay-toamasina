"""
Peuple la FAQ avec un premier jeu de questions/reponses au demarrage, pour
ne pas livrer une page /faq vide. Toutes les reponses decrivent des
fonctionnalites reellement presentes dans le projet au moment ou ce fichier
a ete ecrit — aucune fonctionnalite inventee (ex: pas de "mot de passe
oublie" automatique, car cette fonctionnalite n'existe pas encore cote
auth_router.py).

Meme pattern que seed_data.py : idempotent, appelable a chaque demarrage.
"""
from sqlmodel import Session, select

from .models import FAQ, CategorieFAQ

FAQ_INITIALE: list[dict] = [
    # --- General ---
    {
        "question": "Qu'est-ce que Mahay ?",
        "reponse": (
            "Mahay est une plateforme educative pensee pour les etudiants "
            "des universites publiques malagasy. Elle regroupe des documents "
            "de revision (annales, corriges, fiches), un generateur de quiz "
            "par IA, des cercles d'etude, une classe virtuelle et un tuteur IA."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    {
        "question": "A qui s'adresse Mahay ?",
        "reponse": (
            "Mahay s'adresse aux etudiants inscrits dans une universite "
            "publique malagasy couverte par la plateforme, ainsi qu'aux "
            "professeurs qui animent des sessions dans le module Classe "
            "virtuelle."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    {
        "question": "Pourquoi utiliser Mahay ?",
        "reponse": (
            "Pour retrouver au meme endroit les annales et corriges de votre "
            "filiere, vous entrainer avec des quiz generes automatiquement, "
            "reviser en groupe dans un cercle d'etude, et poser vos questions "
            "a un tuteur IA disponible a tout moment."
        ),
        "categorie": CategorieFAQ.GENERAL,
    },
    # --- Compte et inscription ---
    {
        "question": "Comment creer un compte sur Mahay ?",
        "reponse": (
            "Rendez-vous sur la page d'inscription et renseignez votre nom, "
            "votre numero de telephone (utilise comme identifiant de "
            "connexion) et un mot de passe. Vous choisissez ensuite votre "
            "filiere pour acceder aux documents et quiz qui la concernent."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Comment modifier mon profil ?",
        "reponse": (
            "Depuis la page Securite (accessible une fois connecte), vous "
            "pouvez notamment changer d'universite/filiere et activer la "
            "double authentification. Un delai minimum de 14 jours s'applique "
            "entre deux changements de niveau d'etudes."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    {
        "question": "Que faire si j'oublie mon mot de passe ?",
        "reponse": (
            "La reinitialisation automatique du mot de passe n'est pas "
            "encore disponible sur Mahay. En attendant, contactez-nous via "
            "la page Contact ou le numero WhatsApp indique en bas de page "
            "pour obtenir de l'aide."
        ),
        "categorie": CategorieFAQ.COMPTE,
    },
    # --- Cours et documents ---
    {
        "question": "Comment trouver un cours ou une annale ?",
        "reponse": (
            "La page Documents liste les annales, corriges et fiches de "
            "revision approuves, filtrables par filiere et par matiere."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    {
        "question": "Comment deposer un document ?",
        "reponse": (
            "Depuis la page de depot de document, envoyez votre fichier avec "
            "son titre, sa matiere et son type (annale, corrige, fiche ou "
            "cours). Il devient visible publiquement une fois valide par un "
            "moderateur."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    {
        "question": "Comment retrouver mes documents deposes ?",
        "reponse": (
            "Vos depots restent lies a votre compte ; leur statut (en "
            "attente, approuve ou rejete) est visible depuis votre tableau "
            "de bord."
        ),
        "categorie": CategorieFAQ.COURS,
    },
    # --- Quiz ---
    {
        "question": "Comment fonctionne un quiz sur Mahay ?",
        "reponse": (
            "Le Quiz IA genere un quiz sur mesure a partir d'une matiere que "
            "vous choisissez. Un mode examen chronometre est egalement "
            "disponible pour vous entrainer dans des conditions proches d'un "
            "vrai partiel."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },
    {
        "question": "Comment suivre mes resultats de quiz ?",
        "reponse": (
            "L'historique des quiz conserve vos tentatives precedentes et "
            "vos scores, accessible depuis le menu IA."
        ),
        "categorie": CategorieFAQ.QUIZ,
    },
    # --- Cercles d'etude ---
    {
        "question": "Qu'est-ce qu'un cercle d'etude ?",
        "reponse": (
            "Un cercle d'etude est un espace de discussion en groupe pour "
            "reviser a plusieurs, par filiere ou en groupe libre. C'est une "
            "fonctionnalite Premium."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },
    {
        "question": "Comment rejoindre un cercle d'etude ?",
        "reponse": (
            "Depuis la page Cercles d'etude, recherchez un cercle existant et "
            "envoyez une demande d'adhesion, ou consultez les cercles publics "
            "ouverts a tous."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },
    {
        "question": "Comment creer un cercle d'etude ?",
        "reponse": (
            "Vous pouvez soumettre une demande de creation de cercle depuis "
            "la page Cercles d'etude ; elle est ensuite examinee par "
            "l'administration."
        ),
        "categorie": CategorieFAQ.CERCLES,
    },
    # --- IA ---
    {
        "question": "A quoi sert l'assistant IA de Mahay ?",
        "reponse": (
            "Le Tuteur IA repond a une question de cours en fournissant une "
            "explication, un exemple et un exercice avec sa correction, pour "
            "vous aider a approfondir un point precis."
        ),
        "categorie": CategorieFAQ.IA,
    },
    {
        "question": "Comment utiliser l'IA efficacement pour apprendre ?",
        "reponse": (
            "Posez une question precise et ciblee sur un point de cours "
            "plutot qu'un sujet tres large, puis faites l'exercice propose "
            "avant de consulter sa correction."
        ),
        "categorie": CategorieFAQ.IA,
    },
    # --- Securite et confidentialite ---
    {
        "question": "Comment Mahay protege-t-il mes donnees ?",
        "reponse": (
            "Votre mot de passe n'est jamais stocke en clair, les "
            "formulaires sont proteges contre les attaques CSRF, et vous "
            "pouvez activer la double authentification (2FA) depuis la page "
            "Securite pour renforcer la protection de votre compte."
        ),
        "categorie": CategorieFAQ.SECURITE,
    },
    {
        "question": "Qui peut voir mes informations personnelles ?",
        "reponse": (
            "Vos coordonnees (telephone) restent privees. Si vous publiez un "
            "avis avec l'option d'affichage public activee, seul votre "
            "prenom accompagne votre commentaire — jamais votre telephone."
        ),
        "categorie": CategorieFAQ.SECURITE,
    },
    # --- Feedback et assistance ---
    {
        "question": "Comment donner mon avis sur Mahay ?",
        "reponse": (
            "Rendez-vous sur la page Feedback, attribuez une note de 1 a 5 "
            "etoiles et laissez un commentaire. Vous pouvez choisir de le "
            "rendre visible publiquement ou de le garder prive."
        ),
        "categorie": CategorieFAQ.FEEDBACK,
    },
    {
        "question": "L'equipe Mahay repond-elle aux avis laisses ?",
        "reponse": (
            "Oui, l'administration peut repondre directement a votre avis "
            "depuis son tableau de bord. Sa reponse apparait ensuite sous "
            "votre commentaire, dans la page Feedback."
        ),
        "categorie": CategorieFAQ.FEEDBACK,
    },
]


def peupler_faq_initiale(session: Session) -> None:
    """Insere le jeu de FAQ initial si la table est vide. Idempotent :
    n'ecrase jamais une FAQ deja modifiee/creee par un admin — se contente
    de ne rien faire si au moins une ligne existe deja."""
    deja_seede = session.exec(select(FAQ)).first()
    if deja_seede:
        return

    for ordre, item in enumerate(FAQ_INITIALE):
        session.add(
            FAQ(
                question=item["question"],
                reponse=item["reponse"],
                categorie=item["categorie"],
                ordre_affichage=ordre,
            )
        )
    session.commit()
