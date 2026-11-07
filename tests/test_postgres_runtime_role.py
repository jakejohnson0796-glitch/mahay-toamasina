"""Contrat de permissions du rôle runtime sur PostgreSQL jetable.

Ce test ne se connecte jamais à Supabase/Render. Il crée un rôle CI éphémère,
lui donne des droits DML et BYPASSRLS, puis vérifie l'accès backend et le refus
des opérations DDL. Le rôle et la table sont toujours supprimés.
"""
from __future__ import annotations

import os
import uuid

import psycopg2
from psycopg2 import sql
import pytest


@pytest.mark.postgres
def test_role_runtime_est_dml_only_et_bypassrls_sur_postgres_jetable() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgres://")):
        pytest.skip("DATABASE_URL PostgreSQL requis (job postgres-smoke uniquement).")

    suffix = uuid.uuid4().hex[:12]
    role = f"mahay_rt_{suffix}"
    table = f"runtime_rls_probe_{suffix}"
    admin = psycopg2.connect(database_url)
    admin.autocommit = True
    runtime = None

    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "INHERIT BYPASSRLS"
            ).format(sql.Identifier(role)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            cur.execute(sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(sql.Identifier(role)))
            cur.execute(sql.SQL(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}"
            ).format(sql.Identifier(role)))
            cur.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(sql.Identifier(role)))
            cur.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
            ).format(sql.Identifier(role)))
            cur.execute(sql.SQL(
                "CREATE TABLE public.{} (id integer PRIMARY KEY, valeur text NOT NULL)"
            ).format(sql.Identifier(table)))
            cur.execute(sql.SQL("ALTER TABLE public.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(table)))
            cur.execute(sql.SQL(
                "INSERT INTO public.{} (id, valeur) VALUES (1, 'visible')"
            ).format(sql.Identifier(table)))
            cur.execute(sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{} TO {}"
            ).format(sql.Identifier(table), sql.Identifier(role)))
            cur.execute(
                """
                SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                  AND NOT (
                    has_table_privilege(%s, c.oid, 'SELECT')
                    AND has_table_privilege(%s, c.oid, 'INSERT')
                    AND has_table_privilege(%s, c.oid, 'UPDATE')
                    AND has_table_privilege(%s, c.oid, 'DELETE')
                  )
                """,
                (role, role, role, role),
            )
            assert cur.fetchone()[0] == 0, "Le rôle runtime doit avoir le DML sur les tables applicatives existantes."

            cur.execute(
                """
                SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
                FROM pg_roles WHERE rolname = %s
                """,
                (role,),
            )
            assert cur.fetchone() == (True, False, False, False, True)

            cur.execute(
                """
                SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                  AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = %s)
                """,
                (role,),
            )
            assert cur.fetchone()[0] == 0, "Le rôle runtime ne doit posséder aucune table."

        runtime = psycopg2.connect(database_url)
        with runtime:
            with runtime.cursor() as cur:
                cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
                cur.execute(sql.SQL("SELECT valeur FROM public.{} WHERE id = 1").format(sql.Identifier(table)))
                assert cur.fetchone() == ("visible",), "Le rôle backend doit accéder à la table malgré RLS activé."

                cur.execute(sql.SQL("INSERT INTO public.{} (id, valeur) VALUES (2, 'insert')").format(sql.Identifier(table)))
                cur.execute(sql.SQL("UPDATE public.{} SET valeur = 'updated' WHERE id = 2").format(sql.Identifier(table)))
                cur.execute(sql.SQL("DELETE FROM public.{} WHERE id = 2").format(sql.Identifier(table)))

                cur.execute("SAVEPOINT deny_create")
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute("CREATE TABLE public.runtime_must_not_create (id integer)")
                cur.execute("ROLLBACK TO SAVEPOINT deny_create")

                cur.execute("SAVEPOINT deny_alter")
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute(sql.SQL("ALTER TABLE public.{} ADD COLUMN interdit integer").format(sql.Identifier(table)))
                cur.execute("ROLLBACK TO SAVEPOINT deny_alter")
    finally:
        if runtime is not None:
            runtime.close()
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("DROP TABLE IF EXISTS public.{}").format(sql.Identifier(table)))
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        finally:
            admin.close()
