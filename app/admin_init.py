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

logger = logging.getLogger("mahay.admin_init")


def assurer_compte_admin(session: Session) -> None:
    if not parametres.admin_phone:
        return

    utilisateur = session.exec(
        select(Utilisateur).where(Utilisateur.telephone == parametres.admin_phone)
    ).first()

    if utilisateur:
        if utilisateur.role != RoleUtilisateur.ADMIN:
            utilisateur.role = RoleUtilisateur.ADMIN
            session.add(utilisateur)
            session.commit()
            logger.info("Compte existant promu admin (telephone se terminant par ...%s).", parametres.admin_phone[-4:])
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
        telephone=parametres.admin_phone,
        mot_de_passe_hash=hacher_mot_de_passe(parametres.admin_mot_de_passe_initial),
        role=RoleUtilisateur.ADMIN,
    )
    session.add(nouveau)
    session.commit()
    # Le mot de passe lui-meme n'est jamais logue, seul le fait qu'un
    # compte ait ete cree.
    logger.info("Compte admin cree automatiquement (telephone se terminant par ...%s).", parametres.admin_phone[-4:])
