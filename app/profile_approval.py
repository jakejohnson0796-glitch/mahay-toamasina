"""Règles communes de validation des profils non élèves."""

from __future__ import annotations

from typing import Any, Optional


CHAMPS_VALIDATION_PROFIL = {
    "professeur": {
        "label": "Enseignant / Professeur",
        "statut": "statut_verification_enseignant",
        "date_demande": "demande_enseignant_le",
        "date_decision": "verification_enseignant_le",
        "motif": "motif_refus_enseignant",
    },
    "repetiteur": {
        "label": "Répétiteur / Répétitrice",
        "statut": "statut_verification_repetiteur",
        "date_demande": "demande_repetiteur_le",
        "date_decision": "verification_repetiteur_le",
        "motif": "motif_refus_repetiteur",
    },
    "sponsor": {
        "label": "Sponsor / Commerce / Service",
        "statut": "statut_verification_sponsor",
        "date_demande": "demande_sponsor_le",
        "date_decision": "verification_sponsor_le",
        "motif": "motif_refus_sponsor",
    },
    "responsable": {
        "label": "Parent / Responsable légal",
        "statut": "statut_verification_responsable",
        "date_demande": "demande_responsable_le",
        "date_decision": "verification_responsable_le",
        "motif": "motif_refus_responsable",
    },
}


def details_validation_profil(utilisateur: Any) -> Optional[dict]:
    """Retourne les informations d'une demande en attente ou refusée."""
    profil = str(getattr(utilisateur, "profil_souhaite", "") or "")
    configuration = CHAMPS_VALIDATION_PROFIL.get(profil)
    if not configuration:
        return None

    statut = str(getattr(utilisateur, configuration["statut"], "non_concerne") or "non_concerne")
    if statut not in {"en_attente", "refuse"}:
        return None

    return {
        "profil": profil,
        "libelle": configuration["label"],
        "statut": statut,
        "date_demande": getattr(utilisateur, configuration["date_demande"], None),
        "date_decision": getattr(utilisateur, configuration["date_decision"], None),
        "motif": getattr(utilisateur, configuration["motif"], None),
    }


def profil_validation_requise(utilisateur: Any) -> bool:
    """Tout profil non-élève en attente/refusé est confiné à son suivi de demande."""
    return details_validation_profil(utilisateur) is not None


def acces_interactif_admin_autorise(utilisateur: Any) -> bool:
    """Autorise la supervision seulement si le profil effectif est cohérent.

    Les demandes en attente ou refusées restent exclues, même si leur rôle
    technique est encore ETUDIANT. Un ancien profil retiré peut retrouver
    l'espace élève, sans réactiver ses anciennes permissions professionnelles.
    """
    if not utilisateur or getattr(utilisateur, "banni", False):
        return False

    role_obj = getattr(utilisateur, "role", "")
    role = str(getattr(role_obj, "value", role_obj) or "")
    profil = str(getattr(utilisateur, "profil_souhaite", "") or "")

    if role == "etudiant":
        if profil == "eleve":
            return True
        configuration = CHAMPS_VALIDATION_PROFIL.get(profil)
        if not configuration:
            return False
        statut = str(
            getattr(utilisateur, configuration["statut"], "non_concerne")
            or "non_concerne"
        )
        return statut == "retire"

    configuration = CHAMPS_VALIDATION_PROFIL.get(profil)
    if not configuration or role != profil:
        return False

    statut = str(
        getattr(utilisateur, configuration["statut"], "non_concerne")
        or "non_concerne"
    )
    return statut == "approuve"
