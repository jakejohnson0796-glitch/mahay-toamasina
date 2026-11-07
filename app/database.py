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

from sqlmodel import SQLModel, Session, create_engine

from .config import parametres

DATABASE_URL = parametres.database_url
MIGRATION_DATABASE_URL = parametres.migration_database_url or DATABASE_URL


def _creer_engine(database_url: str):
    """Construit un moteur avec les mêmes garde-fous pour chaque compte."""
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        connect_args = {
            "connect_timeout": 10,
            "options": "-c statement_timeout=10000",
        }

    moteur = create_engine(
        database_url,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=3,
        max_overflow=2,
        pool_timeout=10,
    )

    if database_url.startswith("sqlite"):
        @event.listens_for(moteur, "connect")
        def _enregistrer_fonction_normalisation_sqlite(dbapi_connection, _record):
            from .texte_normalise import normaliser
            dbapi_connection.create_function("mahay_normaliser", 1, normaliser)

    return moteur


# Le backend n'utilise que ce moteur pour les requêtes de l'application.
engine = _creer_engine(DATABASE_URL)

# Alembic dispose d'un moteur distinct et d'un compte distinct en production.
# Le fallback sur DATABASE_URL est conservé pour les environnements locaux/CI.
migration_engine = (
    engine
    if MIGRATION_DATABASE_URL == DATABASE_URL
    else _creer_engine(MIGRATION_DATABASE_URL)
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
