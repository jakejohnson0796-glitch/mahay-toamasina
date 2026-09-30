"""
Point d'entree de Gasy Mahay Toamasina.

Lancer avec :  uvicorn app.main:app --reload
(depuis la racine du projet, apres avoir installe requirements.txt)
"""
import asyncio
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Depends
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from .templating import templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select, func

from .config import parametres
from .database import executer_migrations, engine, get_session
from .models import Faculte, Universite, Mention, Filiere, CercleEtude, StatutCercle, Document, StatutDocument, TentativeQuiz
from .routers import auth_router, documents_router, sponsoring_router, cercles_router, abonnement_router, dashboard_router, quiz_router, admin_router, admin_referentiel_router, tuteur_router, classe_router, faq_router, feedback_router, academique_router, mode_emploi_router, notifications_router, revisions_router
from .security_headers import EnTetesSecuriteMiddleware
from .seed_data import peupler_donnees_initiales
from .seed_faq import peupler_faq_initiale
from .admin_init import assurer_compte_admin
from .cercles_referentiel import assurer_cercles_referentiel
from scripts.dedupliquer_cercles_nationaux import deduplicquer as deduplicquer_cercles_nationaux
from scripts.import_academic_data import importer as importer_referentiel_academique
from .auth import utilisateur_courant
from . import ai_worker

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
    session_cookie="__Host-session" if parametres.environnement == "production" else "session",
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
app.include_router(mode_emploi_router.router)
app.include_router(notifications_router.router)
app.include_router(revisions_router.router)


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

    # Les migrations restent synchrones : le schema doit etre pret avant que
    # l'application serve des donnees. Le remplissage/maintenance peut en
    # revanche etre effectue apres le boot, dans un thread, afin que Render
    # puisse atteindre le serveur et valider son health check sans attendre
    # l'import du referentiel, le seed et la maintenance des cercles.
    print("[DEBUG DATABASE] Migrations OK — lancement de l'initialisation des donnees en arriere-plan.")
    initialisation = asyncio.create_task(asyncio.to_thread(_initialiser_donnees_apres_demarrage))
    app.state.initialisation_donnees = initialisation

    # Render Free ne fournit pas de Background Worker gratuit. Lorsque Redis
    # est configure, la boucle IA tourne donc dans un thread interne au Web
    # service. Les appels IA restent hors de la boucle asyncio HTTP, tandis
    # que Redis absorbe les rafales et PostgreSQL reste le filet de securite.
    if parametres.redis_url:
        arret_worker = threading.Event()
        worker_ia = threading.Thread(
            target=ai_worker.boucle_worker,
            args=(arret_worker,),
            name="ai-worker-inline",
            daemon=True,
        )
        worker_ia.start()
        app.state.ai_worker_stop = arret_worker
        app.state.ai_worker_thread = worker_ia
        print(
            "[DEBUG AI QUEUE] Worker IA integre au Web demarre — "
            f"redis=True cle={ai_worker.ai_queue.CLE_FILE_REDIS}."
        )
    else:
        app.state.ai_worker_stop = None
        app.state.ai_worker_thread = None
        print(
            "[DEBUG AI QUEUE] Redis absent — worker IA integre desactive "
            "(fallback SQL disponible uniquement si lance manuellement)."
        )

    (BASE_DIR.parent / "uploads").mkdir(exist_ok=True)
    print("[DEBUG DATABASE] Demarrage HTTP pret.")

@app.on_event("shutdown")
async def arreter_worker_ia() -> None:
    """Arrete proprement le worker IA embarque avant l'extinction du Web."""
    arret_worker = getattr(app.state, "ai_worker_stop", None)
    if arret_worker is not None:
        arret_worker.set()

    thread = getattr(app.state, "ai_worker_thread", None)
    if thread is not None and thread.is_alive():
        await asyncio.to_thread(thread.join, 20)
        if thread.is_alive():
            print("[DEBUG AI QUEUE] Worker IA encore actif apres 20s; arret du Web.")
        else:
            print("[DEBUG AI QUEUE] Worker IA arrete proprement.")


