"""
Connexion a la base de donnees.

V1 demarrait uniquement sur SQLite. Desormais, si DATABASE_URL est definie
(dans .env ou l'environnement) et pointe vers Postgres — typiquement l'URI
Supabase fournie dans Project Settings > Database — on bascule dessus.
Sinon, fallback sur SQLite local, exactement comme avant. SQLModel/SQLAlchemy
abstraient le moteur, donc aucun autre fichier n'a besoin de savoir lequel
des deux est utilise.
"""
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

from sqlmodel import SQLModel, Session, create_engine

from .config import parametres

DATABASE_URL = parametres.database_url
MIGRATION_DATABASE_URL = parametres.migration_database_url or DATABASE_URL


# Les requêtes HTTP doivent échouer rapidement plutôt que garder un worker occupé.
TEMPS_REQUETE_RUNTIME_MS = 10_000
# Les backfills et les DDL peuvent dépasser le délai des requêtes HTTP.
TEMPS_REQUETE_MIGRATION_MS = 300_000
# Une migration ne doit pas rester bloquée indéfiniment derrière un verrou SQL.
TEMPS_ATTENTE_VERROU_MIGRATION_MS = 30_000


def _arguments_connexion(database_url: str, *, pour_migrations: bool = False) -> dict[str, object]:
    """Construit des options séparées pour les requêtes HTTP et Alembic."""
    if make_url(database_url).get_backend_name() == "sqlite":
        return {"check_same_thread": False}

    timeout = (
        TEMPS_REQUETE_MIGRATION_MS
        if pour_migrations
        else TEMPS_REQUETE_RUNTIME_MS
    )
    options = f"-c statement_timeout={timeout}"
    if pour_migrations:
        options += f" -c lock_timeout={TEMPS_ATTENTE_VERROU_MIGRATION_MS}"
    return {"connect_timeout": 10, "options": options}


def _creer_engine(database_url: str, *, pour_migrations: bool = False):
    """Construit un moteur adapté au backend et au type de connexion."""
    url = make_url(database_url)
    est_sqlite = url.get_backend_name() == "sqlite"
    options = {
        "echo": False,
        "connect_args": _arguments_connexion(
            database_url, pour_migrations=pour_migrations
        ),
        "pool_pre_ping": True,
    }
    if est_sqlite and url.database in (None, "", ":memory:"):
        # Une base SQLite en mémoire doit partager une seule connexion ; deux
        # moteurs indépendants créeraient deux bases différentes.
        moteur = create_engine(
            database_url,
            poolclass=StaticPool,
            **options,
        )
    else:
        moteur = create_engine(
            database_url,
            pool_recycle=300,
            pool_size=3,
            max_overflow=2,
            pool_timeout=10,
            **options,
        )

    if est_sqlite:
        @event.listens_for(moteur, "connect")
        def _enregistrer_fonction_normalisation_sqlite(dbapi_connection, _record):
            from .texte_normalise import normaliser
            dbapi_connection.create_function("mahay_normaliser", 1, normaliser)

    return moteur


def _creer_engine_migration(
    database_url: str,
    migration_database_url: str,
    engine_runtime,
):
    """Partage SQLite lorsqu'il n'y a pas de compte/URL séparé."""
    if (
        database_url == migration_database_url
        and make_url(database_url).get_backend_name() == "sqlite"
    ):
        return engine_runtime
    return _creer_engine(migration_database_url, pour_migrations=True)


# Le backend n'utilise que ce moteur pour les requêtes de l'application.
engine = _creer_engine(DATABASE_URL)

# Alembic utilise un moteur distinct pour PostgreSQL afin d'avoir ses propres
# délais. SQLite réutilise le moteur runtime lorsque l'URL est identique, en
# particulier pour préserver la même base en mémoire pendant les tests locaux.
migration_engine = _creer_engine_migration(
    DATABASE_URL, MIGRATION_DATABASE_URL, engine
)


RACINE_PROJET = Path(__file__).resolve().parent.parent


def executer_migrations() -> None:
    """Applique les migrations Alembic jusqu'a la derniere version.
    Remplace l'ancien creer_tables()/create_all() : contrairement a
    create_all(), ceci met aussi a jour les tables DEJA existantes
    (nouvelles colonnes, nouvelles contraintes...), ce qui est necessaire
    maintenant que le schema continue d'evoluer apres la mise en prod.
    Appele au demarrage de l'app, comme le faisait creer_tables() avant —
    donc aucun geste manuel supplementaire requis sur Render."""
    from alembic import command
    from alembic.config import Config

    config_alembic = Config(str(RACINE_PROJET / "alembic.ini"))
    config_alembic.set_main_option("script_location", str(RACINE_PROJET / "alembic"))
    # IMPORTANT : empeche alembic/env.py d'appeler logging.config.fileConfig()
    # (qui ne s'execute normalement que si config_file_name est renseigne).
    # fileConfig() reconfigure le systeme de logging GLOBAL de Python, ce
    # qui peut entrer en conflit avec celui deja mis en place par uvicorn
    # et bloquer indefiniment sur certaines configurations Windows (bug
    # constate : le process reste bloque juste apres la fin reelle de
    # executer_migrations(), sans jamais atteindre "Application startup
    # complete"). On n'a de toute facon pas besoin de cette configuration
    # de logging specifique a Alembic ici : nos propres print() et les
    # logs d'uvicorn suffisent amplement.
    config_alembic.config_file_name = None
    command.upgrade(config_alembic, "head")


def get_session():
    """Dependance FastAPI : fournit une session DB et la ferme proprement."""
    with Session(engine) as session:
        yield session
