"""
Detecte et fusionne les cercles nationaux "doublons" : plusieurs
cercles ACTIFS qui representent en realite le MEME parcours national
(meme mention + meme nom de parcours une fois normalise) au meme
niveau, mais qui existent en plusieurs exemplaires parce qu'ils
referencent des lignes Filiere DIFFERENTES — une par universite, la
table Filiere etant scopee sous Faculte/Composante (voir
Filiere.faculte_id dans app/models.py), donc jamais partagee entre
deux universites meme quand il s'agit du meme parcours.

ORIGINE DU PROBLEME (corrigee dans cercles_referentiel.py par la meme
livraison que ce script, pour que le probleme ne revienne pas au
prochain redemarrage) : le provisionnement automatique des cercles
nationaux (assurer_cercles_pour_filiere) cree un cercle par
(mention_id, filiere_id, niveau). Tant qu'une seule universite avait
des Filiere rattachees a une Mention (Toamasina), filiere_id etait de
facto un identifiant national valable. Depuis l'import du referentiel
MESUPRES (scripts/import_academic_data.py), plusieurs universites ont
chacune leur PROPRE ligne Filiere pour ce qui est en realite le meme
parcours (ex: "Finance" a Fianarantsoa ET a Mahajanga, deux Filiere.id
distincts) — le provisionnement automatique a alors cree un cercle
PAR UNIVERSITE au lieu d'un seul cercle national : exactement ce que
le brief refonte academique interdit (§16-18 : "Ne pas creer un cercle
different pour chaque universite... Cela fragmenterait inutilement les
etudiants").

Ce script :
1. Regroupe les cercles ACTIFS par (mention_id, nom de parcours
   normalise, niveau) — la meme cle logique que le cercle national
   AURAIT du avoir depuis le debut.
2. Pour chaque groupe de plus d'un cercle : choisit un survivant
   (celui qui a le plus de membres reels ; a egalite, le plus ancien –
   id le plus petit) et y fusionne tout le contenu des autres
   (adhesions, demandes d'adhesion en attente, messages,
   notifications, theme-du-jour, historique de demandes de creation)
   avant de les ARCHIVER (statut=ARCHIVE — jamais de suppression
   physique, pour rester recuperable, §24 du brief : "les anciennes
   donnees doivent rester recuperables pendant la phase de
   transition").
3. Ne touche jamais un cercle deja ARCHIVE.

Idempotent : un groupe deja fusionne (un seul cercle ACTIF restant)
n'est plus modifie au prochain lancement.

Usage :
    python -m scripts.dedupliquer_cercles_nationaux [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    CercleEtude, DemandeAdhesionCercle, DemandeCreationCercle, Filiere,
    MembreCercle, MessageCercle, Notification, StatutCercle,
    StatutDemandeAdhesion, ThemeDuJour,
)


def normaliser(texte: str | None) -> str:
    """Meme fonction que scripts/import_academic_data.py (dupliquee a
    dessein : ce projet prefere des scripts autonomes plutot que des
    modules partages entre eux pour ce genre d'utilitaire court)."""
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
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
    themes_du_jour_reassignes: int = 0
    demandes_creation_reassignees: int = 0
    cercles_archives: list = field(default_factory=list)

    def imprimer(self) -> None:
        print("\n=== RAPPORT DE DEDUPLICATION DES CERCLES NATIONAUX ===\n")
        print(f"Groupes de doublons trouves et fusionnes : {len(self.groupes_fusionnes)}")
        for cle, survivant_id, perdants_ids in self.groupes_fusionnes:
            _mention_id, nom_parcours, niveau = cle
            print(f"  - [{niveau}] {nom_parcours!r} : survivant #{survivant_id} <- fusion de {perdants_ids}")
        print(f"\nMembres reassignes vers le survivant : {self.membres_reassignes}")
        print(f"Membres deja presents dans le survivant (doublon ignore, rien a faire) : {self.membres_deja_presents_ignores}")
        print(f"Demandes d'adhesion en attente reassignees : {self.demandes_adhesion_reassignees}")
        print(f"Demandes d'adhesion en conflit avec une demande deja existante (rejetees plutot que dupliquees) : {self.demandes_adhesion_conflit_rejetees}")
        print(f"Messages reassignes : {self.messages_reassignes}")
        print(f"Notifications reassignees : {self.notifications_reassignees}")
        print(f"Themes du jour reassignes : {self.themes_du_jour_reassignes}")
        print(f"Demandes de creation (historique) reassignees : {self.demandes_creation_reassignees}")
        print(f"\nCercles archives (doublons, ne seront plus jamais actifs) : {len(self.cercles_archives)}")
        for c in self.cercles_archives:
            print(f"  - #{c}")


def deduplicquer(dry_run: bool = False) -> Rapport:
    rapport = Rapport()

    with Session(engine) as session:
        cercles = session.exec(
            select(CercleEtude).where(
                CercleEtude.statut == StatutCercle.ACTIF,
                CercleEtude.mention_id.is_not(None),
                CercleEtude.filiere_id.is_not(None),
                CercleEtude.niveau.is_not(None),
            )
        ).all()
        filieres_par_id = {f.id: f for f in session.exec(select(Filiere)).all()}

        groupes = defaultdict(list)
        for c in cercles:
            filiere = filieres_par_id.get(c.filiere_id)
            if filiere is None:
                continue
            cle = (c.mention_id, normaliser(filiere.nom), c.niveau)
            groupes[cle].append(c)

        for cle, cercles_du_groupe in groupes.items():
            if len(cercles_du_groupe) < 2:
                continue

            def _nb_membres(cercle):
                return len(session.exec(
                    select(MembreCercle).where(MembreCercle.cercle_id == cercle.id)
                ).all())

            # Survivant = le plus de membres reels ; a egalite, le plus
            # ancien (id le plus petit = cree en premier). Tous les
            # cercles d'un meme groupe recoivent les memes membres admin
            # automatiques (_assurer_membres_admins), donc comparer le
            # nombre TOTAL de membres reste un signal valable de
            # l'engagement etudiant reel au-dela de cette base commune.
            cercles_tries = sorted(cercles_du_groupe, key=lambda c: (-_nb_membres(c), c.id))
            survivant = cercles_tries[0]
            perdants = cercles_tries[1:]

            for perdant in perdants:
                # --- MembreCercle : reassigne, sauf si l'utilisateur est
                #     deja membre du survivant (evite un doublon logique
                #     de membre, meme si aucune contrainte DB ne
                #     l'interdit explicitement). ---
                membres_survivant = {
                    m.utilisateur_id for m in session.exec(
                        select(MembreCercle).where(MembreCercle.cercle_id == survivant.id)
                    ).all()
                }
                for membre in session.exec(select(MembreCercle).where(MembreCercle.cercle_id == perdant.id)).all():
                    if membre.utilisateur_id in membres_survivant:
                        rapport.membres_deja_presents_ignores += 1
                        continue
                    membre.cercle_id = survivant.id
                    if not dry_run:
                        session.add(membre)
                    membres_survivant.add(membre.utilisateur_id)
                    rapport.membres_reassignes += 1

                # --- DemandeAdhesionCercle : reassigne, sauf conflit
                #     avec l'index unique partiel (une seule demande
                #     EN_ATTENTE par (cercle, utilisateur)) — dans ce
                #     cas la demande du perdant est rejetee plutot que
                #     dupliquee (l'utilisateur a deja une demande active
                #     sur le survivant, inutile d'en garder deux). ---
                utilisateurs_en_attente_survivant = {
                    d.utilisateur_id for d in session.exec(
                        select(DemandeAdhesionCercle).where(
                            DemandeAdhesionCercle.cercle_id == survivant.id,
                            DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE,
                        )
                    ).all()
                }
                for demande in session.exec(select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.cercle_id == perdant.id)).all():
                    if (
                        demande.statut == StatutDemandeAdhesion.EN_ATTENTE
                        and demande.utilisateur_id in utilisateurs_en_attente_survivant
                    ):
                        demande.statut = StatutDemandeAdhesion.REJETEE
                        if not dry_run:
                            session.add(demande)
                        rapport.demandes_adhesion_conflit_rejetees += 1
                        continue
                    demande.cercle_id = survivant.id
                    if not dry_run:
                        session.add(demande)
                    if demande.statut == StatutDemandeAdhesion.EN_ATTENTE:
                        utilisateurs_en_attente_survivant.add(demande.utilisateur_id)
                    rapport.demandes_adhesion_reassignees += 1

                # --- MessageCercle, Notification, ThemeDuJour,
                #     DemandeCreationCercle.cercle_cree_id : simple
                #     reassignation, aucune contrainte d'unicite. ---
                for message in session.exec(select(MessageCercle).where(MessageCercle.cercle_id == perdant.id)).all():
                    message.cercle_id = survivant.id
                    if not dry_run:
                        session.add(message)
                    rapport.messages_reassignes += 1

                for notif in session.exec(select(Notification).where(Notification.cercle_id == perdant.id)).all():
                    notif.cercle_id = survivant.id
                    if not dry_run:
                        session.add(notif)
                    rapport.notifications_reassignees += 1

                for theme in session.exec(select(ThemeDuJour).where(ThemeDuJour.cercle_id == perdant.id)).all():
                    theme.cercle_id = survivant.id
                    if not dry_run:
                        session.add(theme)
                    rapport.themes_du_jour_reassignes += 1

                for demande_creation in session.exec(select(DemandeCreationCercle).where(DemandeCreationCercle.cercle_cree_id == perdant.id)).all():
                    demande_creation.cercle_cree_id = survivant.id
                    if not dry_run:
                        session.add(demande_creation)
                    rapport.demandes_creation_reassignees += 1

                perdant.statut = StatutCercle.ARCHIVE
                if not dry_run:
                    session.add(perdant)
                rapport.cercles_archives.append(perdant.id)

            if not dry_run:
                session.commit()

            rapport.groupes_fusionnes.append((cle, survivant.id, [p.id for p in perdants]))

        if dry_run:
            session.rollback()

    return rapport


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="N'ecrit rien en base, affiche seulement ce qui serait fait.")
    args = parser.parse_args()

    rapport = deduplicquer(dry_run=args.dry_run)
    rapport.imprimer()
