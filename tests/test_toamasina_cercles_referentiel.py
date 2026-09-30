"""Audit complet des cercles nationaux derivés du referentiel Toamasina.

Le test reconstruit les 70 offres spécialisées/parcours du fichier source
(les lignes de type "Tronc commun" ne deviennent pas des Filiere) puis
vérifie que le provisionnement automatique produit exactement un cercle
pour chaque combinaison académique réellement offerte, au bon niveau,
dans l'Université de Toamasina.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.cercles_referentiel import assurer_cercles_referentiel
from app.models import (
    CercleEtude,
    Faculte,
    Filiere,
    Mention,
    MembreCercle,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    StatutCercle,
    Universite,
    Utilisateur,
)
from app.referentiel_academique import profil_correspond_au_cercle


SOURCE = Path(__file__).resolve().parents[1] / "mahay_toamasina_referentiel_source.json"


def normaliser(valeur: object) -> str:
    texte = str(valeur or "").strip().replace("’", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).lower()


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(connexion_dbapi, _record):
        connexion_dbapi.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


def charger_source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))["formations"]


def test_tous_les_cercles_toamasina_matchent_une_offre_reelle():
    lignes = charger_source()
    lignes_parcours = [
        ligne for ligne in lignes
        if normaliser(ligne.get("type")) != normaliser("Tronc commun")
    ]

    engine = nouvel_engine()
    with Session(engine) as session:
        admin = Utilisateur(
            nom="Admin audit Toamasina",
            telephone="0340007000",
            mot_de_passe_hash="x",
            role=RoleUtilisateur.ADMIN,
        )
        universite = Universite(nom="Université de Toamasina", ville="Toamasina")
        session.add_all([admin, universite])
        session.commit()
        session.refresh(admin)
        session.refresh(universite)

        facultes = {}
        mentions = {}
        for ligne in lignes_parcours:
            cle_faculte = normaliser(ligne["composante"])
            faculte = facultes.get(cle_faculte)
            if faculte is None:
                faculte = Faculte(
                    nom=ligne["composante"],
                    universite_id=universite.id,
                )
                session.add(faculte)
                session.commit()
                session.refresh(faculte)
                facultes[cle_faculte] = faculte

            cle_mention = normaliser(ligne["mention"])
            mention = mentions.get(cle_mention)
            if mention is None:
                mention = Mention(nom=ligne["mention"])
                session.add(mention)
                session.commit()
                session.refresh(mention)
                mentions[cle_mention] = mention

            filiere = Filiere(
                nom=ligne["parcours"],
                faculte_id=faculte.id,
                mention_id=mention.id,
                niveau=ligne["niveau"],
            )
            session.add(filiere)
            session.commit()
            session.refresh(filiere)
            session.add(
                ProgrammeUniversitaire(
                    universite_id=universite.id,
                    filiere_id=filiere.id,
                    est_active=True,
                )
            )
            session.commit()

        total_crees = assurer_cercles_referentiel(session,)

        cercles = session.exec(
            select(CercleEtude).where(
                CercleEtude.statut == StatutCercle.ACTIF,
                CercleEtude.mention_id.is_not(None),
                CercleEtude.filiere_id.is_not(None),
                CercleEtude.niveau.is_not(None),
            )
        ).all()

        assert len(cercles) == len(lignes_parcours), (
            f"Attendu {len(lignes_parcours)} cercles Toamasina, obtenu {len(cercles)}"
        )
        assert total_crees == len(lignes_parcours)

        filieres = {f.id: f for f in session.exec(select(Filiere)).all()}
        fac_par_id = {f.id: f for f in session.exec(select(Faculte)).all()}
        mention_par_nom = {normaliser(m.nom): m for m in mentions.values()}

        # Couverture exacte : chaque ligne source hors tronc commun doit avoir
        # un cercle au même niveau, avec le même parcours et la même mention.
        attendus = defaultdict(int)
        for ligne in lignes_parcours:
            attendus[
                (
                    normaliser(ligne["mention"]),
                    normaliser(ligne["parcours"]),
                    ligne["niveau"],
                )
            ] += 1

        vus = defaultdict(int)
        for cercle in cercles:
            filiere = filieres[cercle.filiere_id]
            faculte = fac_par_id[filiere.faculte_id]
            mention = session.get(Mention, cercle.mention_id)

            assert faculte.universite_id == universite.id
            assert filiere.mention_id == cercle.mention_id
            assert filiere.niveau == cercle.niveau
            assert mention is not None

            programme = session.exec(
                select(ProgrammeUniversitaire).where(
                    ProgrammeUniversitaire.universite_id == universite.id,
                    ProgrammeUniversitaire.filiere_id == filiere.id,
                    ProgrammeUniversitaire.est_active == True,  # noqa: E712
                )
            ).first()
            assert programme is not None

            vus[
                (
                    normaliser(mention.nom),
                    normaliser(filiere.nom),
                    cercle.niveau,
                )
            ] += 1

            etudiant = Utilisateur(
                nom="Profil audit",
                telephone=f"0340007{cercle.id:03d}",
                mot_de_passe_hash="x",
                role=__import__("app.models", fromlist=["RoleUtilisateur"]).RoleUtilisateur.ETUDIANT,
                universite_id=universite.id,
                faculte_id=faculte.id,
                mention_id=mention.id,
                filiere_id=filiere.id,
                niveau=cercle.niveau,
            )
            session.add(etudiant)
            session.commit()
            session.refresh(etudiant)

            assert profil_correspond_au_cercle(etudiant, cercle, session)

        assert dict(vus) == dict(attendus)

        # Un "Tronc commun" ne doit jamais être transforme par erreur en
        # cercle de parcours.
        assert all(
            normaliser(filieres[c.filiere_id].nom) != normaliser("Tronc commun")
            for c in cercles
        )
