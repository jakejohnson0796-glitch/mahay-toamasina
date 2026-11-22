from app.programmes_officiels import (
    est_source_officielle,
    normaliser_code_element,
    proposer_structure_programme,
    extraction_validable_apres_controle_manuel,
)
from app.request_limits import SINGLE_DOCUMENT_BODY_LIMIT, limite_corps_requete
from app.admin_security import TAILLE_MAX_FORMULAIRE_ADMIN, limite_formulaire_admin


def test_extraction_reconnait_chapitres_et_lecons_sans_les_valider():
    texte = """
    PROGRAMME SCOLAIRE
    CHAPITRE I : INTRODUCTION
    LEÇON 1 : Les nombres entiers
    Les nombres entiers sont utilisés pour compter.
    LEÇON 2 : Les opérations
    Addition, soustraction et multiplication.
    CHAPITRE II : GÉOMÉTRIE
    1.1 Les points et les droites
    """
    structure = proposer_structure_programme(texte)
    assert [item["type_element"] for item in structure] == [
        "chapitre", "lecon", "lecon", "chapitre", "lecon"
    ]
    assert structure[1]["parent_code"] == structure[0]["code"]
    assert structure[2]["parent_code"] == structure[0]["code"]
    assert structure[4]["parent_code"] == structure[3]["code"]
    assert all(item.get("statut_validation") is None for item in structure)


def test_extraction_conserve_un_document_sans_structure_dans_un_bloc_a_relire():
    structure = proposer_structure_programme(
        "Ce programme présente les notions principales et leur progression."
    )
    assert len(structure) == 1
    assert structure[0]["type_element"] == "rubrique"
    assert structure[0]["titre"] == "Contenu extrait — structure à organiser"
    assert "progression" in structure[0]["contenu"]


def test_source_officielle_exige_https_et_un_domaine_ministeriel_exact():
    assert est_source_officielle("https://education.gov.mg/programmes/ep.pdf")
    assert est_source_officielle("https://www.metfp.gov.mg/documents/frp.pdf")
    assert not est_source_officielle("http://education.gov.mg/programmes.pdf")
    assert not est_source_officielle("https://education.gov.mg.evil.test/programmes.pdf")
    assert not est_source_officielle("https://education-gov.mg/programmes.pdf")
    assert not est_source_officielle("https://user:secret@education.gov.mg/doc.pdf")


def test_code_manuel_est_ascii_et_borne():
    code = normaliser_code_element("Électricité générale : circuits", 4)
    assert code.startswith("MAN-ELECTRICITE-GENERALE-CIRCUITS")
    assert len(code) <= 60


def test_import_programme_respecte_la_limite_http_de_document():
    assert limite_corps_requete(
        "POST", "/admin/programmes-officiels/importer"
    ) == SINGLE_DOCUMENT_BODY_LIMIT
    assert limite_formulaire_admin(
        "/admin/programmes-officiels/importer"
    ) == SINGLE_DOCUMENT_BODY_LIMIT
    assert TAILLE_MAX_FORMULAIRE_ADMIN < SINGLE_DOCUMENT_BODY_LIMIT



def test_extraction_faible_exige_une_confirmation_de_lecture_originale():
    assert not extraction_validable_apres_controle_manuel(0, False)
    assert not extraction_validable_apres_controle_manuel(79, False)
    assert extraction_validable_apres_controle_manuel(80, False)
    assert extraction_validable_apres_controle_manuel(0, True)


def test_empreinte_sha256_est_unique_en_base():
    from sqlalchemy import UniqueConstraint
    from app.models_programmes_officiels import ProgrammeOfficielScolaire

    contraintes = {
        contrainte.name
        for contrainte in ProgrammeOfficielScolaire.__table__.constraints
        if isinstance(contrainte, UniqueConstraint)
    }
    assert "uq_programmeofficiel_empreinte_sha256" in contraintes
