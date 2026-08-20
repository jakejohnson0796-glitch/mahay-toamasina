"""toamasina : correction rattachement Mathematiques-Info + noms mentions Medecine

Revision ID: b7e2d4a8c1f6
Revises: a3c7f1e9b2d4
Create Date: 2026-08-20 14:00:00.000000

CORRECTIF suite a une erreur dans a3c7f1e9b2d4. Nouvelle source trouvee
apres coup, plus fiable que le sous-domaine degmia.univ-toamasina.mg
utilise precedemment : la page officielle archivee de l'universite
elle-meme, http://www.univ-toamasina.mg/facultes.html (consultee via
web.archive.org, citee en reference par
https://fr.wikipedia.org/wiki/Universite_de_Toamasina, verifiee le
20/08/2026).

Cette source liste explicitement la Faculte des Sciences et Technologie
avec QUATRE mentions : Physique, Mathematiques, Mathematiques-
Informatique et Application, Chimie. La mention "Mathematiques,
Informatique et Applications" doit donc etre rattachee a la faculte
"Sciences et Technologies", pas a DEGMIA comme fait par erreur dans
a3c7f1e9b2d4.

Meme source : la Faculte de Medecine a pour mentions officielles
"Medecine humaine", "Maieutique" et "Infirmerie" -- pas "Sage-Femme" ni
"Soins Infirmiers" (noms de metier corrects mais pas les intitules
officiels de mention).

Ce que fait cette migration :
1) Deplace la Filiere "Mathematiques et Informatique" (faculte_id) de
   DEGMIA vers "Sciences et Technologies". Le filiere_id ne change pas
   -- aucun impact sur un Utilisateur.filiere_id existant.
2) Renomme les Mention "Sage-Femme" -> "Maieutique" et
   "Soins Infirmiers" -> "Infirmerie" (idem : mention_id inchange).
3) Renomme les Filiere correspondantes pour rester coherentes.

Non concerne : la separation possible "Histoire" / "Geographie" en 2
mentions distinctes (releve dans la meme source Wikipedia, mais en
contradiction avec le total annonce "cinq mentions" pour cinq elements
lorsqu'on compte Etudes francaises + Philosophie + Anthropologie +
HDD + Histoire-Geographie -- ambigu, donc PAS applique ici tant que ce
n'est pas confirme par une 2e source. La Filiere "Histoire-Geographie"
existante n'est pas touchee.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2d4a8c1f6'
down_revision: Union[str, None] = 'a3c7f1e9b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connexion = op.get_bind()

    # --- 1) Deplacer la Filiere Mathematiques-Info vers la bonne faculte ---
    faculte_sciences_id = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = 'Sciences et Technologies'")
    ).scalar()
    if faculte_sciences_id is not None:
        connexion.execute(
            sa.text("UPDATE filiere SET faculte_id = :fid WHERE nom = 'Mathematiques et Informatique'")
            .bindparams(fid=faculte_sciences_id)
        )

    # --- 2) Renommer les mentions Medecine vers leur intitule officiel ---
    for ancien_nom, nouveau_nom in [
        ("Sage-Femme", "Maieutique"),
        ("Soins Infirmiers", "Infirmerie"),
    ]:
        connexion.execute(
            sa.text("UPDATE mention SET nom = :nouveau WHERE nom = :ancien")
            .bindparams(nouveau=nouveau_nom, ancien=ancien_nom)
        )

    # --- 3) Renommer les Filiere correspondantes pour rester coherentes ---
    for ancien_nom, nouveau_nom in [
        ("Sage-Femme", "Maieutique"),
        ("Infirmiere", "Infirmerie"),
    ]:
        connexion.execute(
            sa.text("UPDATE filiere SET nom = :nouveau WHERE nom = :ancien")
            .bindparams(nouveau=nouveau_nom, ancien=ancien_nom)
        )


def downgrade() -> None:
    connexion = op.get_bind()

    for ancien_nom, nouveau_nom in [
        ("Sage-Femme", "Maieutique"),
        ("Infirmiere", "Infirmerie"),
    ]:
        connexion.execute(
            sa.text("UPDATE filiere SET nom = :ancien WHERE nom = :nouveau")
            .bindparams(ancien=ancien_nom, nouveau=nouveau_nom)
        )

    for ancien_nom, nouveau_nom in [
        ("Sage-Femme", "Maieutique"),
        ("Soins Infirmiers", "Infirmerie"),
    ]:
        connexion.execute(
            sa.text("UPDATE mention SET nom = :ancien WHERE nom = :nouveau")
            .bindparams(ancien=ancien_nom, nouveau=nouveau_nom)
        )

    faculte_degmia_id = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = 'Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)'")
    ).scalar()
    if faculte_degmia_id is not None:
        connexion.execute(
            sa.text("UPDATE filiere SET faculte_id = :fid WHERE nom = 'Mathematiques et Informatique'")
            .bindparams(fid=faculte_degmia_id)
        )
