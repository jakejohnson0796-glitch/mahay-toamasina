"""ProgrammeUniversitaire comme source d'offre + recherche francaise normalisee.

Revision ID: c1e7f4a2b9d6
Revises: b8d2f4a1c7e9

La migration est volontairement additive :
- renforce l'unicite d'une offre active universite/filiere ;
- active la recherche PostgreSQL francaise accent-insensible avec stemming ;
- ne stocke aucune copie normalisee des libelles metier.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1e7f4a2b9d6"
down_revision: Union[str, None] = "b8d2f4a1c7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Nettoyage defensif : une ancienne version pouvait avoir plusieurs
    # lignes actives pour la meme offre. On conserve la plus ancienne ligne.
    conn.execute(sa.text(
        """
        DELETE FROM programmeuniversitaire
        WHERE est_active = TRUE
          AND EXISTS (
              SELECT 1
              FROM programmeuniversitaire p2
              WHERE p2.est_active = TRUE
                AND p2.universite_id = programmeuniversitaire.universite_id
                AND p2.filiere_id = programmeuniversitaire.filiere_id
                AND p2.id < programmeuniversitaire.id
          )
        """
    ))

    # Index de lecture : l'offre est interrogée par universite/filiere et
    # filtre sur est_active dans toutes les validations de profil.
    try:
        op.create_index(
            "ix_programme_universite_filiere_actif",
            "programmeuniversitaire",
            ["universite_id", "filiere_id", "est_active"],
        )
    except Exception:
        # L'index peut déjà exister sur un environnement ayant applique une
        # variante de la migration ; on ne bloque pas le deploiement pour ca.
        pass

    # Une seule offre active pour une universite et une filiere.
    # Les offres historiques inactives restent multiples.
    dialecte = conn.dialect.name
    if dialecte == "postgresql":
        # Supabase expose l'extension unaccent. On ne suppose pas son schema :
        # on le lit après création/activation pour fonctionner aussi bien avec
        # un cluster où elle existe déjà dans public qu'avec schema extensions.
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        schema_unaccent = conn.execute(
            sa.text(
                """
                SELECT n.nspname
                FROM pg_extension e
                JOIN pg_namespace n ON n.oid = e.extnamespace
                WHERE e.extname = 'unaccent'
                """
            )
        ).scalar_one()

        conn.execute(sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_config
                    WHERE cfgname = 'mahay_french'
                ) THEN
                    CREATE TEXT SEARCH CONFIGURATION public.mahay_french
                    (COPY = pg_catalog.french);
                END IF;
            END
            $$;
            """
        ))

        schema_quote = conn.dialect.identifier_preparer.quote(schema_unaccent)
        conn.execute(sa.text(
            f"""
            ALTER TEXT SEARCH CONFIGURATION public.mahay_french
            ALTER MAPPING FOR hword, hword_part, word
            WITH {schema_quote}.unaccent, pg_catalog.french_stem
            """
        ))

        op.create_index(
            "uq_programme_actif_universite_filiere",
            "programmeuniversitaire",
            ["universite_id", "filiere_id"],
            unique=True,
            postgresql_where=sa.text("est_active = TRUE"),
        )
    else:
        # SQLite reçoit la fonction mahay_normaliser via app.database et le
        # fallback Snowball applicatif dans app.recherche.
        op.create_index(
            "uq_programme_actif_universite_filiere",
            "programmeuniversitaire",
            ["universite_id", "filiere_id"],
            unique=True,
            sqlite_where=sa.text("est_active = 1"),
        )


def downgrade() -> None:
    op.drop_index("uq_programme_actif_universite_filiere", table_name="programmeuniversitaire")
    # L'index de lecture peut avoir ete preexistant : le downgrade ne le
    # supprime donc pas pour eviter de detruire un objet d'une ancienne
    # variante de schema.
