"""Stockage explicite de la composante academique dans les profils.

Revision ID: c2f4a8d1b7e6
Revises: b8d2f4a1c7e9

Le formulaire d'inscription demandait deja la composante, mais le modele
Utilisateur ne la persistait pas. Cela rendait impossible une hierarchie
complete pour les etudiants en tronc commun (sans Filiere). La migration
ajoute donc faculte_id a Utilisateur et nouvelle_faculte_id aux demandes
de changement. Les profils specialises existants sont backfilles depuis
Filiere.faculte_id ; les profils de tronc commun ne sont backfilles que
lorsqu'une seule composante de leur universite porte leur mention, afin
de ne jamais deviner une donnee ambigue.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f4a8d1b7e6"
down_revision: Union[str, None] = "b8d2f4a1c7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rows(conn, sql: str, **params):
    return list(conn.execute(sa.text(sql), params).mappings())


def _backfill_composantes_profils(conn) -> None:
    # 1) Specialises : relation certaine via la Filiere.
    conn.execute(sa.text(
        """
        UPDATE utilisateur
        SET faculte_id = (
            SELECT faculte_id
            FROM filiere
            WHERE filiere.id = utilisateur.filiere_id
        )
        WHERE faculte_id IS NULL
          AND filiere_id IS NOT NULL
        """
    ))

    # 2) Tronc commun : seulement si une seule composante de l'universite
    # propose cette mention. Sinon, on laisse NULL pour demander a
    # l'utilisateur de choisir explicitement.
    candidats = _rows(
        conn,
        """
        SELECT u.id AS utilisateur_id, f.faculte_id
        FROM utilisateur u
        JOIN filiere f ON f.mention_id = u.mention_id
        JOIN faculte fa ON fa.id = f.faculte_id AND fa.universite_id = u.universite_id
        WHERE u.faculte_id IS NULL
          AND u.filiere_id IS NULL
          AND u.universite_id IS NOT NULL
          AND u.mention_id IS NOT NULL
        GROUP BY u.id, f.faculte_id
        ORDER BY u.id, f.faculte_id
        """
    )

    par_utilisateur = {}
    for ligne in candidats:
        par_utilisateur.setdefault(ligne["utilisateur_id"], []).append(ligne["faculte_id"])

    for utilisateur_id, faculte_ids in par_utilisateur.items():
        if len(faculte_ids) == 1:
            conn.execute(
                sa.text("UPDATE utilisateur SET faculte_id = :faculte_id WHERE id = :id"),
                {"faculte_id": faculte_ids[0], "id": utilisateur_id},
            )


def upgrade() -> None:
    with op.batch_alter_table("utilisateur") as batch_op:
        batch_op.add_column(sa.Column("faculte_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_utilisateur_faculte_id", ["faculte_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_utilisateur_faculte_id_faculte",
            "faculte",
            ["faculte_id"],
            ["id"],
        )

    with op.batch_alter_table("demandechangementfiliere") as batch_op:
        batch_op.add_column(sa.Column("nouvelle_faculte_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_demande_changement_nouvelle_faculte",
            "faculte",
            ["nouvelle_faculte_id"],
            ["id"],
        )

    conn = op.get_bind()
    _backfill_composantes_profils(conn)


def downgrade() -> None:
    with op.batch_alter_table("demandechangementfiliere") as batch_op:
        batch_op.drop_constraint(
            "fk_demande_changement_nouvelle_faculte",
            type_="foreignkey",
        )
        batch_op.drop_column("nouvelle_faculte_id")

    with op.batch_alter_table("utilisateur") as batch_op:
        batch_op.drop_constraint(
            "fk_utilisateur_faculte_id_faculte",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_utilisateur_faculte_id")
        batch_op.drop_column("faculte_id")
