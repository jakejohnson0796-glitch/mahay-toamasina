"""
Abstraction de stockage des fichiers deposes par les etudiants (annales,
fiches, cours...).

- Si SUPABASE_URL et SUPABASE_SERVICE_KEY sont definis (.env) : les
  fichiers sont envoyes dans un bucket Supabase Storage. C'est le mode a
  utiliser des qu'on deploie ailleurs qu'en local : le disque d'un serveur
  comme Render/Railway/Fly est ephemere, tout uploads/ disparait au
  redeploiement ou au redemarrage du conteneur.
- Sinon : fallback sur le disque local (dossier uploads/), exactement
  comme en V1. Pratique pour developper sans compte Supabase.

Regle importante : Document.chemin_fichier ne doit JAMAIS etre construit
ou interprete directement ailleurs dans le code. C'est une reference
opaque (chemin local relatif, OU cle d'objet dans le bucket Supabase) qui
ne doit passer que par les fonctions de ce module.
"""
import contextlib
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterator

from fastapi import UploadFile

from .config import parametres

DOSSIER_UPLOADS_LOCAL = Path(__file__).resolve().parent.parent / "uploads"

# Types de documents academiques attendus par l'appli (annales, corriges,
# fiches, cours — eventuellement scannes en image pour l'OCR, voir
# pytesseract/pdf2image dans requirements.txt). Tout le reste (executables,
# scripts, archives, HTML/SVG...) est refuse : accepter n'importe quel
# type de fichier permettrait de stocker et redistribuer publiquement du
# contenu dangereux via /documents/{id}/telecharger.
EXTENSIONS_AUTORISEES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png"}
TAILLE_MAX_DOCUMENT = 20 * 1024 * 1024  # 20 Mo


class FichierInvalide(ValueError):
    """Leve par sauvegarder_fichier() si le fichier depose ne respecte
    pas les regles ci-dessus (type ou taille). Le message est destine a
    etre affiche tel quel a l'utilisateur."""


_client_supabase = None


def stockage_distant_actif() -> bool:
    """True si Supabase Storage est configure (cle + URL presentes)."""
    return bool(parametres.supabase_url and parametres.supabase_service_key)


def _obtenir_client_supabase():
    global _client_supabase
    if _client_supabase is None:
        # Import local : si le package `supabase` n'est pas installe et que
        # ce mode n'est pas utilise, le reste de l'appli continue de
        # fonctionner sans planter au demarrage.
        from supabase import create_client

        _client_supabase = create_client(parametres.supabase_url, parametres.supabase_service_key)
    return _client_supabase


def _nettoyer_nom_fichier(nom_fichier: str) -> str:
    """Rend un nom de fichier sur (accents translitteres, tout le reste
    remplace par '_') pour servir de cle d'objet Supabase Storage — qui
    rejette purement et simplement une cle contenant un caractere comme
    'è' (erreur reelle constatee : 'Invalid key: ..._algèbre...pdf').
    Le disque local est plus tolerant, mais autant appliquer la meme
    regle des deux cotes pour un comportement identique partout."""
    # Decompose les caracteres accentues (é -> e + accent) puis ne garde
    # que la partie ASCII, ce qui a pour effet de retirer les accents
    # tout en gardant la lettre de base.
    nom_sans_accents = unicodedata.normalize("NFKD", nom_fichier).encode("ascii", "ignore").decode("ascii")
    # Tout ce qui n'est pas alphanumerique/point/tiret/underscore devient
    # un underscore (espaces, parentheses, caracteres exotiques...).
    return re.sub(r"[^A-Za-z0-9._-]", "_", nom_sans_accents)


def _nom_objet_sur(reference: str, nom_fichier_original: str) -> str:
    # Path(...).name ecarte tout composant de dossier eventuellement
    # present dans le nom fourni par le client (ex: "../../etc/passwd")
    # avant meme le nettoyage caractere-par-caractere ci-dessous — double
    # protection contre toute tentative de traversee de repertoire.
    nom_de_base = Path(nom_fichier_original).name
    nom_nettoye = _nettoyer_nom_fichier(nom_de_base)
    return f"{reference}_{nom_nettoye}"


def sauvegarder_fichier(fichier: UploadFile, reference: str) -> str:
    """Enregistre le fichier uploade (local ou Supabase) et renvoie la
    valeur a stocker dans Document.chemin_fichier.

    Leve FichierInvalide si le type ou la taille du fichier ne respecte
    pas les regles (voir EXTENSIONS_AUTORISEES / TAILLE_MAX_DOCUMENT) —
    a capturer par l'appelant pour afficher un message clair."""
    nom_original = fichier.filename or "document"
    extension = Path(nom_original).suffix.lower()
    if extension not in EXTENSIONS_AUTORISEES:
        extensions_lisibles = ", ".join(sorted(EXTENSIONS_AUTORISEES))
        raise FichierInvalide(f"Type de fichier non accepte. Formats autorises : {extensions_lisibles}.")

    contenu = fichier.file.read()
    if len(contenu) > TAILLE_MAX_DOCUMENT:
        raise FichierInvalide(f"Fichier trop volumineux (max {TAILLE_MAX_DOCUMENT // (1024 * 1024)} Mo).")
    if len(contenu) == 0:
        raise FichierInvalide("Le fichier semble vide.")

    nom_objet = _nom_objet_sur(reference, nom_original)

    if stockage_distant_actif():
        client = _obtenir_client_supabase()
        client.storage.from_(parametres.supabase_bucket).upload(
            nom_objet,
            contenu,
            {"content-type": fichier.content_type or "application/octet-stream"},
        )
        return nom_objet

    DOSSIER_UPLOADS_LOCAL.mkdir(exist_ok=True)
    chemin_local = DOSSIER_UPLOADS_LOCAL / nom_objet
    chemin_local.write_bytes(contenu)
    return str(chemin_local)


def obtenir_url_telechargement(reference_fichier: str) -> str:
    """URL/chemin vers lequel rediriger pour telecharger le fichier."""
    if stockage_distant_actif():
        client = _obtenir_client_supabase()
        return client.storage.from_(parametres.supabase_bucket).get_public_url(reference_fichier)
    return reference_fichier  # chemin local : FileResponse s'en charge directement


@contextlib.contextmanager
def ouvrir_fichier_local(reference_fichier: str) -> Iterator[Path]:
    """Fournit un chemin de fichier local utilisable (pour l'extraction de
    texte avant generation de quiz), en telechargeant depuis Supabase dans
    un fichier temporaire si besoin. A utiliser dans un bloc `with`."""
    if not stockage_distant_actif():
        yield Path(reference_fichier)
        return

    client = _obtenir_client_supabase()
    contenu = client.storage.from_(parametres.supabase_bucket).download(reference_fichier)
    suffixe = Path(reference_fichier).suffix
    with tempfile.NamedTemporaryFile(suffix=suffixe) as tmp:
        tmp.write(contenu)
        tmp.flush()
        yield Path(tmp.name)
