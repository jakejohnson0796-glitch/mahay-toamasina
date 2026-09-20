"""Validation du contenu reel des fichiers importes.

La validation se fait sur les octets, pas sur l'extension ou le Content-Type
annonce par le navigateur. Aucun fichier ZIP/OOXML n'est extrait sur disque.
"""
from io import BytesIO
from pathlib import Path
import warnings
import zipfile

from PIL import Image, UnidentifiedImageError


MIMES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_SIGNATURE_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_SIGNATURE_PDF = b"%PDF-"
_SIGNATURE_PNG = b"\x89PNG\r\n\x1a\n"
_SIGNATURE_JPEG = b"\xff\xd8\xff"
_SIGNATURE_WEBP_RIFF = b"RIFF"

MAX_ZIP_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000


def _valider_zip_ooxml(contenu: bytes, extension: str) -> None:
    if not zipfile.is_zipfile(BytesIO(contenu)):
        raise ValueError("Le fichier bureautique n'est pas un conteneur OOXML valide.")
    try:
        with zipfile.ZipFile(BytesIO(contenu)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError("Le fichier bureautique contient trop d'elements.")
            total = 0
            for info in infos:
                nom = info.filename.replace("\\", "/")
                if nom.startswith("/") or any(part == ".." for part in nom.split("/")):
                    raise ValueError("Le fichier bureautique contient un chemin interne invalide.")
                if info.flag_bits & 0x1:
                    raise ValueError("Les fichiers bureautiques chiffres ne sont pas acceptes.")
                total += max(0, info.file_size)
                if total > MAX_ZIP_UNCOMPRESSED:
                    raise ValueError("Le fichier bureautique est trop volumineux apres decompression.")
            noms = {info.filename for info in infos}
            if "[Content_Types].xml" not in noms:
                raise ValueError("Le fichier bureautique OOXML est incomplet.")
            racine = "word/document.xml" if extension == ".docx" else "ppt/presentation.xml"
            if racine not in noms:
                raise ValueError("Le fichier bureautique ne correspond pas a son extension.")
    except zipfile.BadZipFile as exc:
        raise ValueError("Le fichier bureautique est corrompu.") from exc


def _valider_image(contenu: bytes, extension: str) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contenu)) as image:
                image.verify()
                fmt = (image.format or "").lower()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError("Le contenu image n'est pas valide.") from exc

    attendus = {
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".png": "png",
        ".webp": "webp",
    }
    if fmt != attendus[extension]:
        raise ValueError("Le contenu reel de l'image ne correspond pas a son extension.")


def valider_upload(contenu: bytes, nom_fichier: str, taille_max: int, extensions_autorisees: set[str]) -> str:
    """Valide les octets et renvoie le MIME reel attendu par Storage."""
    if not contenu:
        raise ValueError("Le fichier semble vide.")
    if len(contenu) > taille_max:
        raise ValueError(f"Fichier trop volumineux (max {taille_max // (1024 * 1024)} Mo).")

    extension = Path(nom_fichier or "").suffix.lower()
    if extension not in extensions_autorisees:
        formats = ", ".join(sorted(extensions_autorisees))
        raise ValueError(f"Type de fichier non accepte. Formats autorises : {formats}.")

    if extension == ".pdf":
        if not contenu.startswith(_SIGNATURE_PDF):
            raise ValueError("Le contenu reel du fichier n'est pas un PDF valide.")
    elif extension in {".doc", ".ppt"}:
        if not contenu.startswith(_SIGNATURE_OLE):
            raise ValueError("Le contenu reel du fichier n'est pas un document Microsoft valide.")
    elif extension in {".docx", ".pptx"}:
        _valider_zip_ooxml(contenu, extension)
    elif extension in {".jpg", ".jpeg", ".png", ".webp"}:
        if extension == ".png" and not contenu.startswith(_SIGNATURE_PNG):
            raise ValueError("Le contenu reel du fichier n'est pas un PNG valide.")
        if extension in {".jpg", ".jpeg"} and not contenu.startswith(_SIGNATURE_JPEG):
            raise ValueError("Le contenu reel du fichier n'est pas un JPEG valide.")
        if extension == ".webp" and not (contenu.startswith(_SIGNATURE_WEBP_RIFF) and contenu[8:12] == b"WEBP"):
            raise ValueError("Le contenu reel du fichier n'est pas un WebP valide.")
        _valider_image(contenu, extension)

    return MIMES[extension]
