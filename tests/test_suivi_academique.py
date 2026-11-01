from pathlib import Path
from types import SimpleNamespace
import pytest
from jinja2 import Environment, FileSystemLoader
from app.models import PointagePresence, StatutPointage
from app.routers.suivi_academique_router import calculer_moyenne_ponderee, normaliser_statut_pointage

ROOT = Path(__file__).resolve().parents[1]

def test_moyenne_ponderee_ramene_les_baremes_sur_vingt_et_applique_coefficients():
    devoirs = {1: SimpleNamespace(bareme=20, coefficient=1, periode="S1"), 2: SimpleNamespace(bareme=40, coefficient=3, periode="S1")}
    rendus = [SimpleNamespace(devoir_id=1, note=20), SimpleNamespace(devoir_id=2, note=20)]
    assert calculer_moyenne_ponderee(rendus, devoirs) == 12.5
    assert calculer_moyenne_ponderee(rendus, devoirs, "S1") == 12.5

def test_copies_non_corrigees_et_brouillons_ia_sont_exclus_des_moyennes():
    devoirs = {1: SimpleNamespace(bareme=20, coefficient=1, periode="S1"), 2: SimpleNamespace(bareme=20, coefficient=2, periode="S1")}
    rendus = [SimpleNamespace(devoir_id=1, note=15), SimpleNamespace(devoir_id=2, note=None)]
    assert calculer_moyenne_ponderee(rendus, devoirs) == 15.0

def test_moyennes_par_periode_ne_melangent_pas_les_semestres():
    devoirs = {1: SimpleNamespace(bareme=20, coefficient=1, periode="S1"), 2: SimpleNamespace(bareme=20, coefficient=1, periode="S2")}
    rendus = [SimpleNamespace(devoir_id=1, note=18), SimpleNamespace(devoir_id=2, note=8)]
    assert calculer_moyenne_ponderee(rendus, devoirs, "S1") == 18
    assert calculer_moyenne_ponderee(rendus, devoirs, "S2") == 8

@pytest.mark.parametrize("statut", ["present", "absent", "retard", "excuse", "a_renseigner"])
def test_statuts_pointage_valides(statut):
    assert normaliser_statut_pointage(statut) == StatutPointage(statut)

def test_statut_inconnu_refuse():
    with pytest.raises(ValueError):
        normaliser_statut_pointage("admin")

def test_modele_pointage_impose_une_cle_unique_seance_et_etudiant():
    assert any(getattr(c, "name", None) == "uq_pointagepresence_seance_utilisateur" for c in PointagePresence.__table_args__)

def test_templates_suivi_academique_se_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    for name in ("carnet_notes.html", "mes_notes.html", "registre_presences.html", "mes_presences.html", "rapport_academique.html"):
        assert env.get_template(name) is not None
