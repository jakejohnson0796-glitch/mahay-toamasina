"""Déplace unaccent hors de public sans casser la recherche plein texte.

Supabase réserve public aux objets exposés par l'API. L'extension unaccent
est relocatable ; le dictionnaire lié à public.mahay_french référence les
objets PostgreSQL par OID, qui restent stables lors d'un SET SCHEMA.
Le search_path Supabase comprend déjà le schéma extensions.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3d8a9c2e5b1"
down_revision = "f1c7a9d3e2b6"
branch_labels = None
depends_on = None

EXTENSION_NAME = "unaccent"
TARGET_SCHEMA = "extensions"


def _schema_extension(bind) -> str | None:
    return bind.execute(
        sa.text(
            """
            SELECT n.nspname
            FROM pg_extension e
            JOIN pg_namespace n ON n.oid=e.extnamespace
            WHERE e.extname=:extension
            """
        ),
        {"extension": EXTENSION_NAME},
    ).scalar_one_or_none()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    bind.execute(sa.text("CREATE SCHEMA IF NOT EXISTS extensions"))
    schema_actuel = _schema_extension(bind)

    if schema_actuel is None:
        bind.execute(
            sa.text(
                "CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions"
            )
        )
        schema_actuel = _schema_extension(bind)

    if schema_actuel != TARGET_SCHEMA:
        relocatable = bind.execute(
            sa.text(
                "SELECT extrelocatable FROM pg_extension "
                "WHERE extname=:extension"
            ),
            {"extension": EXTENSION_NAME},
        ).scalar_one_or_none()
        if not relocatable:
            raise RuntimeError(
                "L'extension unaccent existe mais n'est pas relocatable ; "
                "le schéma public n'a pas été modifié."
            )
        bind.execute(
            sa.text("ALTER EXTENSION unaccent SET SCHEMA extensions")
        )

    # Supabase possède déjà ces privilèges sur extensions. Les GRANT sont
    # idempotents et préparent aussi les rôles simulés par le smoke PostgreSQL.
    roles = bind.execute(
        sa.text(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname = ANY(:roles) ORDER BY rolname"
        ),
        {"roles": ["anon", "authenticated", "service_role"]},
    ).scalars().all()
    preparer = bind.dialect.identifier_preparer
    for role in roles:
        role_quote = preparer.quote(role)
        bind.execute(
            sa.text(f"GRANT USAGE ON SCHEMA extensions TO {role_quote}")
        )

    # La configuration mahay_french conserve les OID des dictionnaires après
    # ALTER EXTENSION SET SCHEMA ; ne pas reconstruire son mapping à l'aveugle.
    config_presente = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_ts_config c
            JOIN pg_namespace n ON n.oid=c.cfgnamespace
            WHERE n.nspname='public' AND c.cfgname='mahay_french'
            """
        )
    ).first()
    if config_presente is None:
        raise RuntimeError(
            "La configuration public.mahay_french est absente ; "
            "la migration refuse de déplacer unaccent sans elle."
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    schema_actuel = _schema_extension(bind)
    if schema_actuel == TARGET_SCHEMA:
        bind.execute(
            sa.text("ALTER EXTENSION unaccent SET SCHEMA public")
        )
