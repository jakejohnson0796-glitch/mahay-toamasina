"""Bilan de diagnostic par matière pour la préparation CEPE, BEPC et BAC.

Les résultats proviennent exclusivement des ProgressionNotion de l'utilisateur
et du niveau actuellement déclaré. Une matière sans historique reste « à évaluer ».
"""
from collections import defaultdict
from datetime import datetime
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

    instant = maintenant or datetime.utcnow()
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
