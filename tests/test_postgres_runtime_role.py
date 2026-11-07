"""Contrat de permissions du rôle runtime sur PostgreSQL jetable.

Ce test ne se connecte jamais à Supabase/Render. Il crée un rôle CI éphémère,
lui donne uniquement les droits DML attendus, puis vérifie RLS et l'absence
de droits de propriété/DDL.
"""
from __future__ import annotations

import os
import uuid

import psycopg2
import pytest


@pytest.mark.postgres
def test_role_runtime_est_dml_only_et_bypassrls_sur_postgres_jetable() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgres://")):
        pytest.skip("DATABASE_URL PostgreSQL requis (job postgres-smoke uniquement).")

    role = "mahay_runtime"
    table = f"runtime_rls_probe_{uuid.uuid4().hex[:12]}"
    conn = psycopg2.connect(database_url)
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone():
                cur.execute(f'DROP OWNED BY "{role}"')
                cur.execute(f'DROP ROLE "{role}"')
            cur.execute(
                f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB '
                "NOCREATEROLE INHERIT BYPASSRLS"
            )
            cur.execute("GRANT USAGE ON SCHEMA public TO mahay_runtime")
            cur.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                "TO mahay_runtime"
            )
            cur.execute(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
                "TO mahay_runtime"
            )
            cur.execute(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mahay_runtime"
            )
            cur.execute(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO mahay_runtime"
            )
            cur.execute(
                f'CREATE TABLE public."{table}" (id integer PRIMARY KEY, valeur text NOT NULL)'
            )
            cur.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
            cur.execute(f'INSERT INTO public."{table}" (id, valeur) VALUES (1, %s)', ("visible",))
            cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON public."{table}" TO mahay_runtime')

            cur.execute(
                """
                SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
                FROM pg_roles WHERE rolname = %s
                """,
                (role,),
            )
            attributes = cur.fetchone()
            assert attributes == (True, False, False, False, True)

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

            cur.execute(f'SET ROLE "{role}"')
            cur.execute(f'SELECT valeur FROM public."{table}" WHERE id = 1')
            assert cur.fetchone() == ("visible",), "Le rôle runtime doit passer RLS pour le backend."

            cur.execute(f'INSERT INTO public."{table}" (id, valeur) VALUES (2, %s)', ("insert",))
            cur.execute(f'UPDATE public."{table}" SET valeur = %s WHERE id = 2', ("updated",))
            cur.execute(f'DELETE FROM public."{table}" WHERE id = 2')

            cur.execute("SAVEPOINT deny_create")
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("CREATE TABLE public.runtime_must_not_create (id integer)")
            cur.execute("ROLLBACK TO SAVEPOINT deny_create")

            cur.execute("SAVEPOINT deny_alter")
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f'ALTER TABLE public."{table}" ADD COLUMN interdit integer')
            cur.execute("ROLLBACK TO SAVEPOINT deny_alter")
            cur.execute("RESET ROLE")
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS public."{table}"')
                cur.execute(f'DROP OWNED BY "{role}"')
                cur.execute(f'DROP ROLE IF EXISTS "{role}"')
        finally:
            conn.close()
