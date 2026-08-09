"""
Generation des jetons d'acces LiveKit (audio/video/partage d'ecran de la
classe virtuelle). Le jeton est genere cote serveur UNIQUEMENT apres que
la permission d'acces a la seance a deja ete verifiee independamment
(voir rejoindre_seance()/salle_virtuelle() dans classe_router.py) — ce
module ne fait AUCUNE verification d'autorisation lui-meme, il fait
juste confiance a l'appelant de ne l'invoquer qu'apres coup. La cle et le
secret API ne quittent jamais le serveur : seul le jeton signe (JWT), qui
encode deja la salle et les permissions precises (y compris QUELLES
sources l'utilisateur peut publier — camera/micro pour tous, partage
d'ecran pour le professeur/admin uniquement), est envoye au navigateur.
"""
from datetime import timedelta

from livekit import api

from .config import parametres


class LiveKitNonConfigure(RuntimeError):
    """Levee si LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET ne
    sont pas toutes definies. Permet d'afficher un message clair a
    l'utilisateur plutot qu'une 500 brute si la classe virtuelle est
    utilisee avant d'etre configuree."""


def livekit_configure() -> bool:
    return bool(parametres.livekit_url and parametres.livekit_api_key and parametres.livekit_api_secret)


def generer_jeton_salle(nom_salle: str, utilisateur_id: int, nom_affiche: str, peut_publier: bool, peut_partager_ecran: bool) -> str:
    """Genere un jeton JWT signe, valable 4h, limite a CETTE salle et a
    CET utilisateur precis.

    peut_publier=True (tout participant autorise a rejoindre) permet de
    publier camera/micro. peut_partager_ecran=True (professeur/admin
    uniquement) ajoute la source ecran — un etudiant ne peut PAS
    partager son ecran meme s'il bidouille le JS cote client, puisque
    c'est LiveKit lui-meme qui refuse la publication d'une source non
    listee dans le jeton signe (verification serveur, pas juste un
    bouton cache)."""
    if not livekit_configure():
        raise LiveKitNonConfigure(
            "LiveKit n'est pas configure sur ce serveur (LIVEKIT_URL / "
            "LIVEKIT_API_KEY / LIVEKIT_API_SECRET manquantes)."
        )

    sources_autorisees = ["camera", "microphone"]
    if peut_partager_ecran:
        sources_autorisees.append("screen_share")

    grants = api.VideoGrants(
        room_join=True,
        room=nom_salle,
        can_publish=peut_publier,
        can_publish_sources=sources_autorisees if peut_publier else None,
        can_subscribe=True,
        can_publish_data=True,  # chat + evenements du tableau blanc
    )

    jeton = (
        api.AccessToken(parametres.livekit_api_key, parametres.livekit_api_secret)
        .with_identity(str(utilisateur_id))
        .with_name(nom_affiche)
        .with_grants(grants)
        .with_ttl(timedelta(hours=4))
        .to_jwt()
    )
    return jeton
