import json
from types import SimpleNamespace

from fastapi.responses import RedirectResponse

from app.ai_quiz import OUTIL_TUTEUR, OUTIL_TUTEUR_VERIFICATION, generer_reponse_tuteur
from app.models import Document, RoleUtilisateur, SessionTuteur, StatutDocument
from app.routers import documents_router


def test_tuteur_genere_un_indice_distinct_sans_supprimer_les_quatre_sections(monkeypatch):
    payload = {
        "explication": "Voici la méthode générale.",
        "exemple": "Exemple court.",
        "indice": "Commence par isoler les données de l'énoncé.",
        "exercice": "Calcule le déterminant de cette matrice.",
        "correction": "La correction détaillée.",
    }
    message = SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(payload, ensure_ascii=False)))])
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    monkeypatch.setattr("app.ai_quiz._obtenir_client", lambda: object())
    monkeypatch.setattr("app.ai_quiz.ai_memory.contexte_erreurs_recurrentes", lambda **_kwargs: "")
    monkeypatch.setattr("app.ai_quiz.ai_ensemble.cost_controller.call", lambda *_args, **_kwargs: completion)
    response = generer_reponse_tuteur("Aide-moi avec un déterminant.", notion="Déterminant", matiere="Mathématiques", verifier=False)
    assert response["indice"] == payload["indice"]
    for key in ("explication", "exemple", "exercice", "correction"):
        assert response[key] == payload[key]


def test_contrat_du_tuteur_separe_indice_et_correction():
    assert "indice" in OUTIL_TUTEUR["function"]["parameters"]["properties"]
    assert "indice" in OUTIL_TUTEUR["function"]["parameters"]["required"]
    assert "indice" not in OUTIL_TUTEUR_VERIFICATION["function"]["parameters"]["properties"]
    assert "indice" not in OUTIL_TUTEUR_VERIFICATION["function"]["parameters"]["required"]
    assert "indice" in SessionTuteur.model_fields


def test_fiche_documentaire_n_est_validable_que_si_une_extraction_exploitable_existe():
    from app.routers.documents_router import _fiche_pedagogique_peut_etre_validee
    assert _fiche_pedagogique_peut_etre_validee(SimpleNamespace(resume_ia="Résumé", resume_statut_ia="generee"))
    assert _fiche_pedagogique_peut_etre_validee(SimpleNamespace(resume_ia="Aperçu", resume_statut_ia="provisoire"))
    assert not _fiche_pedagogique_peut_etre_validee(SimpleNamespace(resume_ia="X", resume_statut_ia="insuffisante"))
    assert not _fiche_pedagogique_peut_etre_validee(SimpleNamespace(resume_ia="", resume_statut_ia="generee"))


def test_generation_quiz_document_est_bloquee_tant_que_la_fiche_n_est_pas_validee(monkeypatch):
    user = SimpleNamespace(id=8, role=RoleUtilisateur.ETUDIANT, niveau="L1")
    document = SimpleNamespace(id=42, statut=StatutDocument.APPROUVE, fiche_validation_statut="a_verifier",
        chemin_fichier="not-opened.pdf", titre="Document test", matiere="Mathématiques", resume_ia="Résumé", resume_statut_ia="generee")
    fake_session = SimpleNamespace(get=lambda _model, ident: document if ident == 42 else None)
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _request, _session: user)
    monkeypatch.setattr(documents_router, "acces_premium_ou_redirection", lambda _user, _session: None)
    monkeypatch.setattr(documents_router, "generer_quiz_depuis_texte", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("Quiz généré trop tôt")))
    response = documents_router.quiz_document(None, 42, session=fake_session)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/documents/42/apprendre?erreur=fiche_a_verifier")


def test_route_validation_fiche_enregistre_corrections_et_audit(monkeypatch):
    user = SimpleNamespace(id=12, role=RoleUtilisateur.ETUDIANT)
    original = {"resume":"Résumé ancien.","objectif_pedagogique":"Objectif ancien.","niveau_cible":"L1","notions_cles":["Ancienne notion"],"source":"ia","statut":"generee"}
    document = SimpleNamespace(id=43,uploader_id=user.id,statut=StatutDocument.APPROUVE,resume_ia="Résumé ancien.",
        resume_statut_ia="generee",fiche_pedagogique_json=json.dumps(original,ensure_ascii=False),fiche_validation_statut="a_verifier",
        fiche_validee_par_id=None,fiche_validee_le=None,resume_ia_mg="Résumé MG",fiche_pedagogique_mg_json='{"resume":"Résumé MG"}',resume_statut_ia_mg="generee")
    class FakeSession:
        def get(self, model, ident): return document if model is Document and ident == document.id else None
        def add(self, _obj): pass
        def commit(self): pass
    monkeypatch.setattr(documents_router, "utilisateur_courant", lambda _r, _s: user)
    response=documents_router.valider_fiche_document(None,43,resume_verifie="Résumé corrigé.",objectif_verifie="Objectif corrigé.",
        niveau_verifie="L2",notions_verifiees="Notion corrigée\nNotion corrigée",confirmer_contenu=True,confirmer_metadonnees=True,session=FakeSession())
    assert isinstance(response, RedirectResponse) and response.status_code == 303
    assert document.fiche_validation_statut == "validee"
    assert document.fiche_validee_par_id == user.id and document.fiche_validee_le is not None
    assert document.resume_ia == "Résumé corrigé."
    saved=json.loads(document.fiche_pedagogique_json)
    assert saved["notions_cles"] == ["Notion corrigée"] and saved["validation_humaine"]
    assert document.resume_ia_mg == "" and document.resume_statut_ia_mg == "indisponible"


def test_templates_exigent_relecture_humaine_et_affichent_un_indice_progressif():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    tutor=(root/"app/templates/tuteur_reponse.html").read_text(encoding="utf-8")
    hub=(root/"app/templates/document_parcours.html").read_text(encoding="utf-8")
    library=(root/"app/templates/documents_list.html").read_text(encoding="utf-8")
    moderation=(root/"app/templates/moderation_document_preview.html").read_text(encoding="utf-8")
    assert "Dévoiler l'indice progressif" in tutor
    assert 'data-tuteur-content="indice"' in tutor
    assert 'id="fiche-verification"' in hub
    assert 'name="confirmer_contenu"' in hub and 'name="confirmer_metadonnees"' in hub
    assert 'doc.fiche_validation_statut == "validee"' in library
    assert "/documents/{{ document.id }}/apprendre#fiche-verification" in moderation
