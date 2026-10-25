"""Restreint l'exécution directe de la fonction event-trigger Supabase.

La fonction public.rls_auto_enable() doit continuer à être déclenchée par
l'événement DDL PostgreSQL, mais elle ne doit pas être exposée comme RPC aux
rôles API. Cette migration est sans effet sur les bases où la fonction n'existe
pas (environnements locaux/CI standards hors Supabase).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3a9c1d8e742"
down_revision = "f2d8c1a4e630"
branch_labels = None
depends_on = None

_ROLES_API = ("anon", "authenticated", "service_role")


def _fonction_existe(bind) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT to_regprocedure('public.rls_auto_enable()') IS NOT NULL")
        ).scalar()
    )


def _roles_api_presents(bind) -> list[str]:
    return list(
        bind.execute(
            sa.text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('anon', 'authenticated', 'service_role') "
                "ORDER BY rolname"
            )
        ).scalars()
    )


def _revoquer_execution(bind) -> None:
    if bind.dialect.name != "postgresql" or not _fonction_existe(bind):
        return

    # PostgreSQL déclenche la fonction depuis pg_event_trigger par son OID ;
    # le droit EXECUTE de l'appelant ne sert pas à autoriser ce déclenchement.
    # Il peut donc être retiré des rôles API sans désactiver l'événement DDL.
    bind.exec_driver_sql(
        "REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC"
    )
    identifiant = bind.dialect.identifier_preparer.quote
    for role in _roles_api_presents(bind):
        if role in _ROLES_API:
            bind.exec_driver_sql(
                "REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM "
                + identifiant(role)
            )


def _restaurer_execution(bind) -> None:
    if bind.dialect.name != "postgresql" or not _fonction_existe(bind):
        return

    bind.exec_driver_sql(
        "GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO PUBLIC"
    )
    identifiant = bind.dialect.identifier_preparer.quote
    for role in _roles_api_presents(bind):
        if role in _ROLES_API:
            bind.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO "
                + identifiant(role)
            )


def upgrade() -> None:
    _revoquer_execution(op.get_bind())


def downgrade() -> None:
    _restaurer_execution(op.get_bind())
