from pathlib import Path
from types import SimpleNamespace
import pytest
from jinja2 import Environment, FileSystemLoader
from app.models import PointagePresence, StatutPointage
from app.routers.suivi_academique_router import (
    calculer_moyenne_ponderee,
    construire_statistiques_globales,
    normaliser_statut_pointage,
    _csv_academique_sans_formule,
)

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


def test_rapport_global_agrege_notes_pointages_sans_exposer_les_etudiants():
    from app.models import StatutPointage

    cours = [
        SimpleNamespace(id=1, nom="Analyse", matiere="Mathématiques", niveau="L1", professeur_id=90, portee_academique="universitaire"),
        SimpleNamespace(id=2, nom="Sciences", matiere="Physique", niveau="Terminale", professeur_id=91, portee_academique="scolaire"),
    ]
    inscriptions = [
        SimpleNamespace(cours_id=1, utilisateur_id=10),
        SimpleNamespace(cours_id=1, utilisateur_id=11),
        SimpleNamespace(cours_id=2, utilisateur_id=10),
    ]
    devoirs = [
        SimpleNamespace(id=1, cours_id=1, bareme=20, coefficient=1, periode="S1"),
        SimpleNamespace(id=2, cours_id=1, bareme=40, coefficient=3, periode="S1"),
        SimpleNamespace(id=3, cours_id=2, bareme=20, coefficient=1, periode="T1"),
    ]
    rendus = [
        SimpleNamespace(devoir_id=1, utilisateur_id=10, note=15),
        SimpleNamespace(devoir_id=2, utilisateur_id=10, note=20),
        SimpleNamespace(devoir_id=1, utilisateur_id=11, note=16),
        SimpleNamespace(devoir_id=2, utilisateur_id=11, note=None),
        SimpleNamespace(devoir_id=3, utilisateur_id=10, note=18),
    ]
    seances = [
        SimpleNamespace(id=100, cours_id=1),
        SimpleNamespace(id=200, cours_id=2),
    ]
    pointages = [
        SimpleNamespace(seance_id=100, statut=StatutPointage.PRESENT),
        SimpleNamespace(seance_id=100, statut=StatutPointage.ABSENT),
        SimpleNamespace(seance_id=100, statut=StatutPointage.RETARD),
        SimpleNamespace(seance_id=100, statut=StatutPointage.EXCUSE),
        SimpleNamespace(seance_id=100, statut=StatutPointage.A_RENSEIGNER),
    ]
    professeurs = {
        90: SimpleNamespace(id=90, nom="Professeur A"),
        91: SimpleNamespace(id=91, nom="Professeur B"),
    }

    rapport = construire_statistiques_globales(
        cours, inscriptions, devoirs, rendus, seances, pointages, professeurs,
    )

    assert rapport["totaux"]["nb_cours"] == 2
    assert rapport["totaux"]["nb_etudiants"] == 2
    assert rapport["totaux"]["nb_inscriptions"] == 3
    assert rapport["totaux"]["nb_rendus"] == 5
    assert rapport["totaux"]["nb_corriges"] == 4
    assert rapport["totaux"]["nb_seances"] == 2
    assert rapport["totaux"]["presences"] == {
        "present": 1, "absent": 1, "retard": 1, "excuse": 1,
    }
    analyse = next(ligne for ligne in rapport["cours"] if ligne["cours"].id == 1)
    assert analyse["moyenne"] == 13.62
    assert analyse["nb_etudiants_notes"] == 2
    assert analyse["couverture_notes_pct"] == 100
    assert analyse["professeur"].nom == "Professeur A"
    assert all("utilisateur" not in ligne for ligne in rapport["cours"])


def test_rapport_global_vide_ne_divise_pas_par_zero():
    rapport = construire_statistiques_globales([], [], [], [], [], [])
    assert rapport["cours"] == []
    assert rapport["totaux"]["nb_cours"] == 0
    assert rapport["totaux"]["moyenne"] is None
    assert rapport["totaux"]["presences"] == {
        "present": 0, "absent": 0, "retard": 0, "excuse": 0,
    }


def test_templates_academiques_compilent_et_relient_les_notes_au_tuteur():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    for name in (
        "carnet_notes.html", "mes_notes.html", "registre_presences.html",
        "mes_presences.html", "rapport_academique.html", "admin_rapport_academique.html",
    ):
        assert env.get_template(name) is not None
    source = (ROOT / "app" / "templates" / "mes_notes.html").read_text(encoding="utf-8")
    assert 'action="/tuteur/demander"' in source
    assert "item.rendu.note / item.devoir.bareme * 20 < 10" in source


@pytest.mark.parametrize("valeur", ["=2+2", " +1+1", "@SUM(A1:A2)", "-cmd"])
def test_export_csv_academique_neutralise_les_formules(valeur):
    assert _csv_academique_sans_formule(valeur).startswith("'")
