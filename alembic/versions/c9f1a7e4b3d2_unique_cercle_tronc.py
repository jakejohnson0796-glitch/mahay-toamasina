"""Déduplication SQL des cercles tronc commun actifs.

Revision: c9f1a7e4b3d2
Replaces: b4c6d8e0f2a4

La migration est idempotente : certaines bases de production possèdent déjà
l'index unique créé lors d'une tentative antérieure.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text


revision: str = "c9f1a7e4b3d2"
down_revision: Union[str, Sequence[str], None] = "b4c6d8e0f2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fusionner_troncs_existants(connection) -> None:
    groupes = connection.execute(
        text(
            """
            SELECT mention_id, niveau, MIN(id) AS survivant, COUNT(*) AS nb
            FROM cercleetude
            WHERE statut = 'ACTIF'
              AND mention_id IS NOT NULL
              AND filiere_id IS NULL
              AND niveau IS NOT NULL
            GROUP BY mention_id, niveau
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    for mention_id, niveau, survivant, _nb in groupes:
        perdants = connection.execute(
            text(
                """
                SELECT id
                FROM cercleetude
                WHERE statut = 'ACTIF'
                  AND mention_id = :mention_id
                  AND filiere_id IS NULL
                  AND niveau = :niveau
                  AND id <> :survivant
                ORDER BY id
                """
            ),
            {
                "mention_id": mention_id,
                "niveau": niveau,
                "survivant": survivant,
            },
        ).fetchall()

        for (perdant,) in perdants:
            connection.execute(
                text(
                    """
                    DELETE FROM membrecercle
                    WHERE cercle_id = :perdant
                      AND utilisateur_id IN (
                          SELECT utilisateur_id
                          FROM membrecercle
                          WHERE cercle_id = :survivant
                      )
                    """
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    """
                    UPDATE membrecercle
                    SET cercle_id = :survivant
                    WHERE cercle_id = :perdant
                    """
                ),
                {"perdant": perdant, "survivant": survivant},
            )

            connection.execute(
                text(
                    "UPDATE demandeadhesioncercle SET cercle_id = :survivant "
                    "WHERE cercle_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    "UPDATE messagecercle SET cercle_id = :survivant "
                    "WHERE cercle_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    "UPDATE document SET cercle_id = :survivant "
                    "WHERE cercle_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    "UPDATE notification SET cercle_id = :survivant "
                    "WHERE cercle_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    "UPDATE themedujour SET cercle_id = :survivant "
                    "WHERE cercle_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )
            connection.execute(
                text(
                    "UPDATE demandecreationcercle SET cercle_cree_id = :survivant "
                    "WHERE cercle_cree_id = :perdant"
                ),
                {"perdant": perdant, "survivant": survivant},
            )

            connection.execute(
                text("DELETE FROM cercleetude WHERE id = :perdant"),
                {"perdant": perdant},
            )


def upgrade() -> None:
    bind = op.get_bind()
    _fusionner_troncs_existants(bind)

    # Une tentative précédente peut avoir créé l'index avant que la version
    # Alembic ne soit enregistrée. On le conserve dans ce cas.
    indexes = {
        index.get("name")
        for index in inspect(bind).get_indexes("cercleetude")
        if index.get("name")
    }

    if "ix_cercle_tronc_unique_actif" not in indexes:
        op.create_index(
            "ix_cercle_tronc_unique_actif",
            "cercleetude",
            ["mention_id", "niveau"],
            unique=True,
            sqlite_where=text(
                "statut = 'ACTIF' AND mention_id IS NOT NULL "
                "AND filiere_id IS NULL AND niveau IS NOT NULL"
            ),
            postgresql_where=text(
                "statut = 'ACTIF' AND mention_id IS NOT NULL "
                "AND filiere_id IS NULL AND niveau IS NOT NULL"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {
        index.get("name")
        for index in inspect(bind).get_indexes("cercleetude")
        if index.get("name")
    }
    if "ix_cercle_tronc_unique_actif" in indexes:
        op.drop_index(
            "ix_cercle_tronc_unique_actif",
            table_name="cercleetude",
        )
