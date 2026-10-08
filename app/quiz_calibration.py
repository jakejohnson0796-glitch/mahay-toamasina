"""Calibration de confiance du Quiz IA.

Le score mesure la justesse d'une réponse. Ce module mesure en plus la
qualité du jugement de l'étudiant sur sa propre réponse, sans ajouter une
nouvelle table en base : les niveaux sont stockés dans TentativeQuiz.reponses_json.
"""

import json
from typing import Optional

NIVEAUX_CONFIANCE = ("faible", "moyenne", "forte")
VALEURS_CONFIANCE = {
    "faible": 0.25,
    "moyenne": 0.55,
    "forte": 0.85,
}
LIBELLES_CONFIANCE = {
    "faible": "Faible",
    "moyenne": "Moyenne",
    "forte": "Forte",
}


def normaliser_confiances(valeurs, taille: int) -> list[Optional[str]]:
    """Normalise une liste de niveaux et conserve la position des questions."""
    resultats: list[Optional[str]] = []
    valeurs = list(valeurs or [])
    for index in range(max(0, taille)):
        valeur = valeurs[index] if index < len(valeurs) else None
        valeur = str(valeur).strip().lower() if valeur is not None else None
        resultats.append(valeur if valeur in NIVEAUX_CONFIANCE else None)
    return resultats


def lire_confiances(tentative) -> list[Optional[str]]:
    """Lit les jugements de confiance sur les tentatives nouvelles et futures."""
    if not tentative.reponses_json:
        return [None] * int(tentative.nb_questions or 0)
    try:
        donnees = json.loads(tentative.reponses_json)
    except (TypeError, ValueError):
        return [None] * int(tentative.nb_questions or 0)
    if not isinstance(donnees, dict):
        return [None] * int(tentative.nb_questions or 0)
    return normaliser_confiances(
        donnees.get("confiances") or [],
        int(tentative.nb_questions or 0),
    )


def fusionner_confiances(tentative, confiances: list[Optional[str]]) -> None:
    """Ajoute les confiances au paquet JSON sans casser les anciennes réponses."""
    try:
        donnees = json.loads(tentative.reponses_json or "[]")
    except (TypeError, ValueError):
        donnees = []

    if isinstance(donnees, dict):
        reponses = donnees.get("reponses") or []
        ordre = donnees.get("ordre")
        serie = donnees.get("serie_reussites")
        paquet = {"reponses": reponses, "confiances": confiances}
        if ordre is not None:
            paquet["ordre"] = ordre
        if serie is not None:
            paquet["serie_reussites"] = serie
    else:
        paquet = {
            "reponses": donnees if isinstance(donnees, list) else [],
            "confiances": confiances,
        }

    tentative.reponses_json = json.dumps(paquet, ensure_ascii=False)


def diagnostic_confiance(tentative, questions: Optional[list] = None, reponses: Optional[list] = None) -> dict:
    """Mesure l'écart entre certitude annoncée et résultat observé.

    Le signal est volontairement prudent : moins de 3 jugements ne produit pas
    de diagnostic de calibration. On distingue surtout la surconfiance
    (confiance forte + erreurs) de la sous-confiance (confiance faible +
    bonnes réponses).
    """
    if reponses is None:
        try:
            donnees = json.loads(tentative.reponses_json or "[]")
        except (TypeError, ValueError):
            donnees = []
        if isinstance(donnees, dict):
            reponses = list(donnees.get("reponses") or [])
        else:
            reponses = list(donnees or [])

    confiances = lire_confiances(tentative)
    observations = []
    questions = list(questions or [])
    surconfiances = 0
    sousconfiances = 0

    for index, confiance in enumerate(confiances):
        if confiance not in VALEURS_CONFIANCE:
            continue
        reponse = reponses[index] if index < len(reponses) else None
        if reponse is None:
            continue
        correcte = False
        try:
            correcte = (
                index < len(questions)
                and reponse == questions[index].get("index_bonne_reponse")
            )
        except (IndexError, AttributeError, TypeError):
            correcte = False
        observations.append((confiance, correcte))
        if confiance == "forte" and not correcte:
            surconfiances += 1
        if confiance == "faible" and correcte:
            sousconfiances += 1

    nb = len(observations)
    if nb == 0:
        return {
            "statut": "insuffisante",
            "libelle": "Pas encore assez de données",
            "message": "Indique ton niveau de confiance sur quelques questions pour apprendre à mieux lire ton propre niveau.",
            "nb_observations": 0,
            "ecart": None,
            "surconfiances": 0,
            "sousconfiances": 0,
            "niveau_moyen": None,
        }

    ecarts = []
    for confiance, correcte in observations:
        ecarts.append(abs(VALEURS_CONFIANCE[confiance] - (1.0 if correcte else 0.0)))
    ecart = round(sum(ecarts) / nb * 100)

    niveau_moyen = round(
        sum(VALEURS_CONFIANCE[c] for c, _ in observations) / nb * 100
    )

    if nb < 3:
        statut = "en_observation"
        libelle = "Calibration en observation"
        message = "Continue à noter ta confiance : le système attend plusieurs réponses avant de tirer une conclusion."
    elif surconfiances / nb >= 0.30:
        statut = "surconfiance"
        libelle = "Attention à la surconfiance"
        message = "Tu es parfois très sûr de toi alors que la réponse est fausse. Le prochain entraînement doit vérifier les points que tu crois déjà acquis."
    elif sousconfiances / nb >= 0.30:
        statut = "sous_confiance"
        libelle = "Tu sous-estimes parfois ton niveau"
        message = "Tu réussis aussi des questions sur lesquelles tu te sens peu sûr. Le Tuteur peut t'aider à distinguer doute et difficulté réelle."
    elif ecart <= 20:
        statut = "calibree"
        libelle = "Confiance bien calibrée"
        message = "Ta confiance suit assez bien tes résultats : c'est un bon signal pour décider quoi réviser et quoi laisser respirer."
    else:
        statut = "a_affiner"
        libelle = "Calibration à affiner"
        message = "Tes certitudes et tes résultats ne coïncident pas toujours. Les prochaines répétitions serviront à affiner cette estimation."

    return {
        "statut": statut,
        "libelle": libelle,
        "message": message,
        "nb_observations": nb,
        "ecart": ecart,
        "surconfiances": surconfiances,
        "sousconfiances": sousconfiances,
        "niveau_moyen": niveau_moyen,
    }
