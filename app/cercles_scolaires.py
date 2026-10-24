"""Synchronisation sûre des cercles du référentiel scolaire.

Le catalogue scolaire et universitaire reste séparé dans le modèle et dans
les identifiants. Ce service provisionne uniquement les cibles scolaires
actives et vérifiées, et se rejoue sans créer de doublons.

Cibles automatiques :
- un cercle national général par classe validée ;
- un cercle par série/option validée ;
- un cercle matière par combinaison classe/série-matière dont le rattachement
  de programme a été vérifié.

Les cercles locaux d'établissement ne sont pas devinés : le modèle actuel ne
décrit pas encore les classes réellement offertes par chaque établissement.
Les cercles manuels, transversaux et universitaires ne sont jamais gérés ici.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, func, select

from .models import (
    CercleEtude,
    DemandeAdhesionCercle,
    DemandeCreationCercle,
    Document,
    EtablissementScolaire,
    MatiereScolaire,
    MessageCercle,
    MembreCercle,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleMembreCercle,
    RoleUtilisateur,
    StatutCercle,
    Utilisateur,
)

logger = logging.getLogger("mahay.cercles_scolaires")
CYCLES_SCOLAIRES = {"college", "lycee"}


def _libelle_cycle(cycle: str) -> str:
    return "Collège" if cycle == "college" else "Lycée"


def _option_valide(
    session: Session,
    option: OptionScolaire,
    *,
    referentiel_id: int,
    niveau_id: int,
    options_valides: dict[int, OptionScolaire],
) -> bool:
    if (
        option.referentiel_id != referentiel_id
        or option.niveau_id != niveau_id
        or not option.est_active
        or option.statut_validation != "verifie"
    ):
        return False
    if option.parent_option_id is None:
        return True
    parent = options_valides.get(option.parent_option_id)
    return bool(
        parent
        and parent.parent_option_id is None
        and parent.referentiel_id == referentiel_id
        and parent.niveau_id == niveau_id
        and parent.est_active
        and parent.statut_validation == "verifie"
    )


def _options_compatibles(
    session: Session,
    referentiel_id: int,
    niveaux_valides: dict[int, NiveauScolaire],
) -> dict[int, OptionScolaire]:
    toutes = session.exec(
        select(OptionScolaire).where(
            OptionScolaire.referentiel_id == referentiel_id,
            OptionScolaire.est_active == True,  # noqa: E712
            OptionScolaire.statut_validation == "verifie",
        )
    ).all()
    options_par_id = {option.id: option for option in toutes if option.id is not None}
    return {
        option.id: option
        for option in toutes
        if option.id is not None
        and option.niveau_id in niveaux_valides
        and _option_valide(
            session,
            option,
            referentiel_id=referentiel_id,
            niveau_id=option.niveau_id,
            options_valides=options_par_id,
        )
    }


def _construire_cibles_scolaires(
    session: Session,
    referentiel: ReferentielScolaire,
) -> dict[tuple[Optional[int], Optional[int], Optional[int], Optional[int]], dict]:
    """Construit les identités cibles sans utiliser de nom comme identifiant."""
    niveaux = session.exec(
        select(NiveauScolaire).where(
            NiveauScolaire.referentiel_id == referentiel.id,
            NiveauScolaire.est_actif == True,  # noqa: E712
            NiveauScolaire.statut_validation == "verifie",
            NiveauScolaire.cycle.in_(CYCLES_SCOLAIRES),
        ).order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
    ).all()
    niveaux_valides = {n.id: n for n in niveaux if n.id is not None}
    if not niveaux_valides:
        return {}

    options_valides = _options_compatibles(session, referentiel.id, niveaux_valides)
    matieres = session.exec(
        select(MatiereScolaire).where(
            MatiereScolaire.est_active == True,  # noqa: E712
            MatiereScolaire.statut_validation == "verifie",
        )
    ).all()
    matieres_valides = {m.id: m for m in matieres if m.id is not None}
    etablissements_valides = {
        e.id: e for e in session.exec(
            select(EtablissementScolaire).where(
                EtablissementScolaire.est_actif == True,  # noqa: E712
                EtablissementScolaire.est_verifie == True,  # noqa: E712
            )
        ).all() if e.id is not None
    }

    cibles: dict[
        tuple[Optional[int], Optional[int], Optional[int], Optional[int]], dict
    ] = {}

    def ajouter(
        niveau: NiveauScolaire,
        option: Optional[OptionScolaire],
        matiere: Optional[MatiereScolaire],
        *,
        source: Optional[str] = None,
    ) -> None:
        # Aucun cercle local n'est généré sans preuve qu'un établissement
        # dispense effectivement cette classe. Les cercles locaux peuvent
        # toujours être demandés par l'interface et restent soumis à validation.
        cle = (
            niveau.id,
            option.id if option else None,
            None,
            matiere.id if matiere else None,
        )
        cycle = _libelle_cycle(niveau.cycle)
        parties = [cycle, niveau.libelle]
        if option:
            parent = options_valides.get(option.parent_option_id) if option.parent_option_id else None
            parties.append(parent.libelle if parent else option.libelle)
            if parent:
                parties.append(option.libelle)
        if matiere:
            parties.append(matiere.libelle)
        else:
            parties.append("Cercle national")
        nom = " — ".join(parties)[:180]
        raison = [
            "Cercle scolaire national synchronisé depuis le référentiel vérifié.",
            f"Cycle : {niveau.cycle}.",
            f"Classe : {niveau.libelle}.",
        ]
        if option:
            raison.append(f"Série/option : {option.libelle}.")
        if matiere:
            raison.append(f"Matière : {matiere.libelle}.")
        if source:
            raison.append(f"Source programme : {source}.")
        cibles[cle] = {
            "niveau": niveau,
            "option": option,
            "etablissement": None,
            "matiere": matiere,
            "nom": nom,
            "description": " ".join(raison),
        }

    # Le cercle de classe reste disponible même lorsque la classe ne possède
    # aucune série vérifiée ou que le catalogue des matières est incomplet.
    for niveau in niveaux_valides.values():
        ajouter(niveau, None, None)

    for option in options_valides.values():
        niveau = niveaux_valides.get(option.niveau_id)
        if niveau:
            ajouter(niveau, option, None, source=option.source_officielle)

    programmes = session.exec(
        select(ProgrammeMatiereScolaire).where(
            ProgrammeMatiereScolaire.referentiel_id == referentiel.id,
            ProgrammeMatiereScolaire.statut_validation == "verifie",
        )
    ).all()
    for programme in programmes:
        niveau = niveaux_valides.get(programme.niveau_id)
        matiere = matieres_valides.get(programme.matiere_id)
        option = options_valides.get(programme.option_id) if programme.option_id else None
        if not niveau or not matiere:
            continue
        if programme.option_id is not None and not option:
            continue
        if option and option.niveau_id != niveau.id:
            continue
        # Une association sans option décrit le programme général d'une
        # classe ; une association ciblée reste dans le cercle de cette série.
        ajouter(niveau, option, matiere, source=programme.source_officielle)

    return cibles


def _conditions_cible(cle: tuple[Optional[int], Optional[int], Optional[int], Optional[int]]) -> list:
    niveau_id, option_id, etablissement_id, matiere_id = cle
    return [
        CercleEtude.portee_academique == "scolaire",
        CercleEtude.niveau_scolaire_id == niveau_id,
        CercleEtude.option_scolaire_id.is_(None) if option_id is None else CercleEtude.option_scolaire_id == option_id,
        CercleEtude.etablissement_scolaire_id.is_(None) if etablissement_id is None else CercleEtude.etablissement_scolaire_id == etablissement_id,
        CercleEtude.matiere_scolaire_id.is_(None) if matiere_id is None else CercleEtude.matiere_scolaire_id == matiere_id,
    ]


def _a_contenu_important(session: Session, cercle_id: int) -> bool:
    for modele in (MessageCercle, Document, DemandeAdhesionCercle):
        if session.exec(
            select(modele.id).where(modele.cercle_id == cercle_id).limit(1)
        ).first() is not None:
            return True
    return session.exec(
        select(DemandeCreationCercle.id).where(
            DemandeCreationCercle.cercle_cree_id == cercle_id
        ).limit(1)
    ).first() is not None


def _nb_membres_non_admin(session: Session, cercle_id: int) -> int:
    return int(session.exec(
        select(func.count())
        .select_from(MembreCercle)
        .join(Utilisateur, Utilisateur.id == MembreCercle.utilisateur_id)
        .where(
            MembreCercle.cercle_id == cercle_id,
            Utilisateur.role != RoleUtilisateur.ADMIN,
        )
    ).one())


def assurer_cercles_scolaires(session: Session) -> dict[str, int | str | None]:
    """Réconcilie les cercles gérés automatiquement avec le catalogue vérifié.

    La fonction est idempotente. Elle ne supprime jamais un cercle. Les cibles
    devenues invalides ne sont archivées que si elles sont gérées par ce service
    et n'ont ni membres non-administrateurs ni contenu important.
    """
    referentiel = session.exec(
        select(ReferentielScolaire).order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).first()
    if not referentiel:
        return {
            "referentiel_id": None, "cibles": 0, "crees": 0,
            "reactives": 0, "archives": 0, "preserves": 0, "existants": 0,
        }
    admin = session.exec(
        select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)
        .order_by(Utilisateur.id).limit(1)
    ).first()
    if not admin:
        logger.warning("Synchronisation scolaire reportée : aucun compte admin créateur.")
        return {
            "referentiel_id": referentiel.id, "cibles": 0, "crees": 0,
            "reactives": 0, "archives": 0, "preserves": 0, "existants": 0,
        }

    cibles = _construire_cibles_scolaires(session, referentiel)
    stats: dict[str, int | str | None] = {
        "referentiel_id": referentiel.id,
        "cibles": len(cibles),
        "crees": 0,
        "reactives": 0,
        "archives": 0,
        "preserves": 0,
        "existants": 0,
    }
    clefs_cibles = set(cibles)

    for cle, cible in cibles.items():
        conditions = _conditions_cible(cle)
        actifs = session.exec(
            select(CercleEtude).where(
                *conditions,
                CercleEtude.statut == StatutCercle.ACTIF,
            ).order_by(CercleEtude.id)
        ).all()
        if actifs:
            # Un cercle créé manuellement peut déjà représenter cette cible.
            # On le conserve tel quel : on ne revendique pas son cycle de vie.
            stats["existants"] = int(stats["existants"]) + 1
            continue

        archives = session.exec(
            select(CercleEtude).where(
                *conditions,
                CercleEtude.statut == StatutCercle.ARCHIVE,
                CercleEtude.synchronise_referentiel == True,  # noqa: E712
            ).order_by(CercleEtude.id.desc())
        ).all()
        cercle = archives[0] if archives else None
        if cercle:
            cercle.statut = StatutCercle.ACTIF
            session.add(cercle)
            try:
                session.commit()
            except Exception:
                session.rollback()
                # Un autre processus a pu provisionner la même cible pendant
                # le contrôle. On n'échoue pas le démarrage pour cette course.
                if session.exec(
                    select(CercleEtude.id).where(
                        *conditions,
                        CercleEtude.statut == StatutCercle.ACTIF,
                    ).limit(1)
                ).first() is None:
                    raise
                continue
            stats["reactives"] = int(stats["reactives"]) + 1
            continue

        cercle = CercleEtude(
            nom=cible["nom"],
            description=cible["description"],
            portee_academique="scolaire",
            niveau_scolaire_id=cible["niveau"].id,
            option_scolaire_id=cible["option"].id if cible["option"] else None,
            etablissement_scolaire_id=None,
            matiere_scolaire_id=cible["matiere"].id if cible["matiere"] else None,
            synchronise_referentiel=True,
            statut=StatutCercle.ACTIF,
            createur_id=admin.id,
        )
        session.add(cercle)
        try:
            session.commit()
            session.refresh(cercle)
        except Exception:
            session.rollback()
            # Une autre instance peut avoir créé la même cible : vérifie
            # le résultat plutôt que de faire échouer l'initialisation.
            concurrent = session.exec(
                select(CercleEtude.id).where(
                    *conditions,
                    CercleEtude.statut == StatutCercle.ACTIF,
                ).limit(1)
            ).first()
            if concurrent is None:
                raise
            continue

        # Le créateur technique est administrateur et ne compte pas comme
        # membre réel lors de la réconciliation/archivage.
        session.add(MembreCercle(
            cercle_id=cercle.id,
            utilisateur_id=admin.id,
            role=RoleMembreCercle.CREATEUR,
        ))
        session.commit()
        stats["crees"] = int(stats["crees"]) + 1

    # N'archive que les cercles scolaires gérés par ce synchroniseur. Un
    # cercle manuel n'est jamais archivé parce qu'un programme est modifié.
    cercles_gérés = session.exec(
        select(CercleEtude).where(
            CercleEtude.portee_academique == "scolaire",
            CercleEtude.synchronise_referentiel == True,  # noqa: E712
            CercleEtude.statut == StatutCercle.ACTIF,
        )
    ).all()
    for cercle in cercles_gérés:
        cle = (
            cercle.niveau_scolaire_id,
            cercle.option_scolaire_id,
            cercle.etablissement_scolaire_id,
            cercle.matiere_scolaire_id,
        )
        if cle in clefs_cibles:
            continue
        if _nb_membres_non_admin(session, cercle.id) or _a_contenu_important(session, cercle.id):
            stats["preserves"] = int(stats["preserves"]) + 1
            continue
        cercle.statut = StatutCercle.ARCHIVE
        session.add(cercle)
        session.commit()
        stats["archives"] = int(stats["archives"]) + 1

    logger.info(
        "Synchronisation cercles scolaires: ref=%s cibles=%s crees=%s reactives=%s archives=%s preserves=%s existants=%s",
        stats["referentiel_id"], stats["cibles"], stats["crees"],
        stats["reactives"], stats["archives"], stats["preserves"], stats["existants"],
    )
    return stats
