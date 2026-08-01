"""
Point d'entree de MAHAY Toamasina.

Lancer avec :  uvicorn app.main:app --reload
(depuis la racine du projet, apres avoir installe requirements.txt)
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select

from .config import parametres
from .database import executer_migrations, engine, get_session
from .models import Faculte, Document, StatutDocument
from .routers import auth_router, documents_router, sponsoring_router, cercles_router, abonnement_router, dashboard_router, quiz_router
from .seed_data import peupler_donnees_initiales

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="MAHAY Toamasina")

# Cle de session : lue depuis SESSION_SECRET_KEY (.env) si presente, sinon
# retombe sur la valeur de demo. A REMPLACER avant toute mise en ligne
# reelle (voir .env.example).
app.add_middleware(SessionMiddleware, secret_key=parametres.session_secret_key)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(auth_router.router)
app.include_router(documents_router.router)
app.include_router(sponsoring_router.router)
app.include_router(cercles_router.router)
app.include_router(abonnement_router.router)
app.include_router(dashboard_router.router)
app.include_router(quiz_router.router)


def _masquer_mot_de_passe(url: str) -> str:
    """Renvoie l'URL de connexion avec le mot de passe remplace par ****,
    pour affichage dans les logs. Utilise urllib.parse (plutot qu'un
    decoupage manuel sur '@'/':') car un mot de passe peut lui-meme
    contenir '@', ':' ou d'autres caracteres speciaux — un decoupage
    naif peut alors soit laisser une partie du mot de passe en clair,
    soit tronquer le nom d'utilisateur/le schema par erreur."""
    morceaux = urlsplit(url)
    if not morceaux.password:
        return url

    identifiants = f"{morceaux.username}:****" if morceaux.username else "****"
    hote = f"{morceaux.hostname}:{morceaux.port}" if morceaux.port else (morceaux.hostname or "")
    netloc_masque = f"{identifiants}@{hote}" if hote else identifiants

    return urlunsplit((morceaux.scheme, netloc_masque, morceaux.path, morceaux.query, morceaux.fragment))


@app.on_event("startup")
def au_demarrage() -> None:
    # --- DEBUG : affiche clairement quelle base de donnees est utilisee ---
    url_affichee = _masquer_mot_de_passe(parametres.database_url)

    if url_affichee.startswith("sqlite"):
        print(f"[DEBUG DATABASE] SQLite local utilise : {url_affichee}")
        print("[DEBUG DATABASE] Si tu attendais Supabase, verifie que DATABASE_URL")
        print("[DEBUG DATABASE] est bien rempli dans .env ET que le serveur a ete")
        print("[DEBUG DATABASE] completement redemarre (Ctrl+C puis relance, pas juste --reload).")
    else:
        print(f"[DEBUG DATABASE] Connexion Postgres/Supabase visee : {url_affichee}")

    # --- Connexion + migrations Alembic, avec erreur explicite si echec ---
    try:
        executer_migrations()
        print("[DEBUG DATABASE] Migrations Alembic appliquees — connexion OK.")
    except Exception as erreur:
        print("=" * 70)
        print("[ERREUR DATABASE] Impossible de se connecter / creer les tables.")
        print(f"[ERREUR DATABASE] Type : {type(erreur).__name__}")
        print(f"[ERREUR DATABASE] Detail : {erreur}")
        print("=" * 70)
        raise  # on relance l'erreur pour que uvicorn plante au lieu de demarrer silencieusement en mode degrade

    with Session(engine) as session:
        peupler_donnees_initiales(session)
    (BASE_DIR.parent / "uploads").mkdir(exist_ok=True)


@app.get("/")
def accueil(request: Request, session: Session = Depends(get_session)):
    facultes = session.exec(select(Faculte)).all()
    documents_approuves = session.exec(
        select(Document).where(Document.statut == StatutDocument.APPROUVE)
    ).all()
    derniers_documents = sorted(
        documents_approuves, key=lambda d: d.date_upload, reverse=True
    )[:5]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "facultes": facultes,
            "nb_documents": len(documents_approuves),
            "derniers_documents": derniers_documents,
        },
    )