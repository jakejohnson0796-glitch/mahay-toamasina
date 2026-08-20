"""toamasina : ajoute l'ENS (mention SEAS) + scinde Histoire-Geographie

Revision ID: c9f1a6e3d8b2
Revises: b7e2d4a8c1f6
Create Date: 2026-08-20 16:00:00.000000

Deux ajouts distincts, chacun source verifiee independamment
(consultation du 20/08/2026) :

1) ENS (Ecole Normale Superieure) de Toamasina, absente jusqu'ici du
   referentiel. Une seule mention confirmee : "Sciences de l'Education
   et Administration Scolaire (SEAS)", avec 2 parcours de Master
   (Education et Formation d'Adultes / Administration et Services
   Scolaires). Sources concordantes : site officiel seas.mg (rattache
   pedagogiquement a l'ENS de l'Universite de Toamasina, y compris
   "Mot du Coordonnateur Principal") + flyer officiel PDF
   univ-toamasina.mg/static/pdfs/etablissements/ecoles/nouvelles/ens/ENS_Flyers.pdf
   + article de presse midi-madagasikara.mg (fevrier 2026).
   Niveau Licence egalement mentionne comme ouvert (L1, Licence
   Professionnelle) mais sans parcours nommes distincts trouves -> non
   ajoute, seul le Master (2 parcours nommes) est verse ici.

2) La Filiere "Histoire-Geographie" (seedee a l'origine comme une seule
   filiere) correspond en realite a une simplification : l'AUF
   confirme explicitement (https://www.auf.org/membre/universite-de-toamasina-2/)
   que cette filiere, creee en 1984, "fut scindee en deux l'annee
   suivante" (1985) -- confirme independamment par le listing Wikipedia
   qui mentionne des mentions "Histoire" et "Geographie" separees au
   sein de la FLSH. On AJOUTE donc les 2 mentions/filieres officielles
   "Histoire" et "Geographie", SANS toucher a la Filiere
   "Histoire-Geographie" existante (elle reste utilisable pour ne pas
   casser un Utilisateur.filiere_id existant -- a deprecier plus tard
   via l'admin une fois confirme qu'aucun compte actif n'en a besoin).

Non resolu, volontairement pas invente : la possible mention
"Mathematiques" distincte de "Mathematiques-Informatique et
Application" evoquee par un seul passage Wikipedia (incoherent avec
son propre intitule "trois mentions" pour 4 elements listes, aucune
2e source ne la confirme) -> rien ajoute.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9f1a6e3d8b2'
down_revision: Union[str, None] = 'b7e2d4a8c1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOM_FACULTE_ENS = "Ecole Normale Superieure (ENS)"
NOM_MENTION_SEAS = "Sciences de l'Education et Administration Scolaire (SEAS)"
PARCOURS_SEAS = ["Education et Formation d'Adultes (EFA)", "Administration et Services Scolaires (ASS)"]

NOM_FACULTE_LETTRES = "Lettres et Sciences Humaines"
NOUVELLES_MENTIONS_LETTRES = ["Histoire", "Geographie"]


def _obtenir_ou_creer_universite_toamasina(connexion) -> int:
    return connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()


def _lier_programme(connexion, universite_id: int, filiere_id: int) -> None:
    deja = connexion.execute(
        sa.text("SELECT id FROM programmeuniversitaire WHERE universite_id = :uid AND filiere_id = :fid")
        .bindparams(uid=universite_id, fid=filiere_id)
    ).scalar()
    if deja:
        return
    connexion.execute(
        sa.text(
            "INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) "
            "VALUES (:uid, :fid, TRUE)"
        ).bindparams(uid=universite_id, fid=filiere_id)
    )


def upgrade() -> None:
    connexion = op.get_bind()
    universite_id = _obtenir_ou_creer_universite_toamasina(connexion)
    if universite_id is None:
        return

    # --- 1) ENS + Mention SEAS + 2 parcours ---
    faculte_ens_id = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
        .bindparams(nom=NOM_FACULTE_ENS, uid=universite_id)
    ).scalar()
    if faculte_ens_id is None:
        connexion.execute(
            sa.text("INSERT INTO faculte (nom, universite_id) VALUES (:nom, :uid)")
            .bindparams(nom=NOM_FACULTE_ENS, uid=universite_id)
        )
        faculte_ens_id = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=NOM_FACULTE_ENS, uid=universite_id)
        ).scalar()

    mention_seas_id = connexion.execute(
        sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=NOM_MENTION_SEAS)
    ).scalar()
    if mention_seas_id is None:
        connexion.execute(
            sa.text("INSERT INTO mention (nom, est_active) VALUES (:nom, TRUE)")
            .bindparams(nom=NOM_MENTION_SEAS)
        )
        mention_seas_id = connexion.execute(
            sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=NOM_MENTION_SEAS)
        ).scalar()

    for nom_parcours in PARCOURS_SEAS:
        filiere_id = connexion.execute(
            sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
            .bindparams(nom=nom_parcours, fid=faculte_ens_id)
        ).scalar()
        if filiere_id is None:
            connexion.execute(
                sa.text("INSERT INTO filiere (nom, faculte_id, mention_id) VALUES (:nom, :fid, :mid)")
                .bindparams(nom=nom_parcours, fid=faculte_ens_id, mid=mention_seas_id)
            )
            filiere_id = connexion.execute(
                sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                .bindparams(nom=nom_parcours, fid=faculte_ens_id)
            ).scalar()
        _lier_programme(connexion, universite_id, filiere_id)

    # --- 2) Histoire / Geographie separees (en plus de Histoire-Geographie existante) ---
    faculte_lettres_id = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
        .bindparams(nom=NOM_FACULTE_LETTRES, uid=universite_id)
    ).scalar()
    if faculte_lettres_id is not None:
        for nom_mention in NOUVELLES_MENTIONS_LETTRES:
            mention_id = connexion.execute(
                sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=nom_mention)
            ).scalar()
            if mention_id is None:
                connexion.execute(
                    sa.text("INSERT INTO mention (nom, est_active) VALUES (:nom, TRUE)")
                    .bindparams(nom=nom_mention)
                )
                mention_id = connexion.execute(
                    sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=nom_mention)
                ).scalar()

            filiere_id = connexion.execute(
                sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                .bindparams(nom=nom_mention, fid=faculte_lettres_id)
            ).scalar()
            if filiere_id is None:
                connexion.execute(
                    sa.text("INSERT INTO filiere (nom, faculte_id, mention_id) VALUES (:nom, :fid, :mid)")
                    .bindparams(nom=nom_mention, fid=faculte_lettres_id, mid=mention_id)
                )
                filiere_id = connexion.execute(
                    sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                    .bindparams(nom=nom_mention, fid=faculte_lettres_id)
                ).scalar()
            _lier_programme(connexion, universite_id, filiere_id)


def downgrade() -> None:
    connexion = op.get_bind()

    for nom_mention in NOUVELLES_MENTIONS_LETTRES:
        connexion.execute(
            sa.text("DELETE FROM programmeuniversitaire WHERE filiere_id IN (SELECT id FROM filiere WHERE nom = :nom)")
            .bindparams(nom=nom_mention)
        )
        connexion.execute(sa.text("DELETE FROM filiere WHERE nom = :nom").bindparams(nom=nom_mention))
        connexion.execute(sa.text("DELETE FROM mention WHERE nom = :nom").bindparams(nom=nom_mention))

    for nom_parcours in PARCOURS_SEAS:
        connexion.execute(
            sa.text("DELETE FROM programmeuniversitaire WHERE filiere_id IN (SELECT id FROM filiere WHERE nom = :nom)")
            .bindparams(nom=nom_parcours)
        )
        connexion.execute(sa.text("DELETE FROM filiere WHERE nom = :nom").bindparams(nom=nom_parcours))

    connexion.execute(sa.text("DELETE FROM mention WHERE nom = :nom").bindparams(nom=NOM_MENTION_SEAS))
    connexion.execute(sa.text("DELETE FROM faculte WHERE nom = :nom").bindparams(nom=NOM_FACULTE_ENS))
