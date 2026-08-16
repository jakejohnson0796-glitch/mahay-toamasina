"""
Peuple la base avec la vraie structure de l'Universite de Toamasina, pour
ne pas demarrer avec une base totalement vide. A completer/corriger toi-meme
si des filieres manquent ou ont change de nom.
"""
from sqlmodel import Session, select

from .models import Faculte, Filiere, Universite

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
    """Insere les facultes/filieres de Toamasina si elles n'existent pas
    deja. Idempotent : peut etre appele a chaque demarrage sans risque.

    IMPORTANT : la garde ci-dessous verifie specifiquement les facultes
    de Toamasina (pas "une Faculte existe-t-elle, n'importe laquelle"),
    car la migration f2b8e6a1c9d3 cree desormais aussi des Faculte pour
    les 5 autres universites — un simple "if Faculte existe" se
    declencherait a tort sur une base neuve et sauterait completement
    le seed de Toamasina."""
    universite_toamasina = session.exec(
        select(Universite).where(Universite.nom == "Universite de Toamasina")
    ).first()
    if not universite_toamasina:
        # Ne devrait jamais arriver en pratique (la migration
        # e1a4c9d2b7f5 la cree toujours), mais si ce module est un jour
        # appele avant que les migrations aient tourne, on ne veut pas
        # planter avec une IntegrityError obscure sur universite_id.
        return

    deja_seede = session.exec(
        select(Faculte).where(Faculte.universite_id == universite_toamasina.id)
    ).first()
    if deja_seede:
        return

    for nom_faculte, filieres in STRUCTURE_UNIVERSITE.items():
        faculte = Faculte(nom=nom_faculte, universite_id=universite_toamasina.id)
        session.add(faculte)
        session.commit()
        session.refresh(faculte)
        for nom_filiere in filieres:
            session.add(Filiere(nom=nom_filiere, faculte_id=faculte.id))
    session.commit()
