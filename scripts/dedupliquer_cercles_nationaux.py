"""
Audit, réorganisation et déduplication des Cercles d'étude.

Identité canonique :
- cercle libre : aucun attribut académique ;
- tronc commun : (mention, niveau), sans parcours ;
- parcours national : (mention, nom de parcours normalisé, niveau).

La table Filiere reste locale à une université/composante. Elle ne doit donc
jamais servir seule d'identifiant national du cercle.

Le maintenanceur :
1. détecte les doublons nationaux, y compris lorsqu'ils utilisent des
   Filiere.id différentes pour le même parcours ;
2. transforme les anciens pseudo-cercles nommés "Tronc commun" en vrais
   cercles de tronc commun ;
3. fusionne le contenu dans un survivant déterministe ;
4. archive les doublons et les cercles académiques incohérents qui n'ont
   aucun membre réel ni contenu à préserver ;
5. conserve les cercles suspects contenant des utilisateurs/messages et les
   signale dans le rapport au lieu de prendre une décision destructive ;
6. fonctionne en mode idempotent et dry-run.

Le moteur est lancé au démarrage de l'application. Les archives ne sont jamais
supprimées automatiquement.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    CercleEtude,
    DemandeAdhesionCercle,
    DemandeCreationCercle,
    Document,
    Faculte,
    Filiere,
    MembreCercle,
    MessageCercle,
    Mention,
    Notification,
    ProgrammeUniversitaire,
    RoleMembreCercle,
    RoleUtilisateur,
    StatutCercle,
    StatutDemandeAdhesion,
    ThemeDuJour,
    Universite,
    Utilisateur,
)
from app.referentiel import NIVEAUX  # noqa: E402


def normaliser(texte: str | None) -> str:
    """Même comparaison que app.texte_normalise.normaliser()."""
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
    texte = re.sub(r"\s*&\s*", " et ", texte)
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"\s+", " ", texte)
    return texte.lower()


@dataclass
class Rapport:
    groupes_fusionnes: list = field(default_factory=list)
    membres_reassignes: int = 0
    membres_deja_presents_ignores: int = 0
    demandes_adhesion_reassignees: int = 0
    demandes_adhesion_conflit_rejetees: int = 0
    messages_reassignes: int = 0
    notifications_reassignees: int = 0
    documents_reassignes: int = 0
    themes_du_jour_reassignes: int = 0
    themes_du_jour_desassocies: int = 0
    demandes_creation_reassignees: int = 0
    cercles_archives: list = field(default_factory=list)
    cercles_suspects: list = field(default_factory=list)
    pseudo_tronc_normalises: int = 0

    def imprimer(self) -> None:
        print("\n=== AUDIT / REORGANISATION DES CERCLES ===\n")
        print(f"Groupes de doublons fusionnés : {len(self.groupes_fusionnes)}")
        for cle, survivant_id, perdants_ids in self.groupes_fusionnes:
            nature, mention_id, nom_parcours, niveau = cle
            libelle = "Tronc commun" if nature == "tronc" else repr(nom_parcours)
            print(f"  - [{niveau}] mention #{mention_id} / {libelle} : #{survivant_id} <- {perdants_ids}")
        print(f"Membres réassignés : {self.membres_reassignes}")
        print(f"Doublons de membres supprimés : {self.membres_deja_presents_ignores}")
        print(f"Demandes d'adhésion réassignées : {self.demandes_adhesion_reassignees}")
        print(f"Demandes d'adhésion conflictuelles rejetées : {self.demandes_adhesion_conflit_rejetees}")
        print(f"Messages réassignés : {self.messages_reassignes}")
        print(f"Notifications réassignées : {self.notifications_reassignees}")
        print(f"Documents réattachés : {self.documents_reassignes}")
        print(f"Themes du jour réattachés : {self.themes_du_jour_reassignes}")
        print(f"Themes du jour désassociés en cas de conflit : {self.themes_du_jour_desassocies}")
        print(f"Demandes de création historiques réassignées : {self.demandes_creation_reassignees}")
        print(f"Pseudo-tronc normalisés : {self.pseudo_tronc_normalises}")
        print(f"Cercles archivés : {len(self.cercles_archives)}")
        if self.cercles_archives:
            print("  " + ", ".join(f"#{cid}" for cid in self.cercles_archives))
        print(f"Cercles suspects conservés pour revue : {len(self.cercles_suspects)}")
        for item in self.cercles_suspects:
            print(f"  - #{item['id']} : {item['raison']}")


@dataclass
class _Contexte:
    filieres: dict[int, Filiere]
    mentions: dict[int, Mention]
    facultes: dict[int, Faculte]
    programmes_actifs: set[tuple[int, int]]
    utilisateurs: dict[int, Utilisateur]
    nb_membres_reels: dict[int, int]
    nb_messages: dict[int, int]


def _charger_contexte(session: Session, cercles: list[CercleEtude]) -> _Contexte:
    filieres = {
        f.id: f
        for f in session.exec(select(Filiere)).all()
        if f.id is not None
    }
    mentions = {
        m.id: m
        for m in session.exec(select(Mention)).all()
        if m.id is not None
    }
    facultes = {
        f.id: f
        for f in session.exec(select(Faculte)).all()
        if f.id is not None
    }
    programmes_actifs = {
        (p.universite_id, p.filiere_id)
        for p in session.exec(
            select(ProgrammeUniversitaire).where(ProgrammeUniversitaire.est_active == True)  # noqa: E712
        ).all()
    }
    utilisateurs = {
        u.id: u
        for u in session.exec(select(Utilisateur)).all()
        if u.id is not None
    }

    ids = [c.id for c in cercles if c.id is not None]
    nb_membres_reels = {}
    if ids:
        lignes = session.exec(
            select(MembreCercle.cercle_id, MembreCercle.utilisateur_id)
            .where(MembreCercle.cercle_id.in_(ids))
        ).all()
        for cercle_id, utilisateur_id in lignes:
            utilisateur = utilisateurs.get(utilisateur_id)
            if utilisateur and utilisateur.role != RoleUtilisateur.ADMIN:
                nb_membres_reels[cercle_id] = nb_membres_reels.get(cercle_id, 0) + 1

    nb_messages = {}
    if ids:
        for cercle_id, nb in session.exec(
            select(MessageCercle.cercle_id, func.count())
            .where(MessageCercle.cercle_id.in_(ids))
            .group_by(MessageCercle.cercle_id)
        ).all():
            nb_messages[cercle_id] = nb

    return _Contexte(
        filieres=filieres,
        mentions=mentions,
        facultes=facultes,
        programmes_actifs=programmes_actifs,
        utilisateurs=utilisateurs,
        nb_membres_reels=nb_membres_reels,
        nb_messages=nb_messages,
    )


def _universite_id_de_filiere(contexte: _Contexte, filiere: Filiere) -> Optional[int]:
    faculte = contexte.facultes.get(filiere.faculte_id)
    return faculte.universite_id if faculte else None


def _offre_active_filiere(contexte: _Contexte, filiere: Filiere) -> bool:
    universite_id = _universite_id_de_filiere(contexte, filiere)
    return bool(
        universite_id is not None
        and (universite_id, filiere.id) in contexte.programmes_actifs
    )


def _cle_canonique(
    cercle: CercleEtude,
    contexte: _Contexte,
) -> tuple[tuple, Optional[str]]:
    """Renvoie (clé, raison_suspicion). None comme clé = incomplet non publiable."""
    if not cercle.mention_id and not cercle.filiere_id and not cercle.niveau:
        return ("libre", cercle.id), None

    # Un niveau est obligatoire pour toute identité académique nationale.
    if not cercle.mention_id or not cercle.niveau:
        return ("incomplet", cercle.id), "profil académique partiel (mention/niveau manquant)"

    if cercle.niveau not in NIVEAUX:
        return ("incomplet", cercle.id), f"niveau invalide : {cercle.niveau!r}"

    mention = contexte.mentions.get(cercle.mention_id)
    if not mention:
        return ("incomplet", cercle.id), "mention inexistante"
    if not mention.est_active:
        return ("incomplet", cercle.id), "mention inactive"

    # Vrai tronc commun : il ne porte aucune Filiere technique.
    if cercle.filiere_id is None:
        return ("tronc", cercle.mention_id, None, cercle.niveau), None

    filiere = contexte.filieres.get(cercle.filiere_id)
    if not filiere:
        return ("incomplet", cercle.id), "parcours inexistant"

    nom_normalise = normaliser(filiere.nom)

    # Legacy fréquent : un ancien cercle avait pris "Tronc commun" comme
    # Filiere alors que le modèle canonique le représente par mention+niveau.
    if nom_normalise == "tronc commun":
        return ("tronc", cercle.mention_id, None, cercle.niveau), None

    if filiere.mention_id != cercle.mention_id:
        return ("incomplet", cercle.id), "mention du cercle différente de celle du parcours"

    if filiere.niveau and filiere.niveau != cercle.niveau:
        return ("incomplet", cercle.id), "niveau du cercle différent du niveau explicite du parcours"

    if not _offre_active_filiere(contexte, filiere):
        return ("incomplet", cercle.id), "aucune offre universitaire active pour ce parcours"

    if not nom_normalise:
        return ("incomplet", cercle.id), "nom de parcours vide après normalisation"

    return ("parcours", cercle.mention_id, nom_normalise, cercle.niveau), None


def _est_contenu_important(session: Session, cercle_id: int) -> bool:
    if session.exec(
        select(MessageCercle.id).where(MessageCercle.cercle_id == cercle_id).limit(1)
    ).first():
        return True
    if session.exec(
        select(Document.id).where(Document.cercle_id == cercle_id).limit(1)
    ).first():
        return True
    if session.exec(
        select(DemandeAdhesionCercle.id).where(DemandeAdhesionCercle.cercle_id == cercle_id).limit(1)
    ).first():
        return True
    return False


def _fusionner_membres(
    session: Session,
    survivant: CercleEtude,
    perdant: CercleEtude,
    rapport: Rapport,
    dry_run: bool,
) -> None:
    membres_survivant = {
        m.utilisateur_id: m
        for m in session.exec(
            select(MembreCercle).where(MembreCercle.cercle_id == survivant.id)
        ).all()
    }

    for membre in session.exec(
        select(MembreCercle).where(MembreCercle.cercle_id == perdant.id)
    ).all():
        deja = membres_survivant.get(membre.utilisateur_id)
        if deja:
            rapport.membres_deja_presents_ignores += 1
            if not dry_run:
                session.delete(membre)
            continue

        if membre.utilisateur_id != survivant.createur_id and membre.role == RoleMembreCercle.CREATEUR:
            membre.role = RoleMembreCercle.MEMBRE

        if not dry_run:
            membre.cercle_id = survivant.id
            session.add(membre)
        membres_survivant[membre.utilisateur_id] = membre
        rapport.membres_reassignes += 1

    # Le propriétaire du cercle fusionné reste joignable sur le survivant.
    if (
        perdant.createur_id
        and perdant.createur_id != survivant.createur_id
        and perdant.createur_id not in membres_survivant
    ):
        if not dry_run:
            session.add(
                MembreCercle(
                    cercle_id=survivant.id,
                    utilisateur_id=perdant.createur_id,
                    role=RoleMembreCercle.MEMBRE,
                )
            )
        rapport.membres_reassignes += 1


def _fusionner_demandes_adhesion(
    session: Session,
    survivant: CercleEtude,
    perdant: CercleEtude,
    rapport: Rapport,
    dry_run: bool,
) -> None:
    attentes = {
        d.utilisateur_id
        for d in session.exec(
            select(DemandeAdhesionCercle).where(
                DemandeAdhesionCercle.cercle_id == survivant.id,
                DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE,
            )
        ).all()
    }

    for demande in session.exec(
        select(DemandeAdhesionCercle).where(
            DemandeAdhesionCercle.cercle_id == perdant.id
        )
    ).all():
        if (
            demande.statut == StatutDemandeAdhesion.EN_ATTENTE
            and demande.utilisateur_id in attentes
        ):
            if not dry_run:
                demande.statut = StatutDemandeAdhesion.REJETEE
                session.add(demande)
            rapport.demandes_adhesion_conflit_rejetees += 1
            continue

        if not dry_run:
            demande.cercle_id = survivant.id
            session.add(demande)
        if demande.statut == StatutDemandeAdhesion.EN_ATTENTE:
            attentes.add(demande.utilisateur_id)
        rapport.demandes_adhesion_reassignees += 1


def _fusionner_dependances(
    session: Session,
    survivant: CercleEtude,
    perdant: CercleEtude,
    rapport: Rapport,
    dry_run: bool,
) -> None:
    for message in session.exec(
        select(MessageCercle).where(MessageCercle.cercle_id == perdant.id)
    ).all():
        if not dry_run:
            message.cercle_id = survivant.id
            session.add(message)
        rapport.messages_reassignes += 1

    for notification in session.exec(
        select(Notification).where(Notification.cercle_id == perdant.id)
    ).all():
        if not dry_run:
            notification.cercle_id = survivant.id
            session.add(notification)
        rapport.notifications_reassignees += 1

    for document in session.exec(
        select(Document).where(Document.cercle_id == perdant.id)
    ).all():
        if not dry_run:
            document.cercle_id = survivant.id
            session.add(document)
        rapport.documents_reassignes += 1

    dates_survivant = {
        t.date_jour
        for t in session.exec(
            select(ThemeDuJour).where(ThemeDuJour.cercle_id == survivant.id)
        ).all()
    }
    for theme in session.exec(
        select(ThemeDuJour).where(ThemeDuJour.cercle_id == perdant.id)
    ).all():
        if theme.date_jour in dates_survivant:
            if not dry_run:
                theme.cercle_id = None
                session.add(theme)
            rapport.themes_du_jour_desassocies += 1
            continue
        if not dry_run:
            theme.cercle_id = survivant.id
            session.add(theme)
        dates_survivant.add(theme.date_jour)
        rapport.themes_du_jour_reassignes += 1

    for demande_creation in session.exec(
        select(DemandeCreationCercle).where(
            DemandeCreationCercle.cercle_cree_id == perdant.id
        )
    ).all():
        if not dry_run:
            demande_creation.cercle_cree_id = survivant.id
            session.add(demande_creation)
        rapport.demandes_creation_reassignees += 1


def _fusionner_groupe(
    session: Session,
    cle: tuple,
    cercles_du_groupe: list[CercleEtude],
    contexte: _Contexte,
    rapport: Rapport,
    dry_run: bool,
) -> None:
    def score(c: CercleEtude) -> tuple:
        nature, _mention, nom, niveau = cle
        valide = 0
        offre = 0
        if nature == "tronc":
            valide = 1
        else:
            filiere = contexte.filieres.get(c.filiere_id)
            if filiere:
                valide = 1 if (
                    filiere.mention_id == c.mention_id
                    and (not filiere.niveau or filiere.niveau == c.niveau)
                    and _offre_active_filiere(contexte, filiere)
                ) else 0
                offre = 1 if _offre_active_filiere(contexte, filiere) else 0
        return (
            valide,
            offre,
            contexte.nb_membres_reels.get(c.id, 0),
            contexte.nb_messages.get(c.id, 0),
            -c.id,
        )

    survivant = max(cercles_du_groupe, key=score)
    perdants = [c for c in cercles_du_groupe if c.id != survivant.id]

    if cle[0] == "tronc":
        nb_pseudo_tronc = sum(
            1
            for c in cercles_du_groupe
            if c.filiere_id is not None
            and (
                contexte.filieres.get(c.filiere_id)
                and normaliser(contexte.filieres[c.filiere_id].nom) == "tronc commun"
            )
        )
        if not dry_run:
            survivant.filiere_id = None
            session.add(survivant)
        rapport.pseudo_tronc_normalises += nb_pseudo_tronc
    else:
        # Un cercle national doit pointer vers une Filiere représentative
        # qui a une offre active. On garde l'ID le plus petit parmi les
        # représentantes admissibles pour rendre le résultat stable.
        candidates = [
            f for f in contexte.filieres.values()
            if f.mention_id == cle[1]
            and normaliser(f.nom) == cle[2]
            and _offre_active_filiere(contexte, f)
            and (not f.niveau or f.niveau == cle[3])
        ]
        if candidates:
            filiere_canonique = min(candidates, key=lambda f: f.id)
            if not dry_run:
                survivant.filiere_id = filiere_canonique.id
                session.add(survivant)

    for perdant in perdants:
        _fusionner_membres(session, survivant, perdant, rapport, dry_run)
        _fusionner_demandes_adhesion(session, survivant, perdant, rapport, dry_run)
        _fusionner_dependances(session, survivant, perdant, rapport, dry_run)

        if not dry_run:
            perdant.statut = StatutCercle.ARCHIVE
            session.add(perdant)
        rapport.cercles_archives.append(perdant.id)

    if not dry_run:
        session.commit()

    rapport.groupes_fusionnes.append(
        (cle, survivant.id, [p.id for p in perdants])
    )


def _archiver_suspect_si_possible(
    session: Session,
    cercle: CercleEtude,
    raison: str,
    contexte: _Contexte,
    rapport: Rapport,
    dry_run: bool,
) -> None:
    if contexte.nb_membres_reels.get(cercle.id, 0) > 0 or _est_contenu_important(session, cercle.id):
        rapport.cercles_suspects.append({
            "id": cercle.id,
            "raison": f"{raison} — conservé car il contient un membre réel ou du contenu",
        })
        return

    if not dry_run:
        cercle.statut = StatutCercle.ARCHIVE
        session.add(cercle)
        session.commit()
    rapport.cercles_archives.append(cercle.id)


def deduplicquer(session: Optional[Session] = None, dry_run: bool = False) -> Rapport:
    """Audit et fusion des cercles ACTIFS. Idempotent."""
    rapport = Rapport()
    session_a_fermer = session is None
    if session is None:
        session = Session(engine)

    try:
        cercles = session.exec(
            select(CercleEtude).where(CercleEtude.statut == StatutCercle.ACTIF)
        ).all()
        contexte = _charger_contexte(session, cercles)

        groupes: dict[tuple, list[CercleEtude]] = defaultdict(list)
        for cercle in cercles:
            cle, suspicion = _cle_canonique(cercle, contexte)

            if cle[0] == "incomplet":
                _archiver_suspect_si_possible(
                    session, cercle, suspicion or "cercle incohérent", contexte, rapport, dry_run
                )
                continue

            # Les cercles libres ne sont pas fusionnés : plusieurs groupes
            # libres peuvent être légitimes, car leur identité n'est pas
            # académique.
            if cle[0] == "libre":
                continue

            groupes[cle].append(cercle)

        for cle, cercles_du_groupe in groupes.items():
            # Une seule instance active par identité nationale.
            if len(cercles_du_groupe) >= 2:
                _fusionner_groupe(
                    session, cle, cercles_du_groupe, contexte, rapport, dry_run
                )
                continue

            cercle = cercles_du_groupe[0]

            # Un pseudo-tronc isolé devient un vrai tronc commun.
            if cle[0] == "tronc" and cercle.filiere_id is not None:
                if not dry_run:
                    cercle.filiere_id = None
                    session.add(cercle)
                    session.commit()
                rapport.pseudo_tronc_normalises += 1
                continue

            # Représentante canonique pour un cercle parcours unique.
            if cle[0] == "parcours":
                candidates = [
                    f for f in contexte.filieres.values()
                    if f.mention_id == cle[1]
                    and normaliser(f.nom) == cle[2]
                    and _offre_active_filiere(contexte, f)
                    and (not f.niveau or f.niveau == cle[3])
                ]
                if candidates:
                    fid_canonique = min(candidates, key=lambda f: f.id).id
                    if cercle.filiere_id != fid_canonique and not dry_run:
                        cercle.filiere_id = fid_canonique
                        session.add(cercle)

        if not dry_run:
            session.commit()

        if dry_run:
            session.rollback()
    finally:
        if session_a_fermer:
            session.close()

    return rapport


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="n'écrit rien en base et affiche seulement le rapport",
    )
    args = parser.parse_args()

    deduplicquer(dry_run=args.dry_run).imprimer()
