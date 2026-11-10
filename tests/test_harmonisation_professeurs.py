from datetime import datetime
from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.models import RoleUtilisateur, StatutDemandeMiseAJourCours, StatutDocument, TypeDocument
from app.routers import harmonisation_router


def test_espace_enseignant_refuse_un_eleve(monkeypatch):
    eleve = SimpleNamespace(
        id=7,
        role=RoleUtilisateur.ETUDIANT,
        statut_verification_enseignant="non_concerne",
    )
    monkeypatch.setattr(harmonisation_router, "utilisateur_courant", lambda request, session: eleve)
    response = harmonisation_router.page_harmonisation_professeur(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_espace_enseignant_refuse_un_professeur_non_verifie(monkeypatch):
    professeur = SimpleNamespace(
        id=8,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="en_attente",
    )
    monkeypatch.setattr(harmonisation_router, "utilisateur_courant", lambda request, session: professeur)
    response = harmonisation_router.page_harmonisation_professeur(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert response.status_code == 303


def test_espace_admin_refuse_un_professeur(monkeypatch):
    professeur = SimpleNamespace(
        id=8,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="approuve",
    )
    monkeypatch.setattr(harmonisation_router, "utilisateur_courant", lambda request, session: professeur)
    response = harmonisation_router.page_harmonisation_admin(
        SimpleNamespace(), session=SimpleNamespace()
    )
    assert response.status_code == 303


def test_admin_peut_publier_une_proposition_sur_la_version_examinee():
    maintenant = datetime(2026, 11, 10, 12, 0, 0)
    document = SimpleNamespace(
        statut=StatutDocument.APPROUVE,
        type_document=TypeDocument.COURS,
        version_harmonisee=2,
        contenu_harmonise="Ancienne version",
        date_mise_a_jour_harmonisee=None,
    )
    demande = SimpleNamespace(
        version_source=2,
        contenu_propose="Nouvelle version complète du cours.",
        statut=StatutDemandeMiseAJourCours.EN_ATTENTE.value,
        traite_par_id=None,
        date_traitement=None,
        date_modification=None,
        motif_decision="",
    )
    admin = SimpleNamespace(id=99)

    publie = harmonisation_router.publier_demande_validee(
        demande, document, admin, maintenant
    )

    assert publie is True
    assert document.contenu_harmonise == demande.contenu_propose
    assert document.version_harmonisee == 3
    assert document.date_mise_a_jour_harmonisee == maintenant
    assert demande.statut == StatutDemandeMiseAJourCours.VALIDEE.value
    assert demande.traite_par_id == 99


def test_proposition_obsolete_ne_peut_pas_ecraser_une_version_plus_recente():
    document = SimpleNamespace(
        statut=StatutDocument.APPROUVE,
        type_document=TypeDocument.COURS,
        version_harmonisee=4,
        contenu_harmonise="Version récente",
        date_mise_a_jour_harmonisee=None,
    )
    demande = SimpleNamespace(
        version_source=3,
        contenu_propose="Ancienne proposition",
        statut=StatutDemandeMiseAJourCours.EN_ATTENTE.value,
        traite_par_id=None,
        date_traitement=None,
        date_modification=None,
        motif_decision="",
    )

    publie = harmonisation_router.publier_demande_validee(
        demande, document, SimpleNamespace(id=99)
    )

    assert publie is False
    assert document.contenu_harmonise == "Version récente"
    assert document.version_harmonisee == 4


def test_carte_document_affiche_la_date_de_publication_harmonisee():
    from pathlib import Path

    template = Path(__file__).resolve().parents[1] / "app" / "templates" / "documents_list.html"
    contenu = template.read_text(encoding="utf-8")
    assert "Document mis à jour le" in contenu
    assert "/documents/{{ doc.id }}/cours-harmonise" in contenu


def _rendre_bloc_harmonisation_du_dashboard(alertes_harmonisation):
    from pathlib import Path

    from jinja2 import Environment

    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "dashboard_etudiant.html"
    )
    source = template.read_text(encoding="utf-8")
    debut = source.index(
        "{% if alertes_harmonisation is not none %}Espace enseignant"
    )
    marqueur_fin = '    {% endif %}

    <section class="tb-routine"'
    fin = source.index(marqueur_fin, debut)
    bloc = source[debut:fin + len("    {% endif %}")]
    environnement = Environment(autoescape=True)
    return environnement.from_string(bloc).render(
        alertes_harmonisation=alertes_harmonisation,
        request=SimpleNamespace(),
        csp_nonce=lambda _request: "test-nonce",
    )


def test_dashboard_conditionne_les_alertes_aux_professeurs_valides():
    from pathlib import Path

    template = Path(__file__).resolve().parents[1] / "app" / "templates" / "dashboard_etudiant.html"
    contenu = template.read_text(encoding="utf-8")
    assert contenu.count("{% if alertes_harmonisation is not none %}") == 3
    assert "alertes_harmonisation is defined" not in contenu
    assert "{% for item in alertes_harmonisation %}" in contenu
    assert "/enseignant/harmonisation/demandes/" in contenu


def test_dashboard_eleve_ne_tente_pas_diterer_les_alertes_absentes():
    rendu = _rendre_bloc_harmonisation_du_dashboard(None)

    assert "Pret a continuer ton apprentissage ?" in rendu
    assert "Espace enseignant" not in rendu
    assert "tb-harmonisation" not in rendu


def test_dashboard_professeur_sans_demande_affiche_un_etat_vide():
    rendu = _rendre_bloc_harmonisation_du_dashboard([])

    assert "Espace enseignant" in rendu
    assert "Aucune proposition récente." in rendu


def test_professeur_verifie_uniquement_si_role_et_validation_sont_conformes():
    professeur = SimpleNamespace(
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="approuve",
    )
    professeur_en_attente = SimpleNamespace(
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="en_attente",
    )
    eleve = SimpleNamespace(
        role=RoleUtilisateur.ETUDIANT,
        statut_verification_enseignant="approuve",
    )
    assert harmonisation_router.professeur_verifie(professeur)
    assert not harmonisation_router.professeur_verifie(professeur_en_attente)
    assert not harmonisation_router.professeur_verifie(eleve)


def test_consultation_cours_harmonise_refuse_un_eleve(monkeypatch):
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
    response = harmonisation_router.consulter_cours_harmonise_public(
        123,
        SimpleNamespace(),
        session=SimpleNamespace(),
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303


def test_carte_cours_harmonise_est_reservee_aux_professeurs_et_admins():
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "templates"
        / "documents_list.html"
    )
    contenu = template.read_text(encoding="utf-8")
    assert 'utilisateur.role.value == "professeur"' in contenu
    assert 'utilisateur.role.value == "admin"' in contenu
