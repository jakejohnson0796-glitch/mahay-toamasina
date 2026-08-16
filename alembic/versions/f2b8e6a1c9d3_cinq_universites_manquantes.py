"""cinq universites manquantes + backfill utilisateurs existants

Revision ID: f2b8e6a1c9d3
Revises: e1a4c9d2b7f5
Create Date: 2026-08-16 09:00:00.000000

Ajoute les 5 universites publiques manquantes (seule "Universite de
Toamasina" existait). Donnees sourcees (Wikipedia, AUF, sites officiels
des universites, pas inventees) :
- Universite d'Antananarivo : fondee 1961 (Universite de Madagascar),
  reorganisee en 1988, Antananarivo.
- Universite de Fianarantsoa : Centre Universitaire Regional des 1977,
  universite autonome depuis 1988, Fianarantsoa.
- Universite de Toliara : creee en 1971, statut universite en 1988,
  Toliara (campus Maninday).
- Universite de Mahajanga : CUR des 1977, universite depuis 1983,
  Mahajanga.
- Universite d'Antsiranana : etablie en 1976 (source : Africarrieres/
  systeme educatif Madagascar 2026). Ville confirmee ; annee de
  reorganisation en universite autonome non retrouvee avec certitude
  dans les sources consultees -> non affichee plutot que devinee.

Etablissements (facultes) ajoutes UNIQUEMENT quand confirmes par
plusieurs sources concordantes. Pas de filieres ajoutees a ce stade :
la liste precise des filieres/mentions de chaque universite necessite
une verification plus approfondie (voir le brief §8 : "ne pas inventer
une formation non confirmee, marquer A_VERIFIER"). Universite
d'Antsiranana : aucun etablissement ajoute, sources insuffisamment
precises trouvees a ce jour.

Tous les utilisateurs existants (avant cette migration, tous inscrits
via l'unique universite disponible) sont rattaches a l'Universite de
Toamasina — fait deja vrai, pas une supposition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b8e6a1c9d3'
down_revision: Union[str, None] = 'e1a4c9d2b7f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UNIVERSITES = [
    # (nom, ville, code)
    ("Universite d'Antananarivo", "Antananarivo", "UA"),
    ("Universite de Fianarantsoa", "Fianarantsoa", "UF"),
    ("Universite de Toliara", "Toliara", "UT"),
    ("Universite de Mahajanga", "Mahajanga", "UM"),
    ("Universite d'Antsiranana", "Antsiranana", "UDA"),
]

# (nom_universite, nom_faculte) — uniquement les etablissements
# confirmes par au moins deux sources concordantes lors de la
# recherche menee pour cette migration.
ETABLISSEMENTS = [
    ("Universite d'Antananarivo", "Faculte de Droit, d'Economie, de Gestion et de Sociologie (DEGS)"),
    ("Universite d'Antananarivo", "Faculte des Lettres et Sciences Humaines"),
    ("Universite d'Antananarivo", "Faculte de Medecine"),
    ("Universite d'Antananarivo", "Faculte des Sciences"),
    ("Universite d'Antananarivo", "Ecole Normale Superieure (ENS)"),
    ("Universite d'Antananarivo", "Ecole Superieure Polytechnique d'Antananarivo (ESPA)"),
    ("Universite d'Antananarivo", "Ecole Superieure des Sciences Agronomiques (ESSA)"),

    ("Universite de Fianarantsoa", "Faculte de Droit, d'Economie, de Gestion et des Sciences Sociales (DEGSS)"),
    ("Universite de Fianarantsoa", "Faculte des Sciences"),
    ("Universite de Fianarantsoa", "Faculte des Lettres et Sciences Humaines"),
    ("Universite de Fianarantsoa", "Ecole Normale Superieure (ENS)"),

    ("Universite de Toliara", "Faculte de Droit, Economie, Gestion et Sociologie (DEGS)"),
    ("Universite de Toliara", "Faculte des Lettres et Sciences Humaines et Sociales"),
    ("Universite de Toliara", "Faculte des Sciences"),
    ("Universite de Toliara", "Institut Halieutique et des Sciences Marines (IHSM)"),

    ("Universite de Mahajanga", "Faculte de Medecine"),
    ("Universite de Mahajanga", "Faculte des Sciences, de Technologies et de l'Environnement (FSTE)"),
]


def upgrade() -> None:
    connexion = op.get_bind()

    # L'ancien index unique global sur faculte.nom (pose par la toute
    # premiere migration du projet) empecherait d'inserer "Faculte des
    # Sciences" pour plus d'une universite. Remplace par une contrainte
    # composite (universite_id, nom) : le meme intitule reste interdit
    # en double au sein d'UNE universite, mais autorise entre universites
    # differentes — ce qui correspond a la realite (voir models.py).
    with op.batch_alter_table('faculte') as batch_op:
        batch_op.drop_index('ix_faculte_nom')
        batch_op.create_index('ix_faculte_nom', ['nom'])  # non-unique, garde la recherche rapide
        batch_op.create_unique_constraint('uq_faculte_universite_nom', ['universite_id', 'nom'])

    for nom, ville, code in UNIVERSITES:
        connexion.execute(
            sa.text("INSERT INTO universite (nom, ville, code, est_active) VALUES (:nom, :ville, :code, TRUE)")
            .bindparams(nom=nom, ville=ville, code=code)
        )

    for nom_universite, nom_faculte in ETABLISSEMENTS:
        universite_id = connexion.execute(
            sa.text("SELECT id FROM universite WHERE nom = :nom").bindparams(nom=nom_universite)
        ).scalar()
        connexion.execute(
            sa.text("INSERT INTO faculte (nom, universite_id) VALUES (:nom, :uid)")
            .bindparams(nom=nom_faculte, uid=universite_id)
        )

    # Tous les utilisateurs existants sont, dans les faits, deja des
    # etudiants de Toamasina (seule universite disponible jusqu'ici a
    # l'inscription) : rattachement direct, aucune ambiguite.
    universite_toamasina_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()
    connexion.execute(
        sa.text("UPDATE utilisateur SET universite_id = :uid WHERE universite_id IS NULL")
        .bindparams(uid=universite_toamasina_id)
    )


def downgrade() -> None:
    connexion = op.get_bind()
    universite_toamasina_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()
    connexion.execute(
        sa.text("UPDATE utilisateur SET universite_id = NULL WHERE universite_id = :uid")
        .bindparams(uid=universite_toamasina_id)
    )

    for nom_universite, nom_faculte in ETABLISSEMENTS:
        connexion.execute(
            sa.text("DELETE FROM faculte WHERE nom = :nom").bindparams(nom=nom_faculte)
        )

    for nom, _ville, _code in UNIVERSITES:
        connexion.execute(sa.text("DELETE FROM universite WHERE nom = :nom").bindparams(nom=nom))

    with op.batch_alter_table('faculte') as batch_op:
        batch_op.drop_constraint('uq_faculte_universite_nom', type_='unique')
        batch_op.drop_index('ix_faculte_nom')
        batch_op.create_index('ix_faculte_nom', ['nom'], unique=True)
