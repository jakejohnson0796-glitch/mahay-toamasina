from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "app" / "routers" / "dashboard_router.py"
TEMPLATE = ROOT / "app" / "templates" / "mon_parcours.html"
BASE = ROOT / "app" / "templates" / "base.html"
STYLE = ROOT / "app" / "static" / "mon-parcours.css"


def test_page_parcours_est_authentifiee_et_filtre_les_donnees_du_compte():
    router = ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/mon-parcours")' in router
    assert "utilisateur_courant(request, session)" in router
    assert 'RedirectResponse("/connexion", status_code=303)' in router
    assert "ProgressionNotion.utilisateur_id == utilisateur.id" in router
    assert "InscriptionCours.utilisateur_id == utilisateur.id" in router
    assert "learning_recap.construire_bilan" in router


def test_page_parcours_affiche_les_indicateurs_et_etats_vides():
    template = TEMPLATE.read_text(encoding="utf-8")
    for fragment in ("Quiz terminés", "Notions suivies", "Maîtrise confirmée",
                     "Mes cours suivis", "À renforcer", "Révisions programmées",
                     "Activités récentes", "bilan.mission.lien"):
        assert fragment in template
    assert "Aucun cours de classe" in template
    assert "Aucune activité enregistrée" in template


def test_page_parcours_est_accessible_et_adaptative():
    base = BASE.read_text(encoding="utf-8")
    style = STYLE.read_text(encoding="utf-8")
    assert 'href="/mon-parcours"' in base
    assert "version_asset('mon-parcours.css')" in base
    assert "@media(max-width:560px)" in style
    assert "@media(prefers-reduced-motion:reduce)" in style
