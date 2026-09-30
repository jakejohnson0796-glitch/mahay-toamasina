import io

from PIL import Image
from fastapi import UploadFile

from app import storage


def _png_bytes(couleur=(220, 30, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (3, 3), couleur).save(buf, format="PNG")
    return buf.getvalue()


def test_sauvegarder_avatar_valide_et_remplace_ancien_fichier(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DOSSIER_UPLOADS_LOCAL", tmp_path)
    monkeypatch.setattr(storage, "stockage_distant_actif", lambda: False)

    ancien = tmp_path / "avatar_42.jpg"
    ancien.write_bytes(b"ancienne-photo")

    nouveau = UploadFile(file=io.BytesIO(_png_bytes()), filename="profil.png")
    chemin = storage.sauvegarder_avatar(nouveau, 42, ancien_chemin=str(ancien))

    assert chemin == str(tmp_path / "avatar_42.png")
    assert not ancien.exists()
    assert (tmp_path / "avatar_42.png").read_bytes() == _png_bytes()

    remplacement = UploadFile(file=io.BytesIO(_png_bytes((20, 80, 200))), filename="profil.png")
    chemin2 = storage.sauvegarder_avatar(replacement, 42, ancien_chemin=chemin)

    assert chemin2 == chemin
    assert (tmp_path / "avatar_42.png").read_bytes() == _png_bytes((20, 80, 200))
