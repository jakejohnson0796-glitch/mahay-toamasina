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
#
# connect_timeout=10 (Postgres uniquement) : sans ca, une connexion qui ne
# repond pas (reseau capricieux, pooler Supabase qui traine...) fait
# attendre indefiniment sans jamais afficher d'erreur — exactement le
# symptome observe en prod (page qui reste bloquee sur "Internal Server
# Error" generique, rien dans les logs). Avec ce timeout, l'echec est
# rapide et explicite.
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {
        "connect_timeout": 10,
        # statement_timeout impose cote SERVEUR Postgres (pas cote client) :
        # meme si la connexion TCP est etablie sans souci (ce qui semble
        # etre le cas — connect_timeout ne s'est jamais declenche), une
        # requete peut rester bloquee en attendant une reponse qui
        # n'arrive jamais (souci reseau, pooler capricieux...). Sans ca,
        # rien ne borne cette attente et l'app peut se figer pour
        # toujours, exactement le symptome observe.
        "options": "-c statement_timeout=10000",
    }

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    # pool_pre_ping : verifie qu'une connexion recyclee depuis le pool est
    # toujours valide avant de l'utiliser (fait un petit round-trip SELECT 1
    # au prealable). Evite d'utiliser une connexion morte silencieusement
    # coupee cote pooler Supabase apres un moment d'inactivite.
    pool_pre_ping=True,
    # pool_recycle : force le renouvellement des connexions au bout de 5
    # minutes, avant que le pooler Supabase ne les ferme lui-meme de son
    # cote (comportement frequent des poolers PgBouncer-like, qui coupent
    # les connexions inactives sans le signaler proprement au client).
    pool_recycle=300,
    # pool_size/max_overflow volontairement bas : ce projet n'a pas besoin
    # de beaucoup de connexions simultanees, et un pool trop genereux cote
    # app peut a lui seul saturer la limite du pooler Supabase (souvent
    # basse sur les plans gratuits) si plusieurs process app tournent en
    # parallele (dev + prod, ou plusieurs `uvicorn` lances par erreur).
    pool_size=3,
    max_overflow=2,
    # pool_timeout : si le pool est plein (toutes les connexions deja
    # utilisees ailleurs), on echoue au bout de 10s avec une erreur claire
    # plutot que d'attendre indefiniment qu'une connexion se libere.
    pool_timeout=10,
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
