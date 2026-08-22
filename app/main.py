"""
Point d'entree de Gasy Mahay Toamasina.

Lancer avec :  uvicorn app.main:app --reload
(depuis la racine du projet, apres avoir installe requirements.txt)
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from .templating import templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select

from .config import parametres
from .database import executer_migrations, engine, get_session
from .models import Faculte, Universite, Mention, Filiere, CercleEtude, StatutCercle, Document, StatutDocument, TentativeQuiz
from .routers import auth_router, documents_router, sponsoring_router, cercles_router, abonnement_router, dashboard_router, quiz_router, admin_router, admin_referentiel_router, tuteur_router, classe_router, faq_router, feedback_router, academique_router
from .security_headers import EnTetesSecuriteMiddleware
from .seed_data import peupler_donnees_initiales
from .seed_faq import peupler_faq_initiale
from .admin_init import assurer_compte_admin
from .cercles_referentiel import assurer_cercles_referentiel
from .auth import utilisateur_courant

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Gasy Mahay Toamasina")

# --- Garde-fou : refuse de demarrer en production avec la cle de demo ---
# Un secret par defaut connu de tous (present dans .env.example, donc
# visible sur GitHub) permettrait a n'importe qui de forger un cookie de
# session valide pour n'importe quel compte, y compris admin, s'il etait
# oublie tel quel sur un vrai deploiement. On echoue bruyamment plutot
# que de demarrer silencieusement dans un etat dangereux.
if parametres.environnement == "production" and parametres.session_secret_key == "a-changer-en-production":
    raise RuntimeError(
        "SESSION_SECRET_KEY est encore la valeur de demo alors que "
        "ENVIRONNEMENT=production. Genere une vraie valeur (python -c "
        "\"import secrets; print(secrets.token_hex(32))\") et definis-la "
        "dans les variables d'environnement de l'hebergeur avant de redeployer."
    )

# Cle de session : lue depuis SESSION_SECRET_KEY (.env) si presente, sinon
# retombe sur la valeur de demo. A REMPLACER avant toute mise en ligne
# reelle (voir .env.example).
app.add_middleware(
    SessionMiddleware,
    secret_key=parametres.session_secret_key,
    # https_only : le navigateur refuse d'envoyer le cookie en clair (HTTP).
    # Desactive seulement en developpement local (ou HTTPS n'est pas
    # configure) ; errone en production sinon toute la protection tombe.
    https_only=parametres.environnement == "production",
    same_site="lax",
    # Session expiree apres 14 jours d'inactivite : limite la fenetre de
    # danger si un cookie est vole (poste partage, appareil perdu...).
    max_age=14 * 24 * 60 * 60,
)
app.add_middleware(EnTetesSecuriteMiddleware, https_actif=parametres.environnement == "production")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(documents_router.router)
app.include_router(sponsoring_router.router)
app.include_router(cercles_router.router)
app.include_router(abonnement_router.router)
app.include_router(dashboard_router.router)
app.include_router(quiz_router.router)
app.include_router(admin_router.router)
app.include_router(admin_referentiel_router.router)
app.include_router(tuteur_router.router)
app.include_router(classe_router.router)
app.include_router(faq_router.router)
app.include_router(feedback_router.router)
app.include_router(academique_router.router)


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
async def au_demarrage() -> None:
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

    print("[DEBUG DATABASE] Verification des donnees initiales...")
    with Session(engine) as session:
        peupler_donnees_initiales(session)
        peupler_faq_initiale(session)
        assurer_compte_admin(session)
        # Apres assurer_compte_admin : un cercle genere automatiquement a
        # besoin d'un createur_id valide (voir cercles_referentiel.py).
        nb_cercles_crees = assurer_cercles_referentiel(session)
        if nb_cercles_crees:
            print(f"[DEBUG DATABASE] {nb_cercles_crees} cercle(s) national/nationaux provisionne(s) automatiquement.")
    print("[DEBUG DATABASE] Donnees initiales OK.")
    (BASE_DIR.parent / "uploads").mkdir(exist_ok=True)
    print("[DEBUG DATABASE] Demarrage termine.")


@app.get("/")
def accueil(request: Request, session: Session = Depends(get_session)):
    facultes = session.exec(select(Faculte)).all()
    documents_approuves = session.exec(
        select(Document).where(Document.statut == StatutDocument.APPROUVE)
    ).all()
    derniers_documents = sorted(
        documents_approuves, key=lambda d: d.date_upload, reverse=True
    )[:5]

    # Section 9 du brief "Le Phare" : hero a 4 stats (documents,
    # universites, cercles actifs, quiz completes) au lieu de 2.
    nb_universites = len(session.exec(select(Universite).where(Universite.est_active == True)).all())  # noqa: E712
    nb_cercles_actifs = len(session.exec(select(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)).all())
    nb_quiz_completes = len(session.exec(select(TentativeQuiz).where(TentativeQuiz.date_soumission.is_not(None))).all())

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "facultes": facultes,
            "nb_documents": len(documents_approuves),
            "derniers_documents": derniers_documents,
            "nb_universites": nb_universites,
            "nb_cercles_actifs": nb_cercles_actifs,
            "nb_quiz_completes": nb_quiz_completes,
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@app.get("/a-propos")
def a_propos(request: Request, session: Session = Depends(get_session)):
    nb_universites = len(session.exec(select(Universite).where(Universite.est_active == True)).all())  # noqa: E712
    return templates.TemplateResponse(
        request, "a_propos.html",
        {"nb_universites": nb_universites, "utilisateur": utilisateur_courant(request, session)},
    )


@app.get("/universites")
def universites(request: Request, session: Session = Depends(get_session)):
    # Donnees reelles deja en base — aucune universite, faculte ou
    # filiere n'est inventee pour cette page. Reflete le referentiel
    # academique national (Universite -> Faculte -> Filiere -> Mention),
    # pas seulement Toamasina.
    toutes_universites = session.exec(select(Universite).where(Universite.est_active == True)).all()  # noqa: E712
    toutes_facultes = session.exec(select(Faculte)).all()
    toutes_filieres = session.exec(select(Filiere)).all()
    mentions_par_id = {m.id: m for m in session.exec(select(Mention)).all()}

    facultes_par_universite: dict[int, list] = {}
    for faculte in toutes_facultes:
        facultes_par_universite.setdefault(faculte.universite_id, []).append(faculte)

    filieres_par_faculte: dict[int, list] = {}
    for filiere in toutes_filieres:
        filieres_par_faculte.setdefault(filiere.faculte_id, []).append(filiere)

    universites_info = []
    for u in toutes_universites:
        facultes = facultes_par_universite.get(u.id, [])
        nb_filieres = sum(len(filieres_par_faculte.get(f.id, [])) for f in facultes)
        universites_info.append({
            "universite": u,
            "facultes": [
                {"faculte": f, "filieres": filieres_par_faculte.get(f.id, [])}
                for f in facultes
            ],
            "nb_filieres": nb_filieres,
        })

    return templates.TemplateResponse(
        request,
        "universites.html",
        {
            "universites_info": universites_info,
            "mentions_par_id": mentions_par_id,
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@app.get("/contact")
def contact(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "contact.html", {"utilisateur": utilisateur_courant(request, session)})
