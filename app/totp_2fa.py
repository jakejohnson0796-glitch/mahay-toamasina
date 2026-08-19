"""
Double authentification (2FA) par TOTP — Time-based One-Time Password,
le standard utilise par Google Authenticator, Microsoft Authenticator,
Authy, etc. Choix delibere plutot que la 2FA par SMS : le SMS coute de
l'argent a chaque envoi (passerelle type Twilio, particulierement cher
sur les numeros malgaches) alors que le TOTP est calcule localement sur
le telephone de l'utilisateur, sans aucun service tiers ni cout recurrent.

Rien dans ce module n'appelle de service externe : tout est calcule en
memoire (bibliotheques pyotp/qrcode, standard ouvert RFC 6238).
"""
import base64
import io
import secrets
import string

import pyotp
import qrcode

from .auth import hacher_mot_de_passe, verifier_mot_de_passe


def generer_secret_totp() -> str:
    return pyotp.random_base32()


def generer_qrcode_data_uri(secret: str, telephone: str) -> str:
    """Genere le QR code d'activation en memoire (jamais ecrit sur
    disque) et le renvoie sous forme de data URI directement utilisable
    dans un <img src="...">."""
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=telephone, issuer_name="Gasy Mahay Toamasina")
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encode = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encode}"


def verifier_code_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    # valid_window=1 tolere un decalage d'horloge de +/- 30s entre le
    # telephone de l'utilisateur et le serveur — evite des faux refus
    # agacants sans affaiblir reellement la securite (fenetre de 90s
    # totale, largement dans les pratiques usuelles de ce protocole).
    return totp.verify(code.strip(), valid_window=1)


def generer_codes_secours(nombre: int = 8) -> list[str]:
    """Codes de secours a usage unique (ex: 'XXXX-XXXX'), a usage si le
    telephone de l'utilisateur est perdu/casse. Generes en clair une
    seule fois pour etre affiches a l'utilisateur — jamais reconsultables
    ensuite, seul leur hash est conserve (voir hacher_code_secours)."""
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(nombre):
        partie1 = "".join(secrets.choice(alphabet) for _ in range(4))
        partie2 = "".join(secrets.choice(alphabet) for _ in range(4))
        codes.append(f"{partie1}-{partie2}")
    return codes


def hacher_code_secours(code: str) -> str:
    # Reutilise le hachage de mot de passe existant (bcrypt via passlib,
    # deja audite/en place) plutot que d'introduire un second mecanisme
    # de hachage a maintenir separement.
    return hacher_mot_de_passe(code.strip().upper())


def verifier_code_secours(code: str, code_hash: str) -> bool:
    return verifier_mot_de_passe(code.strip().upper(), code_hash)
