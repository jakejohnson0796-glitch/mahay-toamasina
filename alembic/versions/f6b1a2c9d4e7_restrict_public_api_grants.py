"""Restrict direct Supabase Data API table grants.

MITARIDALA uses its server-side PostgreSQL connection for application data and
uses the Supabase service key only for object storage. The API roles therefore
must not inherit blanket privileges on the application schema. Row-level
security remains enabled; this migration removes unnecessary direct grants and
prevents the default privileges for future objects from silently restoring them.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6b1a2c9d4e7"
down_revision = "f3a9c1d8e742"
branch_labels = None
depends_on = None

_API_ROLES = ("anon", "authenticated")


def _api_roles_present(bind) -> list[str]:
    return list(
        bind.execute(
            sa.text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('anon', 'authenticated') "
                "ORDER BY rolname"
            )
        ).scalars()
    )


def _quoted_roles(bind, roles: list[str]) -> str:
    quote = bind.dialect.identifier_preparer.quote
    return ", ".join(quote(role) for role in roles if role in _API_ROLES)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    roles = _api_roles_present(bind)
    if roles:
        targets = _quoted_roles(bind, roles)

        # RLS with no policies currently denies row access, but privileges such
        # as TRUNCATE, REFERENCES and TRIGGER are not governed by row policies.
        # The API roles do not need direct table access: FastAPI uses DATABASE_URL.
        bind.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {targets}"
        )
        bind.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {targets}"
        )

        # Remove per-schema defaults so new Alembic-created tables/sequences
        # do not silently regain API-role access.
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL PRIVILEGES ON TABLES FROM {targets}"
        )
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL PRIVILEGES ON SEQUENCES FROM {targets}"
        )
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE EXECUTE ON FUNCTIONS FROM {targets}"
        )

    # PostgreSQL otherwise grants EXECUTE on newly created functions to PUBLIC
    # by default. Keep that default closed for future app-owned functions.
    # Existing extension functions (for example unaccent, owned by supabase_admin)
    # are not changed by this default-privilege alteration.
    bind.exec_driver_sql(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    roles = _api_roles_present(bind)
    if roles:
        targets = _quoted_roles(bind, roles)
        bind.exec_driver_sql(
            f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {targets}"
        )
        bind.exec_driver_sql(
            f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {targets}"
        )
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL PRIVILEGES ON TABLES TO {targets}"
        )
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT ALL PRIVILEGES ON SEQUENCES TO {targets}"
        )
        bind.exec_driver_sql(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"GRANT EXECUTE ON FUNCTIONS TO {targets}"
        )

    bind.exec_driver_sql(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres "
        "GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
    )