def _initialiser_donnees_apres_demarrage() -> None:
    print("[DEBUG DATABASE] Verification des donnees initiales...")
    with Session(engine) as session:
        # Le referentiel national (dont les Domaines) est fourni dans le
        # classeur versionne du projet. La migration b8f4d1c6a2e7 cree la
        # structure SQL mais, historiquement, l'importeur etait seulement
        # documente comme une commande manuelle. Sur Render/Supabase aucun
        # shell post-deploiement n'etait disponible : la table Domaine
        # restait donc vide et le filtre des Cercles ne pouvait afficher
        # que "Tous les domaines". On rejoue ici l'importeur, uniquement
        # sur Postgres, car il est idempotent et n'ecrase jamais un
        # rattachement Domaine existant. SQLite/tests continuent de
        # fonctionner comme avant.
        if not parametres.database_url.startswith("sqlite"):
            # Source prioritaire : le referentiel Toamasina exact fourni avec le projet.
            # Le fichier national historique reste un fallback de compatibilite.
            candidats_referentiel = [
                BASE_DIR.parent / "mahay_toamasina_referentiel_source.json",
                BASE_DIR.parent / "mahay_universites_mentions_filieres_recensement.xlsx",
            ]
            chemin_referentiel = next(
                (chemin for chemin in candidats_referentiel if chemin.exists()),
                None,
            )
            if chemin_referentiel is not None:
                try:
                    rapport_referentiel = importer_referentiel_academique(str(chemin_referentiel))
                    print(
                        "[DEBUG ACADEMIQUE] Referentiel synchronise — "
                        f"source={chemin_referentiel.name}, "
                        f"{len(rapport_referentiel.domaines_crees)} domaine(s), "
                        f"{len(rapport_referentiel.mentions_domaine_rattache)} rattachement(s) "
                        f"Mention→Domaine, "
                        f"{len(rapport_referentiel.mentions_domaine_ambigu)} mention(s) ambigue(s), "
                        f"{len(rapport_referentiel.filieres_creees)} filiere(s) creee(s), "
                        f"{rapport_referentiel.programmes_crees} offre(s) creee(s)."
                    )
                except Exception as erreur_referentiel:
                    print(
                        "[ERREUR ACADEMIQUE] Synchronisation du referentiel "
                        f"impossible : {type(erreur_referentiel).__name__}: {erreur_referentiel}"
                    )
            else:
                print(
                    "[DEBUG ACADEMIQUE] Source du referentiel absente — "
                    "synchronisation ignoree."
                )
        peupler_donnees_initiales(session)
        peupler_faq_initiale(session)
        assurer_compte_admin(session)
        # Apres assurer_compte_admin : un cercle genere automatiquement a
        # besoin d'un createur_id valide (voir cercles_referentiel.py).
        nb_cercles_crees = assurer_cercles_referentiel(session)
        if nb_cercles_crees:
            print(f"[DEBUG DATABASE] {nb_cercles_crees} cercle(s) national/nationaux provisionne(s) automatiquement.")
    
        # Fusionne les cercles nationaux "doublons" restants (un par
        # universite au lieu d'un seul, bug historique corrige dans
        # cercles_referentiel.py mais dont les doublons d'AVANT la
        # correction ne se nettoient pas tout seuls — voir
        # scripts/dedupliquer_cercles_nationaux.py). Execute ici, a
        # chaque demarrage plutot qu'a la main via `python -m
        # scripts...`, parce que le plan gratuit de Render ne donne pas
        # d'acces shell pour lancer un script a la demande. Idempotent
        # (un groupe deja fusionne n'est plus retouche), donc sans
        # risque de le rejouer a chaque redemarrage.
        rapport_dedup = deduplicquer_cercles_nationaux(session)
        if rapport_dedup.cercles_archives:
            print(
                f"[DEBUG DATABASE] {len(rapport_dedup.cercles_archives)} cercle(s) national/nationaux "
                f"doublon(s) fusionne(s) et archive(s) ({rapport_dedup.membres_reassignes} membre(s) reassigne(s))."
            )
    print("[DEBUG DATABASE] Donnees initiales OK.")
    (BASE_DIR.parent / "uploads").mkdir(exist_ok=True)
    print("[DEBUG DATABASE] Demarrage termine.")



@app.get("/health")
def health() -> dict:
    """Endpoint de liveness avec etat statique du worker IA inline."""
    thread = getattr(app.state, "ai_worker_thread", None)
    return {
        "status": "ok",
        "ai_worker_configured": bool(parametres.redis_url),
        "ai_worker_alive": bool(thread and thread.is_alive()),
    }


@app.get("/robots.txt", include_in_schema=False)
def robots(request: Request) -> Response:
    """Expose une politique simple d'exploration : pages publiques indexables,
    zones privees et actions internes exclues des moteurs."""
    return PlainTextResponse(
        "\n".join([
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /securite",
            "Disallow: /dashboard",
            "Disallow: /notifications",
            "Disallow: /mes-revisions",
            "Disallow: /abonnement",
            "Disallow: /mot-de-passe-oublie",
            "Disallow: /connexion/2fa",
            "Disallow: /cercles/*/membres",
            "Disallow: /cercles/*/demandes",
            f"Sitemap: {request.base_url}sitemap.xml",
        ]) + "\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request) -> Response:
    """Sitemap minimal des pages publiques stables."""
    base_url = str(request.base_url).rstrip("/")
    chemins = [
        "/",
        "/a-propos",
        "/universites",
        "/documents",
        "/cercles",
        "/faq",
        "/mode-emploi",
        "/contact",
        "/inscription",
        "/connexion",
    ]
    lignes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for chemin in chemins:
        lignes.extend([f"  <url><loc>{base_url}{chemin}</loc></url>"])
    lignes.append("</urlset>")
    return Response(
        content="\n".join(lignes),
        media_type="application/xml",
    )


@app.get("/")
def accueil(request: Request, session: Session = Depends(get_session)):
    facultes = session.exec(select(Faculte)).all()
    derniers_documents = session.exec(
        select(Document).where(Document.statut == StatutDocument.APPROUVE)
        .order_by(Document.date_upload.desc()).limit(5)
    ).all()

    # Section 9 du brief "Le Phare" : hero a 4 stats (documents,
    # universites, cercles actifs, quiz completes) au lieu de 2.
    nb_universites = session.exec(
        select(func.count()).select_from(Universite).where(Universite.est_active == True)  # noqa: E712
    ).one()
    nb_cercles_actifs = session.exec(
        select(func.count()).select_from(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)
    ).one()
    nb_quiz_completes = session.exec(
        select(func.count()).select_from(TentativeQuiz).where(TentativeQuiz.date_soumission.is_not(None))
    ).one()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "facultes": facultes,
            "nb_documents": session.exec(select(func.count()).select_from(Document).where(Document.statut == StatutDocument.APPROUVE)).one(),
            "derniers_documents": derniers_documents,
            "nb_universites": nb_universites,
            "nb_cercles_actifs": nb_cercles_actifs,
            "nb_quiz_completes": nb_quiz_completes,
            "utilisateur": utilisateur_courant(request, session),
        },
    )


@app.get("/a-propos")
def a_propos(request: Request, session: Session = Depends(get_session)):
    nb_universites = session.exec(select(func.count()).select_from(Universite).where(Universite.est_active == True)).one()
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
