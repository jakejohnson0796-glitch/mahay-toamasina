from pathlib import Path

from app.templating import templates


ROOT = Path(__file__).resolve().parents[1]


def lire(chemin: str) -> str:
    return (ROOT / chemin).read_text(encoding="utf-8")


def test_bibliotheque_documents_preserve_un_resume_compact_et_accessible():
    html = lire("app/templates/documents_list.html")

    # Une longue fiche ne doit plus imposer sa hauteur à toute la grille.
    assert '.doc-fiche[open] > [data-fiche-lang]:not([hidden])' in html
    assert "max-height:min(18rem,42vh)" in html
    assert "overflow:auto" in html

    # Les couleurs du carnet doivent rester lisibles dans les deux thèmes.
    assert ".doc-revision-actions{background:#f5faf7;border-color:#91aa9e" in html
    assert 'html[data-theme="sombre"] .doc-revision-actions{background:#142b26' in html


def test_bibliotheque_documents_met_en_evidence_le_lancement_du_quiz():
    html = lire("app/templates/documents_list.html")
    parcours = lire("app/templates/document_parcours.html")

    assert 'class="doc-lien-quiz doc-quiz-cta" href="/documents/{{ doc.id }}/quiz"' in html
    assert "Vérifier puis lancer le quiz" in html
    assert "Lancer le Quiz IA maintenant" in parcours


def test_anciens_cours_sans_fiche_sont_planifies_automatiquement():
    route = lire("app/routers/documents_router.py")

    assert "cours_sans_fiche" in route
    assert "document.type_document == TypeDocument.COURS" in route
    assert "for document_id in cours_sans_fiche[:10]" in route
    assert "ai_queue.planifier_fiche_revision_document(document_id)" in route


def test_templates_de_la_bibliotheque_et_du_parcours_compilent():
    assert templates.env.get_template("documents_list.html") is not None
    assert templates.env.get_template("document_parcours.html") is not None
