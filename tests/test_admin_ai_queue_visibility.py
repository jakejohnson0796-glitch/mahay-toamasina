from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from app.models import RoleUtilisateur, StatutTacheIA
from app.routers import admin_router


ROOT = Path(__file__).resolve().parents[1]


class _ResultatFaux:
    def __init__(self, lignes=None, valeur=0):
        self.lignes = lignes or []
        self.valeur = valeur

    def one(self):
        return self.valeur

    def all(self):
        return self.lignes


class _SessionSupervisionFausse:
    def __init__(self, tache):
        self.tache = tache
        self.requetes = []

    def exec(self, requete):
        sql = str(requete)
        self.requetes.append(sql)
        sql_minuscule = sql.lower()
        if "count(" in sql_minuscule:
            return _ResultatFaux(valeur=0)
        if "performancemodeleia" in sql_minuscule:
            return _ResultatFaux()
        if "left outer join" in sql_minuscule and "tentativequiz" in sql_minuscule:
            return _ResultatFaux(lignes=[(self.tache, None)])
        raise AssertionError(f"Requête de supervision inattendue : {sql}")


def test_supervision_admin_ia_inclut_les_fiches_sans_tentative_quiz(monkeypatch):
    maintenant = datetime.utcnow()
    erreur_brute = (
        "RuntimeError: provider rate limit 429; api_key=gsk_SECRET_A_NE_PAS_AFFICHER "
        "et contenu prive d'une reponse utilisateur"
    )
    tache = SimpleNamespace(
        id=714,
        type_tache="fiche_revision_document",
        tentative_quiz_id=None,
        session_tuteur_id=None,
        document_id=None,
        fiche_revision_cours_id=None,
        fiche_revision_document_id=91,
        statut=StatutTacheIA.EN_ATTENTE,
        strategie_verification="standard",
        score_risque=2,
        nombre_essais=3,
        disponible_le=maintenant - timedelta(minutes=3),
        prise_en_charge_le=None,
        terminee_le=None,
        derniere_erreur=erreur_brute,
        date_creation=maintenant - timedelta(minutes=25),
    )
    session = _SessionSupervisionFausse(tache)
    admin = SimpleNamespace(id=1, role=RoleUtilisateur.ADMIN)
    rendu = {}

    monkeypatch.setattr(admin_router, "_admin_requis", lambda _request, _session: admin)
    monkeypatch.setattr(
        admin_router.ai_metrics,
        "resume_global",
        lambda: SimpleNamespace(appels=0, problemes=0, arbitrages=0, duree_moyenne=0),
    )

    def template_response(_request, nom_template, contexte):
        rendu["template"] = nom_template
        rendu["contexte"] = contexte
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(admin_router.templates, "TemplateResponse", template_response)

    reponse = admin_router.page_admin_ia(SimpleNamespace(), session)

    assert reponse.status_code == 200
    assert rendu["template"] == "admin_ia.html"
    assert any("LEFT OUTER JOIN" in requete.upper() for requete in session.requetes)
    assert len(rendu["contexte"]["taches_recentes"]) == 1
    fiche = rendu["contexte"]["taches_recentes"][0]
    assert fiche["id"] == 714
    assert fiche["type_label"] == "Fiche de révision de document"
    assert fiche["cible"] == "Fiche de révision de document #91"
    assert fiche["statut_label"] == "En attente"
    assert fiche["age_label"] == "25 min"
    assert fiche["alerte"] is True
    assert "Limite de débit ou quota IA atteint" in fiche["erreur_resume"]
    assert "gsk_SECRET_A_NE_PAS_AFFICHER" not in repr(rendu["contexte"])
    assert "contenu prive d'une reponse utilisateur" not in repr(rendu["contexte"])
    assert erreur_brute not in repr(rendu["contexte"])


def test_resume_erreur_tache_ia_ne_restitue_jamais_le_message_brut():
    from app.routers.admin_router import _resume_erreur_tache_ia

    brute = "ValueError: JSON invalide avec token=secret-et-contenu-cours"
    resume = _resume_erreur_tache_ia(brute)

    assert resume
    assert "secret-et-contenu-cours" not in resume
    assert "JSON invalide" in resume


def test_page_supervision_taches_compile_et_presente_age_et_diagnostic_sans_brut():
    dossier_templates = ROOT / "app" / "templates"
    environnement = Environment(loader=FileSystemLoader(str(dossier_templates)))
    page = environnement.get_template("admin_ia.html")
    source = (dossier_templates / "admin_ia.html").read_text(encoding="utf-8")

    assert page.name == "admin_ia.html"
    assert "LEFT OUTER JOIN" not in source
    assert "{{ tache.type_label }}" in source
    assert "{{ tache.age_label }}" in source
    assert "{{ tache.erreur_resume }}" in source
    assert "{{ tache.derniere_erreur }}" not in source
    assert "30 dernières tâches" in source
    assert "fiches de révision" in source.lower()
