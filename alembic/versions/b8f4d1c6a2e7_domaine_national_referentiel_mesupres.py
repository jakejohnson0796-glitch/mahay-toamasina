"""domaine national + preparation import referentiel MESUPRES

Revision ID: b8f4d1c6a2e7
Revises: 9f376861b81b
Create Date: 2026-08-22 15:00:00.000000

Premiere etape de l'integration du fichier
mahay_universites_mentions_filieres_recensement.xlsx (recensement
national, 6 universites publiques + 22 privees — voir analyse
presentee a Jake avant cette migration).

Decisions prises avec Jake avant d'ecrire cette migration :
1) Domaine = entite NATIONALE (comme Mention), PAS un enfant strict de
   Faculte/Composante — voir la docstring du modele Domaine dans
   models.py pour la justification complete (le meme domaine porte un
   intitule different selon l'universite dans le fichier source).
2) Perimetre d'import : les 6 universites PUBLIQUES uniquement (les
   22 privees du fichier restent hors scope pour l'instant).
3) Fusion, jamais remplacement : Toamasina et Antananarivo ont deja
   des Filiere/Mention verifiees a la main avec sources citees
   (migrations a3c7f1e9b2d4, e5b9c3f7a2d8, b7e2d4a8c1f6,
   c9f1a6e3d8b2) — cette migration ne touche AUCUNE ligne existante.
   Le script scripts/import_academic_data.py (a lancer separement,
   apres cette migration) fait l'import proprement dit et ne cree de
   nouvelles Filiere que pour les 4 universites qui n'en ont encore
   aucune (Fianarantsoa, Mahajanga, Toliara, Antsiranana) ; pour
   Toamasina/Antananarivo il se contente d'un rattachement Domaine
   best-effort sur les Mention deja existantes, jamais d'insertion en
   double (voir le rapport qu'il produit).

Purement additive : nouvelle table + nouvelle colonne nullable.
Aucune ligne existante modifiee ou renumerotee.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b8f4d1c6a2e7'
down_revision: Union[str, None] = '9f376861b81b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'domaine',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('est_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_domaine_nom'), 'domaine', ['nom'], unique=True)

    with op.batch_alter_table('mention') as batch_op:
        batch_op.add_column(sa.Column('domaine_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_mention_domaine', 'domaine', ['domaine_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('mention') as batch_op:
        batch_op.drop_constraint('fk_mention_domaine', type_='foreignkey')
        batch_op.drop_column('domaine_id')

    op.drop_index(op.f('ix_domaine_nom'), table_name='domaine')
    op.drop_table('domaine')
