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


def _client_serveur() -> api.LiveKitAPI:
    """Client d'API serveur LiveKit (mute/expulsion/liste des participants) --
    distinct de AccessToken ci-dessus, qui ne fait que SIGNER un jeton sans
    jamais parler au serveur LiveKit lui-meme. Meme URL que la connexion
    WebSocket cote navigateur (LIVEKIT_URL, wss://...) : le SDK serveur
    l'accepte telle quelle pour ses appels HTTP, pas besoin de la reecrire
    en https://. A utiliser avec `async with` (ferme la session HTTP)."""
    if not livekit_configure():
        raise LiveKitNonConfigure(
            "LiveKit n'est pas configure sur ce serveur (LIVEKIT_URL / "
            "LIVEKIT_API_KEY / LIVEKIT_API_SECRET manquantes)."
        )
    return api.LiveKitAPI(parametres.livekit_url, parametres.livekit_api_key, parametres.livekit_api_secret)


async def muter_micro_participant(nom_salle: str, identite_participant: str) -> bool:
    """Coupe le micro d'un participant precis, cote serveur (pas juste un
    bouton cache cote client — meme principe de confiance que le jeton
    d'acces : c'est LiveKit qui applique la coupure, pas le navigateur du
    participant qui pourrait choisir de l'ignorer).

    Retourne False si le participant n'a pas (ou plus) de piste micro
    publiee -- deja parti, deja coupe, ou jamais active son micro. Ce
    n'est pas une erreur : l'appelant peut l'ignorer ou l'afficher comme
    "rien a couper", selon le besoin."""
    async with _client_serveur() as lk:
        participants = await lk.room.list_participants(api.ListParticipantsRequest(room=nom_salle))
        cible = next((p for p in participants.participants if p.identity == identite_participant), None)
        if not cible:
            return False
        piste_micro = next((t for t in cible.tracks if t.type == api.TrackType.AUDIO), None)
        if not piste_micro:
            return False
        await lk.room.mute_published_track(api.MuteRoomTrackRequest(
            room=nom_salle, identity=identite_participant, track_sid=piste_micro.sid, muted=True,
        ))
        return True


async def expulser_participant(nom_salle: str, identite_participant: str) -> None:
    """Retire immediatement un participant de la salle LiveKit (sa
    connexion WebRTC est coupee cote serveur). N'empeche pas de rejoindre
    a nouveau -- si un blocage plus durable est necessaire, il doit venir
    de la verification d'acces a la seance (cote application), pas d'ici.

    Ne leve pas d'erreur si le participant n'est deja plus dans la salle
    (parti entre-temps) : LiveKit renvoie une erreur "not found" dans ce
    cas, capturee et ignoree ici puisque le resultat recherche par
    l'appelant (ce participant n'est plus dans la salle) est deja acquis."""
    async with _client_serveur() as lk:
        try:
            await lk.room.remove_participant(api.RoomParticipantIdentity(room=nom_salle, identity=identite_participant))
        except Exception as erreur:
            if "not found" not in str(erreur).lower():
                raise


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
