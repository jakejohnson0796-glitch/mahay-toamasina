"""Analyse de documents en lot, avec concurrence bornée et isolation de la session DB.

Les téléchargements Storage sont préparés avant le pool. Les workers ne
touchent jamais à la session SQLModel partagée par la requête HTTP.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Sequence

from .document_classifier import classifier_document
from .storage import ouvrir_fichier_local
from .text_extraction import extraire_texte

MAX_DOCUMENTS_PAR_LOT = 15
MAX_TAILLE_DOCUMENT_PAR_LOT = 120 * 1024 * 1024
# Render Free dispose de peu de mémoire : l'OCR de gros PDF doit rester borné.
MAX_ANALYSES_PARALLELES = 2


def _analyser_document_local(
    chemin_local: str,
    nom_fichier: str,
    filieres: Sequence[Any],
    *,
    titre_fourni: str = "",
    matiere_fourni: str = "",
    type_fourni: Any = None,
    annee_fournie: int | None = None,
    filiere_id_fournie: int | None = None,
) -> dict[str, Any]:
    """Extrait puis classe un fichier. Cette fonction est sûre pour un worker."""
    texte = extraire_texte(chemin_local)
    classification = classifier_document(
        nom_fichier=nom_fichier,
        texte=texte or "",
        filieres=filieres,
        titre_fourni=titre_fourni,
        matiere_fourni=matiere_fourni,
        type_fourni=type_fourni,
        annee_fournie=annee_fournie,
        filiere_id_fournie=filiere_id_fournie,
    )
    return {
        "classification": classification,
        "caracteres_extraits": len(texte or ""),
    }


def analyser_documents_stockes(
    documents: Sequence[dict[str, Any]],
    filieres: Sequence[Any],
    *,
    titre_fourni: str = "",
    matiere_fourni: str = "",
    type_fourni: Any = None,
    annee_fournie: int | None = None,
    filiere_id_fournie: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Analyse chaque document, avec au plus deux OCR/classifications actifs.

    Le résultat est indexé par l'index d'origine. Une erreur sur un fichier ne
    bloque pas le reste du lot et ne contient jamais le texte extrait.
    """
    resultats: dict[int, dict[str, Any]] = {}
    if not documents:
        return resultats

    with ExitStack() as pile:
        prepares: list[tuple[int, dict[str, Any], str]] = []
        for index, document in enumerate(documents):
            try:
                chemin_local = pile.enter_context(
                    ouvrir_fichier_local(str(document["chemin_stocke"]))
                )
                prepares.append((index, document, str(Path(chemin_local))))
            except Exception:
                resultats[index] = {
                    "erreur": "Le fichier a été enregistré mais ne peut pas être relu pour analyse."
                }

        if not prepares:
            return resultats

        workers = min(MAX_ANALYSES_PARALLELES, len(prepares))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mahay-doc") as pool:
            futures = {
                pool.submit(
                    _analyser_document_local,
                    chemin_local,
                    str(document.get("nom_fichier") or "document"),
                    filieres,
                    titre_fourni=titre_fourni,
                    matiere_fourni=matiere_fourni,
                    type_fourni=type_fourni,
                    annee_fournie=annee_fournie,
                    filiere_id_fournie=filiere_id_fournie,
                ): index
                for index, document, chemin_local in prepares
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    resultats[index] = future.result()
                except Exception:
                    resultats[index] = {
                        "erreur": "L'extraction ou la classification de ce fichier a échoué."
                    }

    return resultats
