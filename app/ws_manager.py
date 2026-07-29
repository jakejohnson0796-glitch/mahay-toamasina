"""
Gestionnaire de connexions WebSocket pour les cercles d'etude : garde en
memoire, par cercle, la liste des connexions actives et diffuse chaque
nouveau message a tout le monde present dans ce meme cercle.

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
        self.connexions_par_cercle: Dict[int, List[WebSocket]] = defaultdict(list)

    async def connecter(self, cercle_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connexions_par_cercle[cercle_id].append(websocket)

    def deconnecter(self, cercle_id: int, websocket: WebSocket) -> None:
        connexions = self.connexions_par_cercle.get(cercle_id)
        if connexions and websocket in connexions:
            connexions.remove(websocket)

    async def diffuser(self, cercle_id: int, donnees: dict) -> None:
        connexions_mortes = []
        for connexion in self.connexions_par_cercle.get(cercle_id, []):
            try:
                await connexion.send_json(donnees)
            except Exception:
                connexions_mortes.append(connexion)
        for connexion in connexions_mortes:
            self.deconnecter(cercle_id, connexion)


gestionnaire = GestionnaireConnexions()
