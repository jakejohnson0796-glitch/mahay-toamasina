import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import (
    ContributionLecon,
    LeconReferentielle,
    RoleUtilisateur,
    StatutLeconReferentielle,
    TacheIA,
)
from app import harmonisation_ia
from app.routers import harmonisation_router


def test_espace_national_refuse_un_eleve(monkeypatch):
    eleve = SimpleNamespace(
        id=7,
        role=RoleUtilisateur.ETUDIANT,
        statut_verification_enseignant="non_concerne",
    )
    monkeypatch.setattr(
        harmonisation_router,
        "utilisateur_courant",
        lambda request, session: eleve,
    )
    response = harmonisation_router.espace_national_lecons_enseignant(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_espace_national_refuse_un_professeur_non_verifie(monkeypatch):
    professeur = SimpleNamespace(
        id=8,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="en_attente",
    )
    monkeypatch.setattr(
        harmonisation_router,
        "utilisateur_courant",
        lambda request, session: professeur,
    )
    response = harmonisation_router.espace_national_lecons_enseignant(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_admin_national_refuse_un_professeur(monkeypatch):
    professeur = SimpleNamespace(
        id=8,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="approuve",
    )
    monkeypatch.setattr(
        harmonisation_router,
        "utilisateur_courant",
        lambda request, session: professeur,
    )
    response = harmonisation_router.espace_national_lecons_admin(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_publication_refusee_sans_deux_enseignants_distincts():
    lecon = SimpleNamespace(
        id=3,
        statut_validation=StatutLeconReferentielle.VERIFIEE.value,
        version_publiee=0,
        contenu_publie="",
        statut_publication="non_publie",
        date_publication=None,
        publie_par_id=None,
    )
    analyse = SimpleNamespace(
        id=12,
        lecon_id=3,
        statut="terminee",
        contributions_ids_json="[5, 6]",
    )
    contributions = [
        SimpleNamespace(id=5, lecon_id=3, auteur_id=21, statut="retenue"),
        SimpleNamespace(id=6, lecon_id=3, auteur_id=21, statut="retenue"),
    ]

    version = harmonisation_router.publier_version_lecon_harmonisee(
        lecon,
        analyse,
        contributions,
        SimpleNamespace(id=99),
        "Un cours final suffisamment long pour satisfaire le minimum de longueur. " * 3,
        "Validation pédagogique motivée et vérification de la source officielle.",
    )

    assert version is None
    assert lecon.version_publiee == 0
    assert lecon.contenu_publie == ""


def test_publication_cree_une_version_apres_deux_contributions_retenues():
    maintenant = datetime(2026, 11, 22, 10, 0, 0)
    lecon = SimpleNamespace(
        id=3,
        statut_validation=StatutLeconReferentielle.VERIFIEE.value,
        version_publiee=2,
        contenu_publie="Ancienne version",
        statut_publication="publie",
        date_publication=None,
        publie_par_id=None,
    )
    analyse = SimpleNamespace(
        id=12,
        lecon_id=3,
        statut="terminee",
        contributions_ids_json="[5, 6, 7]",
    )
    contributions = [
        SimpleNamespace(id=5, lecon_id=3, auteur_id=21, statut="retenue"),
        SimpleNamespace(id=6, lecon_id=3, auteur_id=22, statut="retenue"),
        SimpleNamespace(id=7, lecon_id=3, auteur_id=23, statut="refusee"),
    ]
    contenu = "Cours final relu par l'administrateur. " * 8
    admin = SimpleNamespace(id=99)

    version = harmonisation_router.publier_version_lecon_harmonisee(
        lecon,
        analyse,
        contributions,
        admin,
        contenu,
        "Validation après revue des divergences et des références fournies.",
        maintenant,
    )

    assert version is not None
    assert version.numero_version == 3
    assert version.contenu == contenu.strip()
    assert json.loads(version.contributions_ids_json) == [5, 6]
    assert version.publie_par_id == 99
    assert lecon.version_publiee == 3
    assert lecon.statut_publication == "publie"
    assert lecon.date_publication == maintenant


def test_publier_refuse_une_analyse_non_terminee():
    lecon = SimpleNamespace(
        id=3,
        statut_validation="verifiee",
        version_publiee=0,
        contenu_publie="",
        statut_publication="non_publie",
        date_publication=None,
        publie_par_id=None,
    )
    analyse = SimpleNamespace(
        id=12,
        lecon_id=3,
        statut="en_cours",
        contributions_ids_json="[5, 6]",
    )
    contributions = [
        SimpleNamespace(id=5, lecon_id=3, auteur_id=21, statut="retenue"),
        SimpleNamespace(id=6, lecon_id=3, auteur_id=22, statut="retenue"),
    ]
    version = harmonisation_router.publier_version_lecon_harmonisee(
        lecon,
        analyse,
        contributions,
        SimpleNamespace(id=99),
        "Cours final relu et complet. " * 5,
        "Décision administrative motivée après contrôle.",
    )
    assert version is None
    assert lecon.version_publiee == 0


def test_analyse_ia_refuse_les_identifiants_de_contribution_inconnus():
    donnees = {
        "constats_convergents": [
            {"constat": "Les deux sources sont équivalentes.", "contribution_ids": [5, 999]}
        ],
        "formulations_equivalentes": [],
        "divergences_reelles": [],
        "notions_manquantes": [],
        "hors_programme_potentiels": [],
        "points_non_verifiables": [],
        "limites": [],
        "synthese_proposee": "Une synthèse pédagogique suffisamment longue pour le test. " * 4,
        "avertissement": "",
    }

    try:
        harmonisation_ia._valider_resultat(donnees, {5, 6})
    except ValueError as erreur:
        assert "pas été fournie" in str(erreur)
    else:
        raise AssertionError("Une référence de contribution inconnue ne doit pas être acceptée.")


def test_analyse_ia_accepte_une_provenance_connue():
    donnees = {
        "constats_convergents": [
            {"constat": "Les sources présentent la même notion.", "contribution_ids": [5, 6]}
        ],
        "formulations_equivalentes": [],
        "divergences_reelles": [],
        "notions_manquantes": [],
        "hors_programme_potentiels": [],
        "points_non_verifiables": [],
        "limites": [],
        "synthese_proposee": "Une synthèse pédagogique structurée et suffisamment détaillée. " * 4,
        "avertissement": "Brouillon à revoir.",
    }

    resultat = harmonisation_ia._valider_resultat(donnees, {5, 6})
    assert resultat["constats_convergents"][0]["contribution_ids"] == [5, 6]
    assert "synthese_proposee" in resultat


def test_modeles_et_file_ia_contiennent_les_nouvelles_tables():
    assert LeconReferentielle.__tablename__ == "leconreferentielle"
    assert ContributionLecon.__tablename__ == "contributionlecon"
    assert "analyse_comparative_lecon_id" in TacheIA.__table__.columns
    assert "uq_tache_ia_type_analyse_comparative_lecon" in {
        index.name for index in TacheIA.__table__.indexes
    }


def test_templates_exposent_la_separation_enseignant_admin_et_publication():
    racine = Path(__file__).resolve().parents[1] / "app" / "templates"
    contenu_enseignant = (racine / "harmonisation_referentiel_enseignant.html").read_text(encoding="utf-8")
    contenu_detail = (racine / "harmonisation_lecon_detail.html").read_text(encoding="utf-8")
    contenu_public = (racine / "cours_harmonise_national.html").read_text(encoding="utf-8")
    assert "Voir la leçon et contribuer" in contenu_enseignant
    assert "Soumettre ma contribution" in contenu_detail
    assert "Comparer les contributions actives" in contenu_detail
    assert "Publier la version finale vérifiée" in contenu_detail
    assert "Les contributions d'origine et les analyses de travail ne sont pas publiées" in contenu_public
