"""
Promeut un utilisateur existant au role 'admin' (necessaire pour acceder
a /moderation). Il n'y a pas de bouton pour ca dans l'interface : c'est
volontaire, pour qu'on ne puisse pas se donner ce role depuis le site.

Usage (depuis la racine du projet, apres inscription sur le site) :
    python -m app.creer_admin 0341234567
"""
import sys

from sqlmodel import Session, select

from .database import engine
from .models import Utilisateur, RoleUtilisateur


def promouvoir_admin(telephone: str) -> None:
    with Session(engine) as session:
        utilisateur = session.exec(
            select(Utilisateur).where(Utilisateur.telephone == telephone)
        ).first()
        if not utilisateur:
            print(f"Aucun utilisateur avec le numero {telephone}. Inscrivez-vous d'abord sur le site.")
            return
        utilisateur.role = RoleUtilisateur.ADMIN
        session.add(utilisateur)
        session.commit()
        print(f"{utilisateur.nom} est maintenant administrateur.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.creer_admin <telephone>")
    else:
        promouvoir_admin(sys.argv[1])
