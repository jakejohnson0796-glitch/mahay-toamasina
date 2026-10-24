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



def test_bibliotheque_documents_recherche_tri_couvertures_et_accessibilite():
    html = lire("app/templates/documents_list.html")
    base = lire("app/templates/base.html")
    css = lire("app/static/documents-library.css")

    assert 'class="contenu-clair page-bibliotheque-documents"' in html
    assert 'id="doc-recherche"' in html
    assert 'id="doc-tri"' in html
    assert 'id="doc-resultats" role="status" aria-live="polite"' in html
    assert 'id="doc-recherche-vide" class="doc-recherche-vide" role="status" hidden' in html
    assert 'querySelectorAll(".doc-carte")' in html
    assert 'localeCompare' in html
    assert 'doc-couverture-maths' in html and 'doc-couverture-physique' in html
    assert 'request.url.path == "/documents"' in base
    assert "documents-library.css?v=" in base
    assert "repeat(auto-fit, minmax(min(100%, 19rem), 1fr))" in css
    assert "@media (max-width: 640px)" in css
    assert "prefers-reduced-motion: reduce" in css


def test_bibliotheque_conserve_recherche_tri_et_cercle_pendant_les_filtres():
    html = lire("app/templates/documents_list.html")

    assert 'name="q" id="doc-filtre-q"' in html
    assert 'name="sort" id="doc-filtre-sort"' in html
    assert 'name="cercle_id" value="{{ cercle.id }}"' in html
    assert 'champRechercheFiltres.value = rechercheDocuments ? rechercheDocuments.value.trim() : ""' in html
    assert 'champTriFiltres.value = tri' in html


def test_bibliotheque_n_envoie_pas_un_cercle_vide_dans_les_liens_de_filtre():
    html = lire("app/templates/documents_list.html")

    assert "{{ '&cercle_id=' ~ cercle.id if cercle else '' }}" in html
    assert "&cercle_id={{ cercle.id if cercle else '' }}" not in html
