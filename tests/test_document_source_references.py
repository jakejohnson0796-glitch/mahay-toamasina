import json
from contextlib import nullcontext
from types import SimpleNamespace

from app import text_extraction
from app.routers import tuteur_router


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_pdf_extraction_preserves_real_page_numbers(monkeypatch):
    monkeypatch.setattr(
        text_extraction.pdfplumber,
        "open",
        lambda _path: FakePdf([
            FakePage("Introduction générale."),
            FakePage("Le déterminant d'une matrice carrée."),
            FakePage("Exemples d'application."),
        ]),
    )

    passages = text_extraction.extraire_passages_avec_sources("cours.pdf")

    assert passages == [
        {"reference": "page 1", "texte": "Introduction générale."},
        {"reference": "page 2", "texte": "Le déterminant d'une matrice carrée."},
        {"reference": "page 3", "texte": "Exemples d'application."},
    ]


def test_tuteur_selectionne_le_passage_pertinent_et_conserve_sa_reference(monkeypatch):
    monkeypatch.setattr(
        tuteur_router,
        "ouvrir_fichier_local",
        lambda _reference: nullcontext("/tmp/cours.pdf"),
    )
    monkeypatch.setattr(
        tuteur_router,
        "extraire_passages_avec_sources",
        lambda _path: [
            {"reference": "page 1", "texte": "Introduction à l'histoire des matrices."},
            {"reference": "page 4", "texte": "Le déterminant permet de calculer l'inversibilité d'une matrice."},
            {"reference": "page 5", "texte": "Applications et exercices complémentaires."},
        ],
    )

    extrait, references = tuteur_router._extrait_document_pertinent(
        SimpleNamespace(chemin_fichier="cours.pdf"),
        "Explique le déterminant.",
    )

    assert "Le déterminant permet de calculer" in extrait
    assert "[Référence source : page 4]" in extrait
    assert "page 4" in references
    assert "page 1" not in references


def test_sources_documentaires_historiques_sont_lues_de_facon_defensive():
    session_tuteur = SimpleNamespace(
        sources_documentaires_json=json.dumps([
            {"titre": "Cours de matrices", "references": ["page 4", "page 5"]},
            {"titre": "", "references": ["page 1"]},
            "valeur invalide",
        ], ensure_ascii=False)
    )

    assert tuteur_router._charger_sources_documentaires(session_tuteur) == [
        {"titre": "Cours de matrices", "references": ["page 4", "page 5"]}
    ]
    assert tuteur_router._charger_sources_documentaires(
        SimpleNamespace(sources_documentaires_json="JSON invalide")
    ) == []
