"""
Gestionnaire de connexions WebSocket pour les cercles d'etude : garde en
memoire, par cercle, la liste des connexions actives (avec l'identite de
l'utilisateur derriere chacune, pour la liste des presents) et diffuse
chaque nouveau message ou changement de presence a tout le monde present
dans ce meme cercle.

TODO (uniquement si plusieurs workers/instances un jour) : ce dict est en
memoire locale au process Python. Avec un seul worker uvicorn (le mode par
defaut, largement suffisant pour ce public), c'est parfait. Pour scaler
horizontalement (plusieurs workers ou plusieurs machines), il faudrait un
pub/sub partage entre process pour diffuser les messages — par exemple
Supabase Realtime en ecoutant les insertions sur la table message_cercle
(deja postgres si DATABASE_URL pointe vers Supabase), ou Redis pub/sub.
"""
from collections import defaultdict
from typing import Dict, List

from fastapi import WebSocket


class GestionnaireConnexions:
    def __init__(self) -> None:
        # Un dict {websocket: {"utilisateur_id":, "nom":}} par cercle,
        # plutot qu'une simple liste — necessaire pour pouvoir calculer
        # qui est present (un meme utilisateur peut avoir plusieurs
        # connexions ouvertes, ex. deux onglets, d'ou la dedup par
        # utilisateur_id dans utilisateurs_actifs()).
        self.connexions_par_cercle: Dict[int, Dict[WebSocket, dict]] = defaultdict(dict)

    async def connecter(self, cercle_id: int, websocket: WebSocket, utilisateur_id: int, nom: str) -> None:
        await websocket.accept()
        self.connexions_par_cercle[cercle_id][websocket] = {"utilisateur_id": utilisateur_id, "nom": nom}

    def deconnecter(self, cercle_id: int, websocket: WebSocket) -> None:
        self.connexions_par_cercle.get(cercle_id, {}).pop(websocket, None)

    def utilisateurs_actifs(self, cercle_id: int) -> List[dict]:
        """Liste des utilisateurs distincts actuellement connectes a ce
        cercle (deduplique par utilisateur_id, au cas ou quelqu'un a
        plusieurs onglets ouverts en meme temps)."""
        vus: Dict[int, str] = {}
        for info in self.connexions_par_cercle.get(cercle_id, {}).values():
            vus[info["utilisateur_id"]] = info["nom"]
        return [{"utilisateur_id": uid, "nom": nom} for uid, nom in vus.items()]

    async def diffuser(self, cercle_id: int, donnees: dict) -> None:
        connexions_mortes = []
        for connexion in list(self.connexions_par_cercle.get(cercle_id, {}).keys()):
            try:
                await connexion.send_json(donnees)
            except Exception:
                connexions_mortes.append(connexion)
        for connexion in connexions_mortes:
            self.deconnecter(cercle_id, connexion)

    async def diffuser_presence(self, cercle_id: int) -> None:
        """A appeler apres chaque connexion/deconnexion : renvoie la liste
        complete des presents a tout le monde (plus simple et plus robuste
        a maintenir cote client qu'une diffusion incrementale
        join/leave — le client remplace juste sa liste affichee)."""
        await self.diffuser(cercle_id, {"type": "presence", "utilisateurs": self.utilisateurs_actifs(cercle_id)})


gestionnaire = GestionnaireConnexions()
