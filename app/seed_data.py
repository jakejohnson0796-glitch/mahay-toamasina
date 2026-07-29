"""
Peuple la base avec la vraie structure de l'Universite de Toamasina, pour
ne pas demarrer avec une base totalement vide. A completer/corriger toi-meme
si des filieres manquent ou ont change de nom.
"""
from sqlmodel import Session, select

from .models import Faculte, Filiere

STRUCTURE_UNIVERSITE = {
    "Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)": [
        "Droit",
        "Economie",
        "Gestion",
        "Mathematiques et Informatique",
    ],
    "Sciences et Technologies": [
        "Physique",
        "Chimie",
        "Sciences de la Vie et de la Terre",
    ],
    "Lettres et Sciences Humaines": [
        "Lettres francaises",
        "Anglais",
        "Histoire-Geographie",
        "Philosophie",
    ],
    "Medecine": [
        "Medecine generale",
    ],
}


def peupler_donnees_initiales(session: Session) -> None:
    """Insere les facultes/filieres si la base est vide. Ne fait rien sinon
    (idempotent : peut etre appele a chaque demarrage sans risque)."""
    if session.exec(select(Faculte)).first():
        return

    for nom_faculte, filieres in STRUCTURE_UNIVERSITE.items():
        faculte = Faculte(nom=nom_faculte)
        session.add(faculte)
        session.commit()
        session.refresh(faculte)
        for nom_filiere in filieres:
            session.add(Filiere(nom=nom_filiere, faculte_id=faculte.id))
    session.commit()
