"""Persistance des metriques de performance de l'ensemble IA."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from .database import engine
from .models import PerformanceModeleIA

logger = logging.getLogger(__name__)


def enregistrer_audit(
    audit: Dict[str, Any],
    *,
    type_interaction: str,
    matiere: Optional[str],
    niveau: Optional[str],
    strategie: str,
    duree_secondes: Optional[float],
) -> None:
    """Met a jour les compteurs agreges par modele et par strategie."""
    maintenant = datetime.utcnow()
    try:
        with Session(engine) as session:
            for item in audit.get("critics") or []:
                modele = str(item.get("model") or "inconnu")
                avis = item.get("avis") or {}
                problemes = avis.get("problemes") or []
                element = session.exec(
                    select(PerformanceModeleIA).where(
                        PerformanceModeleIA.type_interaction == type_interaction,
                        PerformanceModeleIA.matiere == (matiere or "").strip(),
                        PerformanceModeleIA.niveau == (niveau or "").strip(),
                        PerformanceModeleIA.modele == modele,
                        PerformanceModeleIA.strategie == strategie,
                    )
                ).first()
                if element is None:
                    element = PerformanceModeleIA(
                        type_interaction=type_interaction,
                        matiere=(matiere or "").strip(),
                        niveau=(niveau or "").strip(),
                        modele=modele,
                        strategie=strategie,
                    )

                ancien_nombre = element.appels
                element.appels += 1
                element.confiants += int(avis.get("confiant") is True)
                element.problemes += len(problemes)
                element.derniere_utilisation_le = maintenant
                element.derniere_duree_secondes = duree_secondes
                if duree_secondes is not None:
                    element.duree_moyenne_secondes = (
                        (element.duree_moyenne_secondes * ancien_nombre + duree_secondes)
                        / element.appels
                    )
                session.add(element)

            if audit.get("arbitration") == "groq_arbiter":
                modele_arbitre = "arbiter:" + str(
                    (audit.get("models") or ["inconnu"])[0]
                )
                element = session.exec(
                    select(PerformanceModeleIA).where(
                        PerformanceModeleIA.type_interaction == type_interaction,
                        PerformanceModeleIA.matiere == (matiere or "").strip(),
                        PerformanceModeleIA.niveau == (niveau or "").strip(),
                        PerformanceModeleIA.modele == modele_arbitre,
                        PerformanceModeleIA.strategie == strategie,
                    )
                ).first()
                if element is None:
                    element = PerformanceModeleIA(
                        type_interaction=type_interaction,
                        matiere=(matiere or "").strip(),
                        niveau=(niveau or "").strip(),
                        modele=modele_arbitre,
                        strategie=strategie,
                    )
                element.arbitrages += 1
                element.derniere_utilisation_le = maintenant
                session.add(element)

            session.commit()
    except Exception:
        # Les metriques ne doivent jamais casser la generation ou le worker.
        logger.exception("Impossible de persister les metriques de l'ensemble IA.")


def resume_global() -> Dict[str, Any]:
    """Resume compact pour la console/admin."""
    try:
        with Session(engine) as session:
            lignes = session.exec(select(PerformanceModeleIA)).all()
    except Exception:
        return {"appels": 0, "problemes": 0, "arbitrages": 0, "duree_moyenne": 0.0, "modeles": []}

    return {
        "appels": sum(x.appels for x in lignes),
        "problemes": sum(x.problemes for x in lignes),
        "arbitrages": sum(x.arbitrages for x in lignes),
        "duree_moyenne": (
            round(
                sum(x.duree_moyenne_secondes * x.appels for x in lignes)
                / max(1, sum(x.appels for x in lignes)),
                2,
            )
        ),
        "modeles": sorted(
            [
                {
                    "modele": x.modele,
                    "appels": x.appels,
                    "confiants": x.confiants,
                    "problemes": x.problemes,
                    "arbitrages": x.arbitrages,
                    "strategie": x.strategie,
                    "duree_moyenne": round(x.duree_moyenne_secondes, 2),
                }
                for x in lignes
            ],
            key=lambda item: (-item["appels"], item["modele"]),
        ),
    }
