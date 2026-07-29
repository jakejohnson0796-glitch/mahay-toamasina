"""
Connexion a la base de donnees.

V1 demarrait uniquement sur SQLite. Desormais, si DATABASE_URL est definie
(dans .env ou l'environnement) et pointe vers Postgres — typiquement l'URI
Supabase fournie dans Project Settings > Database — on bascule dessus.
Sinon, fallback sur SQLite local, exactement comme avant. SQLModel/SQLAlchemy
abstraient le moteur, donc aucun autre fichier n'a besoin de savoir lequel
des deux est utilise.
"""
from sqlmodel import SQLModel, Session, create_engine

from .config import parametres

DATABASE_URL = parametres.database_url

# check_same_thread=False : necessaire uniquement pour SQLite, car FastAPI
# peut traiter les requetes sur plusieurs threads alors que SQLite est
# mono-thread par defaut. Postgres n'en a pas besoin.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def creer_tables() -> None:
    """Cree les tables si elles n'existent pas encore. Appele au demarrage.
    Fonctionne identiquement sur SQLite et sur Postgres/Supabase."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependance FastAPI : fournit une session DB et la ferme proprement."""
    with Session(engine) as session:
        yield session
