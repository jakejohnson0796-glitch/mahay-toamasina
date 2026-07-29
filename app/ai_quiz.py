"""
Generation de quiz par IA a partir du texte d'un document, via l'API Groq.

Pourquoi Groq plutot qu'un autre fournisseur : cle API gratuite sans carte
bancaire (console.groq.com), limites larges pour ce cas d'usage (30
requetes/minute, 1000/jour sur le modele utilise ici) et inference tres
rapide. Largement suffisant pour generer des quiz a la demande sur une
plateforme etudiante — pas besoin de payer pour demarrer.

Comme pour la version precedente, on force une sortie structuree via le
"tool calling" de l'API (schema JSON strict) plutot que de parser du texte
libre : plus fiable qu'un json.loads() hasardeux.
"""
import json
from typing import Dict, List, Optional

from groq import Groq

from .config import parametres

_client: Optional[Groq] = None


def _obtenir_client() -> Groq:
    global _client
    if _client is None:
        if not parametres.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY manquante : creez une cle gratuite sur "
                "https://console.groq.com (aucune carte bancaire requise) "
                "et ajoutez-la dans le fichier .env du serveur."
            )
        _client = Groq(api_key=parametres.groq_api_key)
    return _client


OUTIL_QUIZ = {
    "type": "function",
    "function": {
        "name": "soumettre_quiz",
        "description": "Enregistre un quiz de revision structure genere a partir d'un cours.",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "choix": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 3,
                                "maxItems": 5,
                            },
                            "index_bonne_reponse": {
                                "type": "integer",
                                "description": "Index (base 0) du choix correct dans le tableau 'choix'.",
                            },
                            "explication": {
                                "type": "string",
                                "description": "Courte explication (1-2 phrases) de la bonne reponse.",
                            },
                        },
                        "required": ["question", "choix", "index_bonne_reponse", "explication"],
                    },
                }
            },
            "required": ["questions"],
        },
    },
}


def _quiz_erreur(message: str, detail: str) -> List[Dict]:
    """Renvoie un item de quiz explicite plutot que de faire planter la
    page /documents/{id}/quiz si l'extraction ou l'API a echoue."""
    return [{
        "question": message,
        "choix": [detail],
        "index_bonne_reponse": 0,
        "explication": "",
    }]


def generer_quiz_depuis_texte(texte_document: str, nb_questions: int = 5) -> List[Dict]:
    """
    Envoie le texte du document a Groq et recupere un quiz a choix
    multiples structure (liste de dicts : question, choix, index_bonne_reponse,
    explication).
    """
    texte_document = (texte_document or "").strip()
    if len(texte_document) < 40:
        return _quiz_erreur(
            "Impossible de generer un quiz pour ce document.",
            "Le texte extrait est trop court ou vide — verifiez que c'est un "
            "PDF avec du texte selectionnable, ou que le scan est net (OCR).",
        )

    try:
        client = _obtenir_client()
    except RuntimeError as erreur:
        return _quiz_erreur("Generation de quiz IA non configuree.", str(erreur))

    # On tronque pour rester dans une taille de contexte raisonnable (et
    # rester large sous les limites du palier gratuit) meme sur un gros
    # support de cours.
    texte_tronque = texte_document[:12000]

    try:
        completion = client.chat.completions.create(
            model=parametres.groq_model,
            max_completion_tokens=2048,
            tools=[OUTIL_QUIZ],
            tool_choice={"type": "function", "function": {"name": "soumettre_quiz"}},
            messages=[{
                "role": "user",
                "content": (
                    f"Voici le contenu d'un support de cours universitaire "
                    f"(Universite de Toamasina). Genere exactement {nb_questions} "
                    f"questions de revision a choix multiples en francais : varie "
                    f"les niveaux (comprehension, application, pas seulement de la "
                    f"restitution litterale du texte), 4 choix plausibles par "
                    f"question, une seule bonne reponse, et une explication courte. "
                    f"Utilise l'outil fourni pour repondre.\n\n---\n{texte_tronque}\n---"
                ),
            }],
        )
    except Exception as erreur:
        return _quiz_erreur("La generation du quiz a echoue.", f"Erreur API : {erreur}")

    message = completion.choices[0].message
    if message.tool_calls:
        try:
            arguments = json.loads(message.tool_calls[0].function.arguments)
            questions = arguments.get("questions") or []
            if questions:
                return questions
        except (json.JSONDecodeError, AttributeError):
            pass

    return _quiz_erreur(
        "La generation a echoue.",
        "Aucune reponse structuree n'a ete recue de l'API — reessayez dans un instant.",
    )
