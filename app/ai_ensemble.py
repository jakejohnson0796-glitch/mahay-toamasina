"""Orchestrateur multi-modeles pour les fonctions pedagogiques de Gasy Mahay.

Pipeline volontairement deterministe :
    generateur -> critiques independantes -> arbitre -> sortie unique.

Les fournisseurs secondaires restent optionnels. Le systeme continue avec
Groq seul si GEMINI_API_KEY est absente ou si un fournisseur secondaire
est temporairement indisponible.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from groq import Groq

from .config import parametres
from .json_latex import charger_json_ia
from .ia_transport import (
    PROMPT_TRANSPORT_SANS_ANTISLASH,
    normaliser_structure_quiz,
    normaliser_structure_tuteur,
)

logger = logging.getLogger(__name__)

# MODIF : contrat commun de rendu LaTeX/Markdown pour tous les modèles de contrôle.
REGLES_FORMAT = PROMPT_TRANSPORT_SANS_ANTISLASH
# MODIF : suffixe commun ajouté à chaque prompt de critique/arbitrage.
def _suffixe_format_prompt(quiz: bool = False) -> str:
    if quiz:
        return PROMPT_TRANSPORT_SANS_ANTISLASH
    return "\n\n" + PROMPT_TRANSPORT_SANS_ANTISLASH

# Coupe-circuit court pour eviter de refaire plusieurs requetes Gemini
# lorsque le fournisseur renvoie temporairement des 429/5xx.
_GEMINI_COOLDOWN_UNTIL = 0.0
_GEMINI_TRANSIENT_FAILURES = 0
_GEMINI_COOLDOWN_SECONDS = 60.0


def _groq_client() -> Optional[Groq]:
    if not parametres.groq_api_key:
        return None
    return Groq(api_key=parametres.groq_api_key)


def _gemini_enabled() -> bool:
    return bool(parametres.gemini_api_key and parametres.ai_ensemble_use_gemini)


def _extract_tool_json(completion: Any) -> Optional[Dict[str, Any]]:
    try:
        calls = completion.choices[0].message.tool_calls
        if not calls:
            return None
        return charger_json_ia(calls[0].function.arguments)
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
        return None


def _groq_structured_tool(
    *,
    model: str,
    tool: Dict[str, Any],
    tool_name: str,
    prompt: str,
    max_completion_tokens: int = 2048,
    reasoning_effort: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    client = _groq_client()
    if client is None:
        return None

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_completion_tokens": max_completion_tokens,
        "temperature": 0.2,
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "messages": [{"role": "user", "content": prompt}],
    }
    if reasoning_effort and model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = reasoning_effort

    for attempt in range(1, 3):
        try:
            if attempt == 2:
                kwargs["temperature"] = 0.0
                kwargs["messages"] = [{
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        "IMPORTANT : ta sortie doit obligatoirement appeler l'outil "
                        f"'{tool_name}' maintenant. Ne reponds pas en texte libre."
                    ),
                }]
            completion = client.chat.completions.create(**kwargs)
            parsed = _extract_tool_json(completion)
            if parsed is not None:
                return parsed
            if attempt == 1:
                time.sleep(0.3)
                continue
            logger.warning(
                "Modele Groq %s n'a pas produit l'appel d'outil attendu.",
                model,
            )
            return None
        except Exception as erreur:
            if attempt < 2:
                time.sleep(0.5)
                continue
            logger.warning(
                "Modele Groq %s indisponible apres %s tentatives: %s",
                model,
                attempt,
                erreur,
            )
            return None


def _gemini_json(prompt: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    global _GEMINI_COOLDOWN_UNTIL, _GEMINI_TRANSIENT_FAILURES

    if not _gemini_enabled():
        return None
    if time.time() < _GEMINI_COOLDOWN_UNTIL:
        return None

    # Gemini 3.8 Flash est toujours disponible via generateContent, mais
    # Google recommande désormais l'Interactions API pour les nouveaux
    # workflows, notamment les structured outputs. On utilise cette API
    # ici pour éviter les incompatibilités de contrat entre anciennes et
    # nouvelles configurations responseSchema/generationConfig.
    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    payload = {
        "model": parametres.gemini_model,
        "input": prompt,
        "store": False,
        "response_format": [
            {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            }
        ],
    }
    headers = {
        "x-goog-api-key": parametres.gemini_api_key,
        "Content-Type": "application/json",
    }
    retryable_statuses = {429, 500, 502, 503, 504}

    try:
        with httpx.Client(timeout=45.0) as client:
            for attempt in range(1, 4):
                try:
                    response = client.post(
                        url,
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code in retryable_statuses and attempt < 3:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = float(retry_after) if retry_after else 1.5 * (2 ** (attempt - 1))
                        except (TypeError, ValueError):
                            delay = 1.5 * (2 ** (attempt - 1))
                        time.sleep(min(max(delay, 0.5), 8.0))
                        continue

                    response.raise_for_status()
                    data = response.json()
                    _GEMINI_TRANSIENT_FAILURES = 0
                    _GEMINI_COOLDOWN_UNTIL = 0.0

                    text = data.get("output_text", "")
                    if not text:
                        for step in data.get("steps", []):
                            if step.get("type") != "model_output":
                                continue
                            for item in step.get("content", []):
                                if item.get("type") == "text" and item.get("text"):
                                    text = item["text"]
                                    break
                            if text:
                                break

                    return charger_json_ia(text) if text else None

                except httpx.RequestError as erreur:
                    if attempt >= 3:
                        _GEMINI_TRANSIENT_FAILURES += 1
                        _GEMINI_COOLDOWN_UNTIL = time.time() + _GEMINI_COOLDOWN_SECONDS
                        logger.warning(
                            "Modele Gemini %s indisponible apres %s tentatives (%s). "
                            "Pause Gemini de %.0fs.",
                            parametres.gemini_model,
                            attempt,
                            type(erreur).__name__,
                            _GEMINI_COOLDOWN_SECONDS,
                        )
                        return None
                    time.sleep(min(1.5 * (2 ** (attempt - 1)), 8.0))

                except httpx.HTTPStatusError as erreur:
                    status = erreur.response.status_code
                    if status in retryable_statuses:
                        _GEMINI_TRANSIENT_FAILURES += 1
                        _GEMINI_COOLDOWN_UNTIL = time.time() + _GEMINI_COOLDOWN_SECONDS
                        logger.warning(
                            "Modele Gemini %s indisponible: HTTP %s. "
                            "Pause Gemini de %.0fs avant nouvelle tentative.",
                            parametres.gemini_model,
                            status,
                            _GEMINI_COOLDOWN_SECONDS,
                        )
                    else:
                        detail = (erreur.response.text or "").replace("\n", " ")[:500]
                        logger.warning(
                            "Modele Gemini %s indisponible: HTTP %s — %s",
                            parametres.gemini_model,
                            status,
                            detail,
                        )
                    return None
    except Exception as erreur:
        logger.warning(
            "Erreur inattendue Gemini %s: %s",
            parametres.gemini_model,
            type(erreur).__name__,
        )
        return None


OUTIL_CRITIQUE_QUIZ = {
    "type": "function",
    "function": {
        "name": "critiquer_quiz",
        "description": "Analyse un quiz existant et propose des corrections uniquement si necessaire.",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "choix": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5, "uniqueItems": True},
                            "index_bonne_reponse": {"type": "integer"},
                            "explication": {"type": "string"},
                            "notion": {"type": "string"},
                        },
                        "required": [
                            "question",
                            "choix",
                            "index_bonne_reponse",
                            "explication",
                            "notion",
                        ],
                    },
                },
                "confiant": {"type": "boolean"},
                "problemes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["questions", "confiant", "problemes"],
        },
    },
}


def critiquer_quiz_groq(
    questions: List[Dict[str, Any]],
    matiere: str,
    niveau: str,
) -> Optional[Dict[str, Any]]:
    prompt = (
        "Tu es le deuxieme professeur-verificateur d'un moteur de quiz. "
        "Ne genere pas un nouveau quiz. Analyse celui-ci question par question. "
        "Recalcule ou reverifie chaque resultat avant de valider la bonne reponse. "
        "Controle obligatoirement : index_bonne_reponse -> choix réellement correct, "
        "une seule bonne réponse, explication cohérente avec ce choix, absence de "
        "contradiction interne, distracteurs plausibles et distincts. Pour les "
        "mathématiques, vérifie calculs, signes, matrices, fractions, puissances, "
        "équations et dimensions ; pour la physique, vérifie formule, unités, "
        "signes, conversions et ordre de grandeur ; pour l'informatique, vérifie "
        "syntaxe, sémantique, complexité et résultat du code ; pour les autres "
        "matières, vérifie les faits et la logique. Une phrase comme « aucune des "
        "réponses proposées ne correspond », « il faut corriger les choix » ou "
        "« la bonne réponse est X » incompatible avec l'index est une erreur "
        "bloquante qui doit être corrigée. Corrige seulement ce qui doit l'être. "
        "Garde exactement le même nombre et le même ordre. "
        "Indique confiant=true seulement si tu ne vois aucun doute.\\n\\n"
        f"Matiere: {matiere}\\nNiveau: {niveau}\\n"
        f"{json.dumps(questions, ensure_ascii=False)}"
    )
    prompt += _suffixe_format_prompt(quiz=True)
    return _groq_structured_tool(
        model=parametres.groq_critic_model,
        tool=OUTIL_CRITIQUE_QUIZ,
        tool_name="critiquer_quiz",
        prompt=prompt,
        reasoning_effort="medium",
    )


GEMINI_QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "choix": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5, "uniqueItems": True},
                    "index_bonne_reponse": {"type": "integer"},
                    "explication": {"type": "string"},
                    "notion": {"type": "string"},
                },
                "required": [
                    "question",
                    "choix",
                    "index_bonne_reponse",
                    "explication",
                    "notion",
                ],
            },
        },
        "confiant": {"type": "boolean"},
        "problemes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["questions", "confiant", "problemes"],
}


def critiquer_quiz_gemini(
    questions: List[Dict[str, Any]],
    matiere: str,
    niveau: str,
) -> Optional[Dict[str, Any]]:
    prompt = (
        "Tu es un correcteur universitaire independant. Examine le quiz ci-dessous "
        "sans inventer de source externe. Avant de déclarer une question correcte, "
        "recalcule/reverifie son résultat et compare explicitement le résultat au "
        "choix indiqué par index_bonne_reponse. Vérifie ensuite que l'explication "
        "démontre exactement cette réponse et ne reconnait jamais que les options "
        "sont toutes fausses ou incomplètes. Vérifie calculs et matrices en maths, "
        "unités/formules/conversions en physique, syntaxe/sémantique/résultat en "
        "informatique, puis les faits et la logique dans les autres matières. "
        "Corrige toute incohérence trouvée. Retourne le même nombre de questions. "
        "ne modifie rien si tout est correct.\\n\\n"
        f"Matiere: {matiere}\\nNiveau: {niveau}\\n"
        f"{json.dumps(questions, ensure_ascii=False)}"
    )
    prompt += _suffixe_format_prompt(quiz=True)
    return _gemini_json(prompt, GEMINI_QUIZ_SCHEMA)


def arbitrer_quiz(
    original: List[Dict[str, Any]],
    critiques: List[Dict[str, Any]],
    matiere: str,
    niveau: str,
    outil_verification: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    synthese = json.dumps(critiques, ensure_ascii=False)
    prompt = (
        "Tu es l'arbitre final d'un systeme pedagogique multi-modeles. "
        "Tu dois produire UNE version finale du quiz. Le quiz original est "
        "la base. Deux correcteurs ont donne des avis independants. "
        "Conserve toute question correcte, mais recalcule toi-même les réponses "
        "avant de valider la sortie. L'index doit pointer vers le seul choix "
        "correct et l'explication doit prouver ce choix sans contradiction. "
        "Si une explication dit qu'aucune option ne convient, la question doit "
        "être réparée avant publication. Contrôle aussi les calculs/mesures en "
        "maths et physique, et le résultat/syntaxe/sémantique pour l'informatique. "
        "N'applique une correction que si elle est justifiée. Si les correcteurs "
        "divergent, tranche en t'appuyant sur la logique académique et le quiz "
        "original, sans inventer. Garde exactement le même nombre et le même ordre. "
        "Retourne le quiz final et confiant=true seulement quand les "
        "questions restantes sont suffisamment fiables.\\n\\n"
        f"Matiere: {matiere}\\nNiveau: {niveau}\\n"
        f"ORIGINAL:\\n{json.dumps(original, ensure_ascii=False)}\\n\\n"
        f"CRITIQUES:\\n{synthese}"
    )
    prompt += _suffixe_format_prompt(quiz=True)
    return _groq_structured_tool(
        model=parametres.groq_model,
        tool=outil_verification,
        tool_name="soumettre_verification",
        prompt=prompt,
        max_completion_tokens=8192,
        reasoning_effort="high",
    )


def ensemble_verification_quiz(
    questions: List[Dict[str, Any]],
    matiere: str,
    niveau: str,
    outil_verification: Dict[str, Any],
    validate,
    strategie: str = "standard",
) -> Tuple[List[Dict[str, Any]], bool, Dict[str, Any]]:
    """Fait collaborer les verificateurs avec un niveau de controle adaptatif.

    legere = Qwen seul ; standard/renforcee = Qwen + Gemini.
    L'arbitre n'est appele que lorsqu'un des critiques detecte un probleme
    ou manque de confiance.
    """
    if not parametres.ai_ensemble_enabled or not questions:
        return questions, False, {
            "models": [parametres.groq_model],
            "critics": [],
            "strategy": strategie,
        }

    critiques: List[Dict[str, Any]] = []
    qwen = critiquer_quiz_groq(questions, matiere, niveau)
    if qwen:
        critiques.append({"model": parametres.groq_critic_model, "avis": qwen})

    if strategie != "legere":
        gemini = critiquer_quiz_gemini(questions, matiere, niveau)
        if gemini:
            critiques.append({"model": parametres.gemini_model, "avis": gemini})

    if not critiques:
        return questions, False, {"models": [parametres.groq_model], "critics": [], "strategy": strategie}

    # Aucun correcteur n'a detecte de probleme : inutile de depenser un appel
    # supplementaire d'arbitrage.
    tous_confiants = all(item["avis"].get("confiant") is True for item in critiques)
    problemes = [
        p
        for item in critiques
        for p in (item["avis"].get("problemes") or [])
    ]
    if tous_confiants and not problemes and strategie != "renforcee":
        return questions, True, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
            "strategy": strategie,
        }

    arbitre = arbitrer_quiz(
        questions,
        critiques,
        matiere,
        niveau,
        outil_verification,
    )
    if not arbitre:
        # Si l'arbitre est indisponible, on garde le resultat du premier
        # critique seulement s'il respecte strictement le schema applicatif.
        for critique in critiques:
            candidat = normaliser_structure_quiz(critique["avis"].get("questions") or [])
            try:
                candidat = validate(candidat, expected_count=len(questions))
            except Exception:
                continue
            return candidat, critique["avis"].get("confiant") is True, {
                "models": [parametres.groq_model] + [x["model"] for x in critiques],
                "critics": critiques,
                "arbitration": "fallback_critic",
                "strategy": strategie,
            }
        return questions, False, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
            "arbitration": "original",
            "strategy": strategie,
        }

    candidat = normaliser_structure_quiz(arbitre.get("questions") or [])
    try:
        candidat = validate(candidat, expected_count=len(questions))
    except Exception:
        logger.warning("Arbitrage multi-modeles invalide, conservation du quiz original.")
        return questions, False, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
            "arbitration": "invalid",
            "strategy": strategie,
        }

    return candidat, arbitre.get("confiant") is True, {
        "models": [parametres.groq_model] + [x["model"] for x in critiques],
        "critics": critiques,
        "arbitration": "groq_arbiter",
        "strategy": strategie,
    }


OUTIL_TUTEUR_CRITIQUE = {
    "type": "function",
    "function": {
        "name": "critiquer_tuteur",
        "description": "Evalue une reponse de tuteur sans la remplacer.",
        "parameters": {
            "type": "object",
            "properties": {
                "confiant": {"type": "boolean"},
                "problemes": {"type": "array", "items": {"type": "string"}},
                "ameliorations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["confiant", "problemes", "ameliorations"],
        },
    },
}


def _critique_tuteur_groq(
    reponse: Dict[str, str],
    question: str,
    notion: Optional[str],
    matiere: Optional[str],
) -> Optional[Dict[str, Any]]:
    prompt = (
        "Evalue la reponse d'un tuteur universitaire comme un correcteur "
        "independant. Recalcule ou rederive les exemples et l'exercice avant de "
        "declarer la reponse correcte. Verifie obligatoirement que l'explication "
        "est exacte, que l'exemple est exact, que l'exercice est solvable, et que "
        "la correction resout exactement l'exercice donne sans changer les donnees. "
        "Pour les mathematiques et la physique, verifie calculs, signes, unites, "
        "dimensions, conversions, matrices, fractions, equations et ordre de grandeur. "
        "Pour l'informatique, verifie syntaxe, semantique, resultat du code et "
        "complexite quand elle est pertinente. Pour les autres matieres, verifie "
        "faits, logique et coherence interne. Signale aussi toute contradiction "
        "entre les quatre parties. Ne reecris pas la reponse. Retourne des "
        "problemes courts et des ameliorations concretes. "
        f"Question: {question}\\nNotion: {notion or '-'}\\nMatiere: {matiere or '-'}\\n"
        f"REPONSE:\\n{json.dumps(reponse, ensure_ascii=False)}"
    )
    prompt += _suffixe_format_prompt(quiz=False)
    return _groq_structured_tool(
        model=parametres.groq_critic_model,
        tool=OUTIL_TUTEUR_CRITIQUE,
        tool_name="critiquer_tuteur",
        prompt=prompt,
        reasoning_effort="medium",
    )


TUTEUR_GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "confiant": {"type": "boolean"},
        "problemes": {"type": "array", "items": {"type": "string"}},
        "ameliorations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["confiant", "problemes", "ameliorations"],
}


def _critique_tuteur_gemini(
    reponse: Dict[str, str],
    question: str,
    notion: Optional[str],
    matiere: Optional[str],
) -> Optional[Dict[str, Any]]:
    prompt = (
        "Tu es un controleur pedagogique independant. Recalcule les passages "
        "quantitatifs et verifie chaque etape avant de declarer cette reponse correcte. "
        "Controle la coherence exacte entre explication, exemple, exercice et correction. "
        "Pour les maths/physique, verifie notamment signes, unites, dimensions, "
        "conversions, matrices, equations et resultats numeriques ; pour l'informatique, "
        "verifie syntaxe, semantique et sortie du code ; sinon verifie faits et logique. "
        "Signale toute erreur ou incoherence justifiable.\\n"
        f"Question: {question}\\nNotion: {notion or '-'}\\nMatiere: {matiere or '-'}\\n"
        f"{json.dumps(reponse, ensure_ascii=False)}"
    )
    prompt += _suffixe_format_prompt(quiz=False)
    return _gemini_json(prompt, TUTEUR_GEMINI_SCHEMA)


def verifier_tuteur(
    reponse: Dict[str, str],
    question: str,
    notion: Optional[str],
    matiere: Optional[str],
    outil_tuteur: Dict[str, Any],
) -> Tuple[Dict[str, str], bool, Dict[str, Any]]:
    """Valide une reponse de tuteur avec des critiques independantes.

    L'arbitre reutilise le modele principal et le meme contrat structure que
    la generation initiale.
    """
    if not parametres.ai_ensemble_enabled:
        return reponse, False, {"models": [parametres.groq_model], "critics": []}

    critiques: List[Dict[str, Any]] = []
    qwen = _critique_tuteur_groq(reponse, question, notion, matiere)
    if qwen:
        critiques.append({"model": parametres.groq_critic_model, "avis": qwen})
    gemini = _critique_tuteur_gemini(reponse, question, notion, matiere)
    if gemini:
        critiques.append({"model": parametres.gemini_model, "avis": gemini})

    if not critiques:
        return reponse, False, {"models": [parametres.groq_model], "critics": []}

    problemes = [
        p
        for item in critiques
        for p in (item["avis"].get("problemes") or [])
    ]
    tous_confiants = all(item["avis"].get("confiant") is True for item in critiques)
    if tous_confiants and not problemes:
        return reponse, True, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
        }

    client = _groq_client()
    if client is None:
        return reponse, False, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
            "arbitration": "original",
        }

    prompt = (
        "Tu es l'arbitre final du Tuteur IA. Produis UNE SEULE reponse fiable "
        "en tenant compte des critiques independantes et en refaisant toi-meme les "
        "calculs necessaires. La reponse finale doit conserver exactement quatre "
        "parties : explication, exemple, exercice, correction. La correction doit "
        "resoudre exactement l'exercice presente, avec les memes donnees, sans "
        "inventer une autre question. Verifie une derniere fois les calculs, signes, "
        "unites, dimensions, conversions, matrices, equations et resultats numeriques "
        "en maths/physique, ainsi que syntaxe/semantique/resultat du code en informatique. "
        "Ne laisse jamais une affirmation du type « aucune solution », « resultat "
        "impossible » ou « corrige l'enonce » sans expliquer et reparer l'incoherence. "
        "Reponds en francais, clair et pedagogique.\\n\\n"
        f"Question: {question}\\nNotion: {notion or '-'}\\nMatiere: {matiere or '-'}\\n"
        f"REPONSE INITIALE:\\n{json.dumps(reponse, ensure_ascii=False)}\\n\\n"
        f"CRITIQUES:\\n{json.dumps(critiques, ensure_ascii=False)}"
    )
    prompt += _suffixe_format_prompt(quiz=False)
    result = _groq_structured_tool(
        model=parametres.groq_model,
        tool=outil_tuteur,
        tool_name="repondre_tuteur",
        prompt=prompt,
        max_completion_tokens=4096,
        reasoning_effort="high",
    )
    if not result:
        return reponse, False, {
            "models": [parametres.groq_model] + [x["model"] for x in critiques],
            "critics": critiques,
            "arbitration": "original",
        }

    final = normaliser_structure_tuteur({
        "explication": result.get("explication") or reponse.get("explication") or "—",
        "exemple": result.get("exemple") or reponse.get("exemple") or "—",
        "exercice": result.get("exercice") or reponse.get("exercice") or "—",
        "correction": result.get("correction") or reponse.get("correction") or "—",
    })
    return final, True, {
        "models": [parametres.groq_model] + [x["model"] for x in critiques],
        "critics": critiques,
        "arbitration": "groq_arbiter",
    }
