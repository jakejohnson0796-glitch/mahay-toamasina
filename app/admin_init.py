"""
Initialisation automatique du compte administrateur au demarrage, pour ne
plus jamais avoir a executer app/creer_admin.py a la main apres un
deploiement ou sur un nouvel environnement (voir main.py, appelee juste
apres peupler_donnees_initiales()).

Pilotee par deux variables d'environnement (jamais commitees, jamais
codees en dur — voir .env.example) :
- ADMIN_PHONE : le numero du compte a garantir admin. Absente => cette
  fonction ne fait rien du tout, comportement identique a avant.
- ADMIN_INITIAL_PASSWORD : utilisee UNIQUEMENT si aucun compte n'existe
  encore avec ce numero (creation initiale). Jamais lue ni utilisee pour
  modifier le mot de passe d'un compte deja existant.

Idempotent et sans effet de bord dangereux : peut tourner a chaque
demarrage, sur SQLite comme sur Postgres, sans jamais dupliquer le
compte ni ecraser un mot de passe existant.
"""
import logging

from sqlmodel import Session, select

from .config import parametres
from .models import Utilisateur, RoleUtilisateur
from .auth import hacher_mot_de_passe
from .telephone import normaliser_telephone, TelephoneInvalide

logger = logging.getLogger("mahay.admin_init")


def assurer_compte_admin(session: Session) -> None:
    if not parametres.admin_phone:
        return

    # ADMIN_PHONE doit etre compare a la MEME forme canonique que celle
    # utilisee par l'inscription/connexion (app/telephone.py), sinon un
    # ADMIN_PHONE ecrit "+261..." ne correspond jamais au "034..." stocke
    # en base : on cree/cherche un compte fantome a chaque demarrage, et
    # l'acces admin reel (via /connexion, qui normalise toujours) ne
    # fonctionne jamais. On normalise donc ici AVANT toute comparaison.
    try:
        telephone_normalise = normaliser_telephone(parametres.admin_phone)
    except TelephoneInvalide as erreur:
        logger.error(
            "ADMIN_PHONE (%s) n'est pas un numero malgache valide : %s. "
            "Aucune initialisation admin effectuee.",
            parametres.admin_phone, erreur,
        )
        return

    utilisateur = session.exec(
        select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)
    ).first()

    if utilisateur:
        if utilisateur.role != RoleUtilisateur.ADMIN:
            utilisateur.role = RoleUtilisateur.ADMIN
            session.add(utilisateur)
            session.commit()
            logger.info("Compte existant promu admin (telephone se terminant par ...%s).", telephone_normalise[-4:])
        # Mot de passe jamais touche pour un compte deja existant : on ne
        # fait que garantir le role, rien d'autre.
        return

    if not parametres.admin_mot_de_passe_initial:
        logger.warning(
            "ADMIN_PHONE est definie mais aucun compte n'existe avec ce numero, et "
            "ADMIN_INITIAL_PASSWORD est absente : impossible de creer le compte "
            "automatiquement. Definissez ADMIN_INITIAL_PASSWORD (une seule fois, "
            "pour cette creation initiale) ou creez le compte via /inscription puis "
            "relancez, ou via python -m app.creer_admin."
        )
        return

    nouveau = Utilisateur(
        nom="Administrateur",
        telephone=telephone_normalise,
        mot_de_passe_hash=hacher_mot_de_passe(parametres.admin_mot_de_passe_initial),
        role=RoleUtilisateur.ADMIN,
    )
    session.add(nouveau)
    session.commit()
    # Le mot de passe lui-meme n'est jamais logue, seul le fait qu'un
    # compte ait ete cree.
    logger.info("Compte admin cree automatiquement (telephone se terminant par ...%s).", telephone_normalise[-4:])
