"""Transitions déterministes pour le parcours adaptatif de Gasy Mahay."""
from typing import Any, Dict


ETAPES = ("comprendre", "pratiquer", "verifier")


def transition_apres_quiz(score_pourcent: int, maitrise_confirmee: bool) -> Dict[str, str]:
    """Choisit l'étape suivante sans confondre bon score et maîtrise confirmée."""
    score = max(0, min(100, int(score_pourcent or 0)))
    if score < 60:
        return {
            "etape": "comprendre",
            "statut": "active",
            "feedback": (
                f"Résultat : {score} %. La notion reste fragile. Reviens à l'explication "
                "du Tuteur IA avant de refaire un quiz sur la même notion."
            ),
        }
    if score < 80:
        return {
            "etape": "pratiquer",
            "statut": "active",
            "feedback": (
                f"Résultat : {score} %. Tu progresses, mais il faut encore pratiquer "
                "la même notion pour stabiliser les acquis."
            ),
        }
    if maitrise_confirmee:
        return {
            "etape": "terminee",
            "statut": "terminee",
            "feedback": (
                f"Résultat : {score} %. La maîtrise est confirmée par l'historique : "
                "la mission est terminée et une autre notion peut être travaillée."
            ),
        }
    return {
        "etape": "verifier",
        "statut": "active",
        "feedback": (
            f"Résultat : {score} %. Très bon score. Le parcours demande encore une "
            "preuve de maîtrise confirmée avant de clôturer la mission."
        ),
    }


def appliquer_etat(mission: Dict[str, Any], etat: Any) -> Dict[str, Any]:
    """Fusionne l'état persistant avec les actions à afficher dans le gabarit."""
    vue = dict(mission)
    vue["mission_id"] = etat.id
    vue["etat_mission"] = etat.statut
    vue["etape_courante"] = etat.etape
    vue["nb_tentatives"] = int(etat.nb_tentatives or 0)
    vue["dernier_score"] = etat.dernier_score
    vue["retour_adaptatif"] = etat.dernier_feedback
    etapes = [dict(item) for item in vue.get("etapes", [])]

    if etat.statut == "terminee":
        vue["titre"] = "Mission terminée"
        vue["objectif"] = "Tu as obtenu la preuve attendue pour cette notion."
        vue["action_principale"] = None
        vue["action_secondaire"] = None
        vue["action_label"] = "Mission terminée"
        vue["message"] = etat.dernier_feedback or "La maîtrise a été confirmée."
        vue["preuve"] = "Passe à une autre notion pour poursuivre ta progression."
        for item in etapes:
            item["etat"] = "terminee"
        vue["etapes"] = etapes
        return vue

    titres = {
        "comprendre": "Comprendre une difficulté",
        "pratiquer": "Pratiquer la notion ciblée",
        "verifier": "Vérifier la maîtrise",
    }
    objectifs = {
        "comprendre": "Comprendre l'erreur prioritaire, reformuler la règle puis passer à un nouvel exercice.",
        "pratiquer": "Réussir une série de 5 questions ciblées sur exactement la même notion.",
        "verifier": "Obtenir une nouvelle série réussie et vérifier les critères de maîtrise persistants.",
    }
    etape = etat.etape if etat.etape in ETAPES else "comprendre"
    position = ETAPES.index(etape)
    vue["titre"] = titres[etape]
    vue["objectif"] = objectifs[etape]
    vue["action_principale"] = "tuteur" if etape == "comprendre" else "quiz"
    vue["action_secondaire"] = "quiz" if etape == "comprendre" else "tuteur"
    vue["action_label"] = (
        "Revoir l'explication avec le Tuteur IA"
        if etape == "comprendre"
        else ("Lancer le quiz ciblé" if etape == "pratiquer" else "Faire l'épreuve de vérification")
    )
    vue["message"] = etat.dernier_feedback or "La mission garde la même notion et choisit la prochaine étape à partir de tes résultats."
    vue["preuve"] = "La mission ne se termine qu'après confirmation de la maîtrise, pas sur un bon score isolé."
    for i, item in enumerate(etapes):
        item["etat"] = "terminee" if i < position else ("prioritaire" if i == position else "a_faire")
        item["type"] = ("tuteur", "quiz", "preuve")[i]
    vue["etapes"] = etapes
    return vue
