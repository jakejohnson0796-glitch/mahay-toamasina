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

from sqlmodel import SQLModel, Session, create_engine

from .config import parametres

DATABASE_URL = parametres.database_url

# check_same_thread=False : necessaire uniquement pour SQLite, car FastAPI
# peut traiter les requetes sur plusieurs threads alors que SQLite est
# mono-thread par defaut. Postgres n'en a pas besoin.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

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
    command.upgrade(config_alembic, "head")


def get_session():
    """Dependance FastAPI : fournit une session DB et la ferme proprement."""
    with Session(engine) as session:
        yield session
