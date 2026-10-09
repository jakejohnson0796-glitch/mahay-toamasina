from pathlib import Path
from types import SimpleNamespace
import urllib.error

from app import admin_diagnostics
from app import routers
from app.models import RoleUtilisateur


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_revision_alembic_comparee_aux_tetes_attendues():
    ok = admin_diagnostics.comparer_revisions_migrations({"rev-a"}, {"rev-a"})
    obsolete = admin_diagnostics.comparer_revisions_migrations({"rev-a"}, {"rev-b"})

    assert ok["statut"] == "ok"
    assert obsolete["statut"] == "error"
    assert "rev-a" in ok["detail"]
    assert "rev-b" in obsolete["detail"]


def test_controle_supabase_verifie_le_bucket_sans_afficher_la_cle(monkeypatch):
    cle = "service-secret-ne-doit-jamais-apparaitre"
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_url", "https://storage.example.test")
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_service_key", cle)
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_bucket", "documents")
    captures = {}

    def urlopen(requete, timeout):
        captures["url"] = requete.full_url
        captures["headers"] = dict(requete.header_items())
        captures["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(admin_diagnostics.urllib.request, "urlopen", urlopen)
    resultat = admin_diagnostics.diagnostic_stockage_supabase()

    assert resultat["statut"] == "ok"
    assert captures["url"] == "https://storage.example.test/storage/v1/bucket/documents"
    assert captures["timeout"] == 2.5
    assert "authorization" in {nom.lower() for nom in captures["headers"]}
    assert cle not in repr(resultat)
    assert cle not in captures["url"]


def test_controle_supabase_masque_les_erreurs_et_ne_fuit_pas_la_cle(monkeypatch):
    cle = "secret-de-test-ne-pas-exposer"
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_url", "https://storage.example.test")
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_service_key", cle)
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_bucket", "documents")

    def refus(requete, timeout):
        raise urllib.error.HTTPError(requete.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(admin_diagnostics.urllib.request, "urlopen", refus)
    resultat = admin_diagnostics.diagnostic_stockage_supabase()

    assert resultat["statut"] == "error"
    assert "refusé" in resultat["detail"].lower()
    assert cle not in repr(resultat)
    assert "Forbidden" not in repr(resultat)


def test_stockage_non_configure_signale_un_avertissement(monkeypatch):
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_url", "")
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_service_key", "")
    monkeypatch.setattr(admin_diagnostics.parametres, "supabase_bucket", "documents")

    resultat = admin_diagnostics.diagnostic_stockage_supabase()

    assert resultat["statut"] == "warning"
    assert resultat["libelle"] == "Configuration incomplète"


def test_worker_ia_distingue_absence_redis_et_thread_arrete(monkeypatch):
    monkeypatch.setattr(admin_diagnostics.parametres, "redis_url", "")
    sans_redis = admin_diagnostics.diagnostic_worker_ia(SimpleNamespace())
    assert sans_redis["statut"] == "warning"

    monkeypatch.setattr(admin_diagnostics.parametres, "redis_url", "redis://redis.example.test")
    arrete = admin_diagnostics.diagnostic_worker_ia(SimpleNamespace(ai_worker_thread=None))
    actif = admin_diagnostics.diagnostic_worker_ia(
        SimpleNamespace(ai_worker_thread=SimpleNamespace(is_alive=lambda: True))
    )
    assert arrete["statut"] == "error"
    assert actif["statut"] == "ok"


def test_route_diagnostics_refuse_les_non_administrateurs(monkeypatch):
    from app.routers import admin_router

    monkeypatch.setattr(admin_router, "_admin_requis", lambda _request, _session: None)
    reponse = admin_router.page_diagnostics_admin(SimpleNamespace(), SimpleNamespace())

    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_diagnostics_est_accessible_depuis_le_tableau_admin():
    tableau = (ROOT / "app" / "templates" / "admin_index.html").read_text(encoding="utf-8")
    page = (ROOT / "app" / "templates" / "admin_diagnostics.html").read_text(encoding="utf-8")

    assert tableau.count('href="/admin/diagnostics"') >= 2
    assert callable(admin_diagnostics.diagnostic_base_de_donnees)
    assert "Commit de release" in page
    assert "Les clés, les mots de passe" in page
