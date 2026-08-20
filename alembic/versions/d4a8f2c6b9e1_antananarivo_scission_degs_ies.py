"""antananarivo : scinde DEGS en 2 facultes + ajoute les 2 IES regionaux

Revision ID: d4a8f2c6b9e1
Revises: c9f1a6e3d8b2
Create Date: 2026-08-20 18:00:00.000000

L'Universite d'Antananarivo n'a que 7 etablissements en base
(f2b8e6a1c9d3), mais compte en realite 10 etablissements de formation.
Confirme par plusieurs sources concordantes le 20/08/2026 :
- article de presse (journees portes ouvertes, liste nominative des
  10 etablissements : Lettres, Droit et Sciences Politiques, Economie-
  Gestion-Sociologie, Medecine, Sciences, ENS, ESPA, ESSA, IES
  Soavinandriana, IES Antsirabe) -
  antananarivo78.rssing.com/chan-65781957/all_p30.html
- la page anglaise Wikipedia "University of Antananarivo" confirme
  les 2 IES regionaux comme "regional branches" de l'universite
- le site FOAD Gestion (foadgestion-degs.org, officiel, gere par la
  faculte elle-meme) confirme que la "Faculte d'Economie, de Gestion
  et de Sociologie (Fac.EGS)" est une entite a part, distincte du Droit

Donc "Faculte de Droit, d'Economie, de Gestion et de Sociologie (DEGS)"
seedee par erreur comme une faculte unique doit etre scindee en :
  - Faculte de Droit et des Sciences Politiques
  - Faculte d'Economie, de Gestion et de Sociologie (EGS)

SANS RISQUE de casser un compte existant : l'Universite d'Antananarivo
n'a a ce jour AUCUNE Filiere en base (confirme dans le commentaire de
f2b8e6a1c9d3 : "Pas de filieres ajoutees a ce stade") donc aucun
Utilisateur.filiere_id ne peut pointer vers cette Faculte. On renomme
directement la ligne existante plutot que d'en creer une nouvelle et
d'en laisser une orpheline.

Les 2 IES (Instituts d'Enseignement Superieur regionaux, rattaches
administrativement a l'Universite d'Antananarivo) sont ajoutes comme
nouvelles lignes Faculte.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a8f2c6b9e1'
down_revision: Union[str, None] = 'c9f1a6e3d8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOM_UNIVERSITE = "Universite d'Antananarivo"
ANCIEN_NOM_DEGS = "Faculte de Droit, d'Economie, de Gestion et de Sociologie (DEGS)"
NOUVEAU_NOM_DROIT = "Faculte de Droit et des Sciences Politiques"
NOUVEAU_NOM_EGS = "Faculte d'Economie, de Gestion et de Sociologie (EGS)"

NOUVEAUX_ETABLISSEMENTS = [
    "Institut d'Enseignement Superieur de Soavinandriana (Itasy)",
    "Institut d'Enseignement Superieur d'Antsirabe (Vakinankaratra)",
]


def upgrade() -> None:
    connexion = op.get_bind()

    universite_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = :nom").bindparams(nom=NOM_UNIVERSITE)
    ).scalar()
    if universite_id is None:
        return

    # --- 1) Renommer DEGS -> Faculte de Droit et des Sciences Politiques ---
    ancienne_faculte_id = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
        .bindparams(nom=ANCIEN_NOM_DEGS, uid=universite_id)
    ).scalar()
    if ancienne_faculte_id is not None:
        connexion.execute(
            sa.text("UPDATE faculte SET nom = :nouveau WHERE id = :fid")
            .bindparams(nouveau=NOUVEAU_NOM_DROIT, fid=ancienne_faculte_id)
        )

    # --- 2) Ajouter la Faculte EGS ---
    existe_egs = connexion.execute(
        sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
        .bindparams(nom=NOUVEAU_NOM_EGS, uid=universite_id)
    ).scalar()
    if existe_egs is None:
        connexion.execute(
            sa.text("INSERT INTO faculte (nom, universite_id) VALUES (:nom, :uid)")
            .bindparams(nom=NOUVEAU_NOM_EGS, uid=universite_id)
        )

    # --- 3) Ajouter les 2 IES regionaux ---
    for nom_etablissement in NOUVEAUX_ETABLISSEMENTS:
        deja = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=nom_etablissement, uid=universite_id)
        ).scalar()
        if deja is None:
            connexion.execute(
                sa.text("INSERT INTO faculte (nom, universite_id) VALUES (:nom, :uid)")
                .bindparams(nom=nom_etablissement, uid=universite_id)
            )


def downgrade() -> None:
    connexion = op.get_bind()

    universite_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = :nom").bindparams(nom=NOM_UNIVERSITE)
    ).scalar()
    if universite_id is None:
        return

    for nom_etablissement in NOUVEAUX_ETABLISSEMENTS:
        connexion.execute(
            sa.text("DELETE FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=nom_etablissement, uid=universite_id)
        )

    connexion.execute(
        sa.text("DELETE FROM faculte WHERE nom = :nom AND universite_id = :uid")
        .bindparams(nom=NOUVEAU_NOM_EGS, uid=universite_id)
    )

    connexion.execute(
        sa.text("UPDATE faculte SET nom = :ancien WHERE nom = :nouveau AND universite_id = :uid")
        .bindparams(ancien=ANCIEN_NOM_DEGS, nouveau=NOUVEAU_NOM_DROIT, uid=universite_id)
    )
