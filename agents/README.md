# Worker de transcription Mahay

Ce worker est **séparé du serveur Web Mahay** et ne démarre pas automatiquement avec l'application.
Il doit être déployé comme un processus LiveKit Agents distinct, disponible avant d'activer la
transcription dans une séance.

## Variables privées requises

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY`

Le worker s'enregistre sous le nom `mahay-transcription`. Le serveur Web doit recevoir
`LIVEKIT_TRANSCRIPTION_AGENT_NAME=mahay-transcription` après que le worker est prêt.

## Installation et lancement

Depuis la racine du dépôt, dans un environnement Python isolé :

```bash
python -m pip install -r agents/requirements.txt
python agents/mahay_transcription.py start
```

Ne définis jamais ces secrets dans le navigateur, dans le dépôt ou dans une variable publique.
N'ajoute pas ce worker au processus Web principal : il doit pouvoir être démarré, surveillé et
arrêté indépendamment. Il consomme les ressources du fournisseur LiveKit et du service STT.

## Confidentialité et règles de fonctionnement

- Aucun audio ni aucune vidéo n'est enregistré par ce worker ; il fait uniquement de la
  reconnaissance vocale et publie les segments texte LiveKit.
- Le serveur Mahay n'envoie le dispatch que si tous les participants actuellement connectés
  ont explicitement consenti pour cette séance.
- Un participant qui rejoint pendant une transcription active doit choisir d'accepter ou de
  refuser avant d'entrer dans la salle. Un refus arrête le dispatch actif.
- Le professeur peut arrêter la transcription à tout moment.
- Les segments affichés en direct ne sont pas persistés automatiquement. Le professeur doit
  arrêter l'agent puis cliquer explicitement sur « Enregistrer le compte rendu ».
- Le résumé IA est une étape distincte, déclenchée par le professeur après l'enregistrement.
- Le texte sauvegardé doit être supprimé conformément aux règles de conservation de Mahay et
  aux demandes applicables des participants.

La fonctionnalité reste désactivée tant que le worker n'est pas déployé et que
`LIVEKIT_TRANSCRIPTION_AGENT_NAME` n'est pas défini côté serveur Web.
