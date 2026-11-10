from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import TypeDocument
from app.routers.documents_router import (
    _normaliser_bepc_session_2027_parcours,
    _normaliser_metadonnees_document,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("parcours", ["pe", "ps_a", "ps_b"])
@pytest.mark.parametrize("type_document", [TypeDocument.ANNALE, TypeDocument.CORRIGE])
def test_accepte_les_trois_parcours_bepc_2027_pour_les_annales_de_3e(parcours, type_document):
    niveau = SimpleNamespace(cycle="college", libelle="3e")

    valeur, erreur = _normaliser_bepc_session_2027_parcours(
        parcours,
        portee_academique="scolaire",
        niveau_scolaire=niveau,
        type_document=type_document,
        annee=2027,
    )

    assert erreur is None
    assert valeur == parcours


def test_exige_un_parcours_pour_un_corrige_bepc_2027_de_3e():
    niveau = SimpleNamespace(cycle="college", libelle="3e")

    valeur, erreur = _normaliser_bepc_session_2027_parcours(
        None,
        portee_academique="scolaire",
        niveau_scolaire=niveau,
        type_document=TypeDocument.CORRIGE,
        annee=2027,
    )

    assert valeur is None
    assert "sélectionnez le PE" in erreur


@pytest.mark.parametrize(
    "valeur,cycle,classe,type_document,annee",
    [
        ("pe", "college", "3e", TypeDocument.ANNALE, 2026),
        ("ps_a", "college", "4e", TypeDocument.ANNALE, 2027),
        ("ps_b", "lycee", "Terminale", TypeDocument.CORRIGE, 2027),
        ("pe", "college", "3e", TypeDocument.COURS, 2027),
        ("option_c", "college", "3e", TypeDocument.ANNALE, 2027),
    ],
)
def test_refuse_un_parcours_bepc_hors_perimetre_ou_invalide(
    valeur, cycle, classe, type_document, annee
):
    niveau = SimpleNamespace(cycle=cycle, libelle=classe)

    resultat, erreur = _normaliser_bepc_session_2027_parcours(
        valeur,
        portee_academique="scolaire",
        niveau_scolaire=niveau,
        type_document=type_document,
        annee=annee,
    )

    assert resultat is None
    assert erreur


def test_ne_demande_pas_de_parcours_bepc_aux_autres_documents():
    niveau = SimpleNamespace(cycle="college", libelle="3e")

    valeur, erreur = _normaliser_bepc_session_2027_parcours(
        None,
        portee_academique="scolaire",
        niveau_scolaire=niveau,
        type_document=TypeDocument.COURS,
        annee=2027,
    )

    assert valeur is None
    assert erreur is None


def test_metadata_admin_accepte_un_document_scolaire_sans_filiere():
    donnees, erreur = _normaliser_metadonnees_document(
        titre="Annale BEPC 2027",
        matiere="Mathématiques",
        type_document="annale",
        annee="2027",
        filiere_id="",
        filiere_requise=False,
    )

    assert erreur is None
    assert donnees["filiere_id"] is None


def test_metadata_admin_refuse_une_filiere_universitaire_sur_un_document_scolaire():
    donnees, erreur = _normaliser_metadonnees_document(
        titre="Annale BEPC 2027",
        matiere="Mathématiques",
        type_document="annale",
        annee="2027",
        filiere_id="17",
        filiere_requise=False,
    )

    assert donnees is None
    assert "document scolaire" in erreur


def test_upload_et_moderation_exposent_le_classement_bepc_2027():
    router = (ROOT / "app/routers/documents_router.py").read_text(encoding="utf-8")
    upload = (ROOT / "app/templates/document_upload.html").read_text(encoding="utf-8")
    cascade = (ROOT / "app/static/js/cascade-scolaire-documents.js").read_text(encoding="utf-8")
    moderation = (ROOT / "app/templates/moderation_document_modifier.html").read_text(encoding="utf-8")
    documents = (ROOT / "app/templates/documents_list.html").read_text(encoding="utf-8")

    assert "bepc_session_2027_parcours: Optional[str] = Form(default=None)" in router
    assert "BEPC_SESSION_2027_PARCOURS" in router
    assert "bepc_session_2027_parcours=bepc_parcours_valide" in router
    assert "bepc_session_2027_parcours = parcours_bepc_valide" in router
    assert 'name="bepc_session_2027_parcours"' in upload
    assert 'documentYear.value === "2027"' in cascade
    assert "bepcParcours.required = visible" in cascade
    assert "bepcParcours.disabled = !visible" in cascade
    assert "Nouveau Programme d’études (PE)" in upload
    assert 'name="bepc_session_2027_parcours"' in moderation
    assert "Programme scolaire (PS) · Option A" in documents
    assert "Programme scolaire (PS) · Option B" in documents
    model = (ROOT / "app/models.py").read_text(encoding="utf-8")
    document_model = model.split("class Document(SQLModel, table=True):", 1)[1].split(
        "class ProgressionNotion(SQLModel, table=True):", 1
    )[0]
    assert "bepc_session_2027_parcours" in document_model


def test_migration_ajoute_un_champ_nullable_avec_index():
    migration = (
        ROOT
        / "alembic/versions/l6d8b2f1a4c9_bepc_2027_parcours_annales.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: Union[str, Sequence[str], None] = "k3f8a1d6c9b2"' in migration
    assert '"bepc_session_2027_parcours"' in migration
    assert "nullable=True" in migration
    assert "ix_document_bepc_session_2027_parcours" in migration
