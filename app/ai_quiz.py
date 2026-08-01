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
                    "description": (
                        "Liste des questions du quiz. Genere EXACTEMENT le "
                        "nombre de questions demande dans la consigne — "
                        "aucune limite de taille n'est imposee sur cette "
                        "liste elle-meme (la contrainte 3-5 plus bas ne "
                        "concerne QUE le nombre de choix de reponse a "
                        "l'INTERIEUR de chaque question, pas le nombre de "
                        "questions)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "choix": {
                                "type": "array",
                                "description": (
                                    "Options de reponse pour CETTE question "
                                    "uniquement (4 recommande). Sans lien "
                                    "avec le nombre total de questions du quiz."
                                ),
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


def _generer_completion_avec_reessai(client: Groq, messages_par_essai: List[str], max_completion_tokens: int):
    """Appelle Groq avec le tool-calling force, et reessaie UNE fois avec
    une consigne renforcee si le modele n'appelle pas l'outil du premier
    coup (deja observe : un modele peut, a tort, croire qu'une contrainte
    imbriquee du schema — ex. 3 a 5 choix par question — s'applique au
    nombre de questions demande, et refuser d'appeler l'outil en
    expliquant pourquoi en texte libre au lieu de generer le quiz)."""
    derniere_erreur = None
    for contenu in messages_par_essai:
        try:
            completion = client.chat.completions.create(
                model=parametres.groq_model,
                max_completion_tokens=max_completion_tokens,
                tools=[OUTIL_QUIZ],
                tool_choice={"type": "function", "function": {"name": "soumettre_quiz"}},
                messages=[{"role": "user", "content": contenu}],
            )
        except Exception as erreur:
            derniere_erreur = erreur
            continue

        if completion.choices[0].message.tool_calls:
            return completion, None

    return None, derniere_erreur


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

    consigne_base = (
        f"Voici le contenu d'un support de cours universitaire "
        f"(Universite de Toamasina). Genere exactement {nb_questions} "
        f"questions de revision a choix multiples en francais : varie "
        f"les niveaux (comprehension, application, pas seulement de la "
        f"restitution litterale du texte), 4 choix plausibles par "
        f"question, une seule bonne reponse, et une explication courte. "
        f"Utilise l'outil fourni pour repondre.\n\n---\n{texte_tronque}\n---"
    )
    consigne_renforcee = (
        f"{consigne_base}\n\nRappel important : le nombre de questions a "
        f"generer est EXACTEMENT {nb_questions} — la contrainte de 3 a 5 "
        f"elements dans le schema de l'outil concerne uniquement le "
        f"nombre de choix de reponse A L'INTERIEUR de chaque question, "
        f"pas le nombre de questions. Appelle l'outil 'soumettre_quiz' "
        f"directement, sans poser de question de clarification."
    )

    completion, erreur = _generer_completion_avec_reessai(
        client, [consigne_base, consigne_renforcee], max_completion_tokens=2048
    )

    if completion is None:
        detail = f"Erreur API : {erreur}" if erreur else "Le modele n'a pas repondu au format attendu apres deux tentatives — reessayez dans un instant."
        return _quiz_erreur("La generation du quiz a echoue.", detail)

    return _extraire_questions(completion)


def generer_quiz_par_theme(matiere: str, niveau: str, difficulte: str, nb_questions: int = 5) -> List[Dict]:
    """
    Genere un quiz a choix multiples directement a partir d'un theme choisi
    par l'etudiant (matiere/niveau/difficulte), sans document source. Meme
    schema structure que generer_quiz_depuis_texte, pour que le reste de
    l'app (correction, affichage) n'ait pas a distinguer les deux cas.
    """
    try:
        client = _obtenir_client()
    except RuntimeError as erreur:
        return _quiz_erreur("Generation de quiz IA non configuree.", str(erreur))

    consigne_base = (
        f"Tu es un professeur a l'Universite de Toamasina (Madagascar). "
        f"Genere exactement {nb_questions} questions de revision a choix "
        f"multiples en francais sur la matiere '{matiere}', pour un niveau "
        f"{niveau}, avec une difficulte {difficulte}. Varie les niveaux "
        f"cognitifs (comprehension, application, pas seulement de la "
        f"restitution), 4 choix plausibles par question, une seule bonne "
        f"reponse, et une explication courte pour chaque. Utilise l'outil "
        f"fourni pour repondre."
    )
    consigne_renforcee = (
        f"{consigne_base}\n\nRappel important : le nombre de questions a "
        f"generer est EXACTEMENT {nb_questions}, sans exception — la "
        f"contrainte de 3 a 5 elements dans le schema de l'outil concerne "
        f"uniquement le nombre de choix de reponse A L'INTERIEUR de chaque "
        f"question, pas le nombre de questions. Appelle l'outil "
        f"'soumettre_quiz' directement, sans poser de question de "
        f"clarification."
    )

    completion, erreur = _generer_completion_avec_reessai(
        client, [consigne_base, consigne_renforcee], max_completion_tokens=2048
    )

    if completion is None:
        detail = f"Erreur API : {erreur}" if erreur else "Le modele n'a pas repondu au format attendu apres deux tentatives — reessayez dans un instant."
        return _quiz_erreur("La generation du quiz a echoue.", detail)

    return _extraire_questions(completion)


def generer_theme_reflexion(matiere: Optional[str] = None) -> Dict[str, str]:
    """
    Genere un theme de reflexion ouvert (pas de QCM) a debattre, pour muscler
    l'esprit critique — dans l'esprit d'une question du jour. Renvoie un
    dict {"theme": ..., "amorce": ...} : le sujet et 2-3 phrases pour
    lancer la reflexion (pas une reponse toute faite, sinon ca tue le
    debat)."""
    try:
        client = _obtenir_client()
    except RuntimeError as erreur:
        return {"theme": "Generation indisponible.", "amorce": str(erreur)}

    contexte_matiere = f" en lien avec '{matiere}'" if matiere else ""
    outil_reflexion = {
        "type": "function",
        "function": {
            "name": "proposer_theme",
            "description": "Propose un theme de reflexion ouvert a debattre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "description": "La question ou affirmation a debattre, formulee de facon engageante."},
                    "amorce": {"type": "string", "description": "2 a 3 phrases qui posent les enjeux ou tensions du sujet, sans donner de reponse toute faite."},
                },
                "required": ["theme", "amorce"],
            },
        },
    }

    try:
        completion = client.chat.completions.create(
            model=parametres.groq_model,
            max_completion_tokens=512,
            tools=[outil_reflexion],
            tool_choice={"type": "function", "function": {"name": "proposer_theme"}},
            messages=[{
                "role": "user",
                "content": (
                    f"Propose un theme de reflexion ouvert{contexte_matiere}, destine "
                    f"a des etudiants malgaches, pour muscler leur esprit critique et "
                    f"les faire debattre entre eux (dans un cercle d'etude par "
                    f"exemple). Ni trivial ni trop academique : un sujet qui suscite "
                    f"de vrais points de vue differents. Utilise l'outil fourni."
                ),
            }],
        )
    except Exception as erreur:
        return {"theme": "La generation a echoue.", "amorce": f"Erreur API : {erreur}"}

    message = completion.choices[0].message
    if message.tool_calls:
        try:
            arguments = json.loads(message.tool_calls[0].function.arguments)
            if arguments.get("theme"):
                return {"theme": arguments["theme"], "amorce": arguments.get("amorce", "")}
        except (json.JSONDecodeError, AttributeError):
            pass

    return {"theme": "La generation a echoue.", "amorce": "Reessayez dans un instant."}


def _extraire_questions(completion) -> List[Dict]:
    """Factorise l'extraction du tool-call, partagee par les deux modes de
    generation de quiz (par document et par theme)."""
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
