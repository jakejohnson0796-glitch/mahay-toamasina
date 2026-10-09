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


def choisir_prochaine_notion(carte: Dict[str, Any], progressions: Any, exclure_id: Any = None):
    """Sélectionne une notion non maîtrisée dont les prérequis observés sont confirmés."""
    par_id = {
        int(item.id): item for item in progressions
        if getattr(item, "id", None) is not None
    }
    noeuds = [
        node for sujet in carte.get("sujets", [])
        for node in sujet.get("nodes", [])
        if int(node.get("id") or 0) in par_id
    ]
    par_matiere_notion = {
        (str(node.get("matiere") or ""), str(node.get("notion") or "")): node
        for node in noeuds
    }
    candidats = []
    for node in noeuds:
        node_id = int(node.get("id") or 0)
        progression = par_id.get(node_id)
        if node_id == int(exclure_id or 0) or progression is None:
            continue
        if bool(getattr(progression, "maitrise_confirmee", False)):
            continue
        prerequis = [
            par_matiere_notion[(str(node.get("matiere") or ""), str(nom))]
            for nom in node.get("prerequis", [])
            if (str(node.get("matiere") or ""), str(nom)) in par_matiere_notion
        ]
        if all(
            bool(getattr(par_id.get(int(parent.get("id") or 0)), "maitrise_confirmee", False))
            for parent in prerequis
        ):
            candidats.append(node)
    if not candidats:
        return None
    candidats.sort(
        key=lambda node: (
            int(node.get("score") or 0),
            -int(getattr(par_id.get(int(node.get("id") or 0)), "nb_erreurs", 0) or 0),
            str(node.get("notion") or "").lower(),
        )
    )
    return candidats[0]


def vue_toutes_notions_confirmees() -> dict:
    """État d'interface quand toutes les notions observées sont confirmées."""
    return {
        "active": False,
        "toutes_confirmees": True,
        "notion": None,
        "matiere": None,
        "progression_id": None,
        "mission_id": None,
        "score": None,
        "erreurs": 0,
        "titre": "Toutes les notions suivies sont maîtrisées",
        "objectif": "Tes notions suivies ont obtenu une preuve de maîtrise. Tu peux maintenant commencer une nouvelle notion.",
        "duree": "À ton rythme",
        "action_principale": None,
        "action_secondaire": None,
        "action_label": "Parcours validé",
        "etape_courante": "terminee",
        "etat_mission": "terminee",
        "nb_tentatives": 0,
        "dernier_score": None,
        "retour_adaptatif": None,
        "message": "Ajoute une nouvelle preuve avec un quiz libre pour enrichir ta carte de connaissances.",
        "etapes": [],
        "preuve": "Une notion dépendante n'est proposée qu'après confirmation de ses prérequis observés.",
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
