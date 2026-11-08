-- Provisioning explicite du rôle runtime Mahay.
-- À exécuter par un administrateur PostgreSQL après validation de la sauvegarde.
-- Ne pas intégrer à Alembic : les rôles sont cluster-wide et le secret ne doit
-- jamais être stocké dans le dépôt ou dans l'historique des migrations.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mahay_runtime') THEN
        CREATE ROLE mahay_runtime
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
    ELSE
        ALTER ROLE mahay_runtime
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
    END IF;
END
$$;

-- DML uniquement : aucun droit CREATE/ALTER/DROP ni propriété des objets.
GRANT CONNECT ON DATABASE postgres TO mahay_runtime;
GRANT USAGE ON SCHEMA public TO mahay_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO mahay_runtime;
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA public TO mahay_runtime;

-- Les objets futurs créés par le rôle de migration postgres restent accessibles
-- au runtime sans lui conférer de privilèges DDL.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mahay_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO mahay_runtime;

-- Après exécution, ouvrir psql comme administrateur et définir le secret
-- interactivement (ne jamais le mettre dans ce fichier) :
--   \\password mahay_runtime
-- Puis utiliser ce secret dans DATABASE_URL des deux services Render.
