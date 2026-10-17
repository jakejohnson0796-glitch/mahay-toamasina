from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from app.models import ProgressionNotion, RoleUtilisateur
from app.routers.classe_router import _peut_gerer_cours
from app.routers.classe_router import (
    _cle_academique,
    _cle_niveau,
    construire_plan_reprise,
    construire_radar_pedagogique,
)


ROOT = Path(__file__).resolve().parents[1]


def _progression(utilisateur_id: int, notion: str, score: int) -> ProgressionNotion:
    questions = 10
    return ProgressionNotion(
        utilisateur_id=utilisateur_id,
        matiere="Mathématiques",
        notion=notion,
        niveau="L1",
        nb_questions=questions,
        nb_reussites=round(questions * score / 100),
        nb_erreurs=questions - round(questions * score / 100),
        score_maitrise=score,
        confiance_maitrise=score,
        serie_reussites=0,
        nb_revisions=1,
        niveau_max_reussi="Facile",
        preuves_apprentissage_json="{}",
    )


def test_normalisation_academique_ignore_accents_espaces_et_casse():
    assert _cle_academique("  Mathématiques  ") == _cle_academique("MATHEMATIQUES")
    assert _cle_academique("Algèbre linéaire") == "algebre lineaire"


def test_radar_masque_une_notion_avec_moins_de_trois_etudiants():
    lignes = [
        _progression(11, "Dérivées", 25),
        _progression(12, "Dérivées", 40),
    ]

    radar = construire_radar_pedagogique(lignes, effectif_inscrit=4)

    assert radar["effectif_inscrit"] == 4
    assert radar["effectif_observe"] == 2
    assert radar["couverture_pct"] == 50
    assert radar["nb_notions_mesurees"] == 1
    assert radar["notions"] == []
    assert radar["seuil_confidentialite"] == 3


def test_radar_agrege_les_scores_et_fournit_une_action_collective():
    lignes = [
        _progression(11, "Dérivées", 30),
        _progression(12, "Dérivées", 50),
        _progression(13, "Dérivées", 75),
        _progression(11, "Limites", 90),
        _progression(12, "Limites", 88),
        _progression(13, "Limites", 92),
    ]

    radar = construire_radar_pedagogique(lignes, effectif_inscrit=5)

    assert radar["effectif_observe"] == 3
    assert radar["couverture_pct"] == 60
    derivees = next(item for item in radar["notions"] if item["notion"] == "Dérivées")
    assert derivees["effectif_observe"] == 3
    assert derivees["score_moyen"] == 52
    assert derivees["nb_fragiles"] == 2
    assert derivees["priorite"] == "À reprendre"
    assert "micro-leçon" in derivees["action"]


def test_radar_ne_compte_pas_deux_fois_le_meme_etudiant_pour_une_notion():
    lignes = [
        _progression(11, "Dérivées", 30),
        _progression(11, "Dérivées", 60),
        _progression(12, "Dérivées", 50),
        _progression(13, "Dérivées", 75),
    ]

    radar = construire_radar_pedagogique(lignes, effectif_inscrit=4)
    derivees = radar["notions"][0]

    assert derivees["effectif_observe"] == 3
    assert derivees["score_moyen"] == 52  # score le plus prudent, sans compter l’étudiant deux fois


def test_plan_de_reprise_est_actionnable_et_signale_ses_limites():
    cours = SimpleNamespace(nom="Algèbre 1", matiere="Mathématiques", niveau="L1")
    radar = construire_radar_pedagogique([
        _progression(11, "Dérivées", 30),
        _progression(12, "Dérivées", 50),
        _progression(13, "Dérivées", 75),
    ], effectif_inscrit=3)

    plan = construire_plan_reprise(cours, radar)

    assert "Algèbre 1" in plan
    assert "Dérivées" in plan
    assert "questions nouvelles" in plan
    assert "pas un jugement sur un étudiant" in plan


def test_template_radar_compile_et_contient_les_gardes_de_confidentialite():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    template = env.get_template("radar_pedagogique_classe.html")
    assert template is not None

    source = (ROOT / "app" / "templates" / "radar_pedagogique_classe.html").read_text(encoding="utf-8")
    assert "radar.seuil_confidentialite" in source
    assert "sans noms" in source.lower()
    assert 'id="copier-plan"' in source
    assert 'name="utilisateur.nom"' not in source



def test_radar_professeur_limite_au_proprietaire_du_cours_ou_admin():
    cours = SimpleNamespace(professeur_id=41)
    proprietaire = SimpleNamespace(id=41, role=RoleUtilisateur.PROFESSEUR)
    autre_professeur = SimpleNamespace(id=42, role=RoleUtilisateur.PROFESSEUR)
    etudiant = SimpleNamespace(id=43, role=RoleUtilisateur.ETUDIANT)
    administrateur = SimpleNamespace(id=99, role=RoleUtilisateur.ADMIN)

    assert _peut_gerer_cours(cours, proprietaire)
    assert not _peut_gerer_cours(cours, autre_professeur)
    assert not _peut_gerer_cours(cours, etudiant)
    assert _peut_gerer_cours(cours, administrateur)
    assert not _peut_gerer_cours(cours, None)



def test_niveaux_academiques_sont_normalises_sans_confondre_l1_et_l2():
    assert _cle_niveau("Licence 1") == _cle_niveau("L1")
    assert _cle_niveau("Première année") == _cle_niveau("L1")
    assert _cle_niveau("Master 2") == _cle_niveau("M2")
    assert _cle_niveau("L1") != _cle_niveau("L2")
