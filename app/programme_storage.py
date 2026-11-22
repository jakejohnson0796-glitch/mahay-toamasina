"""Stockage privé des sources EP/FRP, distinct du bucket public des documents."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterator, Optional
import contextlib
import tempfile

from .config import parametres
from .storage import _obtenir_client_supabase, stockage_distant_actif

BUCKET_PROGRAMMES_OFFICIELS = "programmes-officiels-prives"
DOSSIER_LOCAL = Path(__file__).resolve().parents[1] / "uploads" / "programmes_officiels"


def _nom_sur(nom: str) -> str:
    base = Path(nom or "programme").name
    ascii_nom = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    nettoye = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_nom).strip("._")[:120]
    return nettoye or "programme.pdf"


def _assurer_bucket_prive(client) -> None:
    try:
        client.storage.get_bucket(BUCKET_PROGRAMMES_OFFICIELS)
        return
    except Exception:
        pass
    try:
        client.storage.create_bucket(
            BUCKET_PROGRAMMES_OFFICIELS,
            options={
                "public": False,
                "file_size_limit": 20 * 1024 * 1024,
                "allowed_mime_types": [
                    "application/pdf",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-powerpoint",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ],
            },
        )
    except Exception:
        # Tolère une création concurrente ; re-lève si le bucket est réellement absent.
        client.storage.get_bucket(BUCKET_PROGRAMMES_OFFICIELS)


def sauvegarder_programme_officiel(reference: str, nom_original: str, contenu: bytes, mime: str) -> str:
    """Enregistre la source dans un bucket privé ou un dossier local non public."""
    nom = _nom_sur(nom_original)
    objet = f"{reference}/{nom}"
    if stockage_distant_actif():
        client = _obtenir_client_supabase()
        _assurer_bucket_prive(client)
        client.storage.from_(BUCKET_PROGRAMMES_OFFICIELS).upload(
            path=objet,
            file=contenu,
            file_options={"content-type": mime, "upsert": "false"},
        )
        return objet
    DOSSIER_LOCAL.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_LOCAL / reference / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    return str(chemin)


def url_telechargement_programme(reference_fichier: str, expires_in: int = 60) -> Optional[str]:
    """Retourne une URL signée courte pour Supabase ; None en stockage local."""
    if not stockage_distant_actif():
        return None
    client = _obtenir_client_supabase()
    reponse = client.storage.from_(BUCKET_PROGRAMMES_OFFICIELS).create_signed_url(
        reference_fichier, expires_in, {"download": True}
    )
    if isinstance(reponse, dict):
        return (
            reponse.get("signedURL")
            or reponse.get("signedUrl")
            or reponse.get("signed_url")
        )
    return None


def supprimer_programme_officiel(reference_fichier: str) -> None:
    """Nettoyage best-effort lorsqu'une transaction d'import échoue."""
    if stockage_distant_actif():
        try:
            _obtenir_client_supabase().storage.from_(BUCKET_PROGRAMMES_OFFICIELS).remove(
                [reference_fichier]
            )
        except Exception:
            pass
        return
    chemin = Path(reference_fichier)
    try:
        if chemin.exists():
            chemin.unlink()
            if chemin.parent != DOSSIER_LOCAL and chemin.parent.exists():
                chemin.parent.rmdir()
    except OSError:
        pass


@contextlib.contextmanager
def ouvrir_programme_officiel(reference_fichier: str) -> Iterator[Path]:
    """Ouvre la source EP/FRP dans son bucket privé, sans modifier le stockage partagé."""
    if not stockage_distant_actif():
        yield Path(reference_fichier)
        return
    contenu = _obtenir_client_supabase().storage.from_(
        BUCKET_PROGRAMMES_OFFICIELS
    ).download(reference_fichier)
    suffixe = Path(reference_fichier).suffix
    with tempfile.NamedTemporaryFile(suffix=suffixe) as temporaire:
        temporaire.write(contenu)
        temporaire.flush()
        yield Path(temporaire.name)
