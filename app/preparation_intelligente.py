"""Bilan de diagnostic par matière pour la préparation CEPE, BEPC et BAC.

Les résultats proviennent exclusivement des ProgressionNotion de l'utilisateur
et du niveau actuellement déclaré. Une matière sans historique reste « à évaluer ».
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


def _cle(texte: Any) -> str:
    return str(texte or "").strip().casefold()


def construire_bilans_matieres(
    matieres: Iterable[str],
    progressions: Iterable[Any],
    niveau: Optional[str] = None,
    maintenant: Optional[datetime] = None,
) -> list[dict]:
    """Construit un état prudent par matière sans inventer de niveau initial.

    Les progressions d'un autre niveau sont exclues afin qu'un ancien parcours
    ne soit pas présenté comme le diagnostic de la classe actuellement suivie.
    La maîtrise confirmée est recalculée avec les preuves objectives existantes.
    """
    from . import quiz as quiz_module

    instant = maintenant or datetime.now(timezone(timedelta(hours=3)))
    niveau_cible = _cle(niveau)
    par_matiere = defaultdict(list)

    for progression in progressions or []:
        if int(getattr(progression, "nb_questions", 0) or 0) <= 0:
            continue
        if niveau_cible and _cle(getattr(progression, "niveau", None)) != niveau_cible:
            continue
        cle_matiere = _cle(getattr(progression, "matiere", None))
        if cle_matiere:
            par_matiere[cle_matiere].append(progression)

    bilans = []
    deja_vues = set()
    for matiere in matieres or []:
        libelle = str(matiere or "").strip()
        cle_matiere = _cle(libelle)
        if not cle_matiere or cle_matiere in deja_vues:
            continue
        deja_vues.add(cle_matiere)

        observations = par_matiere.get(cle_matiere, [])
        if not observations:
            bilans.append({
                "matiere": libelle,
                "statut": "a_evaluer",
                "libelle_statut": "Diagnostic à faire",
                "libelle_action": "Commencer le diagnostic",
                "score": None,
                "nb_questions": 0,
                "nb_notions": 0,
                "nb_confirmees": 0,
                "nb_a_revoir": 0,
                "resume": "Aucune réponse analysée pour le moment.",
            })
            continue

        diagnostics = [
            (progression, quiz_module.diagnostiquer_maitrise(progression))
            for progression in observations
        ]
        total_questions = sum(
            int(getattr(progression, "nb_questions", 0) or 0)
            for progression, _ in diagnostics
        )
        score_pondere = sum(
            diagnostic["score"] * int(getattr(progression, "nb_questions", 0) or 0)
            for progression, diagnostic in diagnostics
        )
        score = round(score_pondere / total_questions) if total_questions else 0
        confirmees = sum(
            1 for _, diagnostic in diagnostics
            if diagnostic["maitrise_confirmee"]
        )
        a_revoir = 0
        revisions_echues = 0
        for progression, diagnostic in diagnostics:
            prochaine = getattr(progression, "prochaine_revision_le", None)
            echue = bool(prochaine and prochaine <= instant)
            revisions_echues += int(echue)
            if not diagnostic["maitrise_confirmee"] or echue:
                a_revoir += 1

        if confirmees == len(diagnostics):
            statut = "maitrisee"
            libelle_statut = "Maîtrise confirmée"
        elif score < 50 or any(
            diagnostic["statut"] == "fragile"
            for _, diagnostic in diagnostics
        ):
            statut = "a_renforcer"
            libelle_statut = "À renforcer"
        elif score >= 85:
            statut = "a_confirmer"
            libelle_statut = "Maîtrise à confirmer"
        else:
            statut = "en_consolidation"
            libelle_statut = "En consolidation"

        notions = len(diagnostics)
        resume = (
            f"{total_questions} réponse{'s' if total_questions != 1 else ''} analysée{'s' if total_questions != 1 else ''} "
            f"sur {notions} notion{'s' if notions != 1 else ''} suivie{'s' if notions != 1 else ''}."
        )
        if revisions_echues:
            resume += f" {revisions_echues} révision{'s' if revisions_echues != 1 else ''} arrivée{'s' if revisions_echues != 1 else ''} à échéance."

        bilans.append({
            "matiere": libelle,
            "statut": statut,
            "libelle_statut": libelle_statut,
            "libelle_action": (
                "Faire un nouvel entraînement"
                if statut == "maitrisee"
                else "Reprendre cette matière"
            ),
            "score": max(0, min(100, score)),
            "nb_questions": total_questions,
            "nb_notions": notions,
            "nb_confirmees": confirmees,
            "nb_a_revoir": a_revoir,
            "resume": resume,
        })

    priorites = {
        "a_evaluer": 0,
        "a_renforcer": 1,
        "en_consolidation": 2,
        "a_confirmer": 3,
        "maitrisee": 4,
    }
    bilans.sort(key=lambda bilan: (priorites[bilan["statut"]], bilan["matiere"].casefold()))
    return bilans


def construire_plan_hebdomadaire(
    bilans_matieres: Iterable[dict],
    *,
    maintenant: Optional[datetime] = None,
    objectif: Optional[str] = None,
    option_ps: Optional[str] = None,
    lien_quiz: str = "/quiz",
) -> dict:
    """Construit un programme de 7 jours à partir des diagnostics réellement observés.

    Le planning est volontairement recalculé à chaque affichage : aucun score
    n'est inventé et aucun état de progression n'est dupliqué en base. Les
    entraînements réutilisent le parcours d'examen déjà validé côté serveur.
    """
    instant = maintenant or datetime.utcnow()
    priorites = {
        "a_evaluer": 0,
        "a_renforcer": 1,
        "en_consolidation": 2,
        "a_confirmer": 3,
        "maitrisee": 4,
    }
    candidats = []
    vus = set()
    for bilan in bilans_matieres or []:
        if not isinstance(bilan, dict):
            continue
        matiere = str(bilan.get("matiere") or "").strip()
        cle = _cle(matiere)
        if not cle or cle in vus:
            continue
        vus.add(cle)
        statut = bilan.get("statut")
        if statut not in priorites:
            statut = "a_evaluer" if bilan.get("score") is None else "en_consolidation"
        copie = dict(bilan)
        copie["matiere"] = matiere
        copie["statut"] = statut
        candidats.append(copie)

    def cle_priorite(bilan: dict):
        score = bilan.get("score")
        score = int(score) if score is not None else -1
        return (
            priorites[bilan["statut"]],
            score,
            -int(bilan.get("nb_a_revoir") or 0),
            bilan["matiere"].casefold(),
        )

    candidats.sort(key=cle_priorite)
    if not candidats:
        return {
            "seances": [],
            "nb_matieres": 0,
            "duree_totale_minutes": 0,
        }

    objectifs_autorises = {"cepe", "bepc_pe", "bepc_ps", "baccalaureat"}
    objectif_valide = objectif if objectif in objectifs_autorises else None
    option_validee = (
        str(option_ps or "").strip().upper()
        if objectif_valide == "bepc_ps" else None
    )
    if option_validee not in {"A", "B"}:
        if objectif_valide == "bepc_ps":
            objectif_valide = None
        option_validee = None

    # Les séances de correction alternent avec les quiz pour éviter une suite
    # de tests sans temps de compréhension. Quatre matières au plus sont
    # mises en avant chaque semaine ; les premières sont les plus prioritaires.
    sequence = [
        (0, "quiz"),
        (0, "revision"),
        (1, "quiz"),
        (1, "revision"),
        (2, "quiz"),
        (3, "quiz" if len(candidats) >= 4 else "revision"),
        (None, "bilan"),
    ]
    jours_fr = (
        "lundi", "mardi", "mercredi", "jeudi",
        "vendredi", "samedi", "dimanche",
    )
    seances = []
    occurrences = {}

    for index, (index_matiere, mode) in enumerate(sequence):
        date_seance = (instant + timedelta(days=index)).date()
        jour = (
            "Aujourd'hui" if index == 0
            else "Demain" if index == 1
            else jours_fr[date_seance.weekday()].capitalize()
        )
        date_label = date_seance.strftime("%d/%m")

        if mode == "bilan":
            seances.append({
                "jour": jour,
                "date_label": date_label,
                "titre": "Bilan de la semaine",
                "type_label": "Faire le point",
                "matiere": None,
                "description": (
                    "Consulte tes résultats, repère ce qui a progressé et "
                    "choisis les matières à reprendre la semaine prochaine."
                ),
                "duree_minutes": 10,
                "objectif": None,
                "option_ps": None,
                "href": "/mon-parcours",
                "action_label": "Voir ma progression",
            })
            continue

        position = min(int(index_matiere or 0), len(candidats) - 1)
        bilan = candidats[position]
        matiere = bilan["matiere"]
        cle_matiere = _cle(matiere)
        occurrence = occurrences.get(cle_matiere, 0)
        occurrences[cle_matiere] = occurrence + int(mode == "quiz")

        if mode == "revision":
            titre = f"Correction active · {matiere}"
            type_label = "Comprendre ses erreurs"
            description = (
                "Reprends les corrections et les notions de cette matière. "
                "Explique une règle sans regarder le cours, puis note ce qui "
                "reste difficile."
            )
            duree = 15
            href = "/mes-revisions"
            action_label = "Ouvrir mes révisions"
            objectif_session = None
            option_session = None
        else:
            if occurrence > 0:
                titre = f"Vérifier tes progrès · {matiere}"
                type_label = "Nouvelle preuve"
                description = (
                    "Refais un entraînement dans cette matière pour vérifier "
                    "ce qui a été retenu depuis la séance précédente."
                )
            elif bilan["statut"] == "a_evaluer":
                titre = f"Diagnostic initial · {matiere}"
                type_label = "Matière à évaluer"
                description = (
                    "Aucune réponse analysée n'est encore disponible pour "
                    "cette matière. Ce premier quiz établira un point de départ, "
                    "sans supposer que tu es en difficulté."
                )
            elif bilan["statut"] == "a_renforcer":
                titre = f"Renforcement ciblé · {matiere}"
                type_label = "Priorité de révision"
                description = (
                    f"{bilan.get('resume') or 'Des notions demandent à être reprises.'} "
                    "Travaille les bases avant d'augmenter la difficulté."
                )
            elif bilan["statut"] == "a_confirmer":
                titre = f"Vérification des acquis · {matiere}"
                type_label = "Maîtrise à confirmer"
                description = (
                    "Vérifie tes acquis avec un nouvel entraînement et "
                    "consolide les preuves encore manquantes."
                )
            elif bilan["statut"] == "maitrisee":
                titre = f"Rappel espacé · {matiere}"
                type_label = "Entretenir les acquis"
                description = (
                    "Entretiens cette maîtrise avec un rappel et un exercice "
                    "de difficulté adaptée."
                )
            else:
                titre = f"Consolidation · {matiere}"
                type_label = "Entraînement ciblé"
                description = (
                    f"{bilan.get('resume') or 'Poursuis tes entraînements.'} "
                    "Consolide les notions avant de passer à la suite."
                )
            duree = 20
            href = lien_quiz if not objectif_valide else None
            action_label = (
                "Choisir un quiz" if not objectif_valide
                else "Lancer l'entraînement"
            )
            objectif_session = objectif_valide
            option_session = option_validee

        seances.append({
            "jour": jour,
            "date_label": date_label,
            "titre": titre,
            "type_label": type_label,
            "matiere": matiere,
            "description": description,
            "duree_minutes": duree,
            "objectif": objectif_session,
            "option_ps": option_session,
            "href": href,
            "action_label": action_label,
        })

    return {
        "seances": seances,
        "nb_matieres": len(candidats),
        "duree_totale_minutes": sum(
            int(seance["duree_minutes"]) for seance in seances
        ),
    }
