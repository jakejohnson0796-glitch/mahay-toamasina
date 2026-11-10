from contextlib import contextmanager
from pathlib import Path
from threading import Lock
import time

from app import document_batch


def test_lot_analyse_tous_les_fichiers_et_conserve_les_indices(monkeypatch, tmp_path):
    actifs = 0
    maximum = 0
    verrou = Lock()

    @contextmanager
    def faux_ouvrir(chemin):
        yield Path(chemin)

    def faux_analyser(chemin, nom, filieres, **kwargs):
        nonlocal actifs, maximum
        with verrou:
            actifs += 1
            maximum = max(maximum, actifs)
        time.sleep(0.02)
        with verrou:
            actifs -= 1
        return {"classification": nom, "caracteres_extraits": 120}

    fichiers = []
    for index in range(7):
        chemin = tmp_path / f"document-{index}.pdf"
        chemin.write_bytes(b"pdf")
        fichiers.append({"nom_fichier": chemin.name, "chemin_stocke": str(chemin)})

    monkeypatch.setattr(document_batch, "ouvrir_fichier_local", faux_ouvrir)
    monkeypatch.setattr(document_batch, "_analyser_document_local", faux_analyser)
    monkeypatch.setattr(document_batch, "MAX_ANALYSES_PARALLELES", 2)

    resultats = document_batch.analyser_documents_stockes(fichiers, [])

    assert sorted(resultats) == list(range(7))
    assert [resultats[index]["classification"] for index in range(7)] == [
        f"document-{index}.pdf" for index in range(7)
    ]
    assert maximum == 2


def test_erreur_lecture_d_un_fichier_ne_bloque_pas_le_lot(monkeypatch, tmp_path):
    @contextmanager
    def faux_ouvrir(chemin):
        if str(chemin).endswith("illisible.pdf"):
            raise OSError("storage indisponible")
        yield Path(chemin)

    def faux_analyser(chemin, nom, filieres, **kwargs):
        return {"classification": nom, "caracteres_extraits": 20}

    fichiers = [
        {"nom_fichier": "illisible.pdf", "chemin_stocke": "illisible.pdf"},
        {"nom_fichier": "bon.pdf", "chemin_stocke": str(tmp_path / "bon.pdf")},
    ]
    (tmp_path / "bon.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(document_batch, "ouvrir_fichier_local", faux_ouvrir)
    monkeypatch.setattr(document_batch, "_analyser_document_local", faux_analyser)

    resultats = document_batch.analyser_documents_stockes(fichiers, [])

    assert "erreur" in resultats[0]
    assert resultats[1]["classification"] == "bon.pdf"


def test_limites_de_lot_sont_bornees_pour_render_free():
    assert document_batch.MAX_DOCUMENTS_PAR_LOT == 15
    assert document_batch.MAX_ANALYSES_PARALLELES == 2
    assert document_batch.MAX_TAILLE_DOCUMENT_PAR_LOT == 120 * 1024 * 1024
