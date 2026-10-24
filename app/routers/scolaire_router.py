"""API publique en lecture du référentiel scolaire versionné.

Les options non vérifiées ne sont jamais proposées comme un choix officiel.
Le catalogue indique explicitement quand l'inventaire est partiel.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, or_, select

from ..database import get_session
from ..models import (
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
)

router = APIRouter(prefix="/api/scolaire", tags=["référentiel scolaire"])


def _referentiel_actif(session: Session) -> Optional[ReferentielScolaire]:
    """Dernière version importée ; les anciennes versions restent consultables."""
    rows = session.exec(
        select(ReferentielScolaire)
        .order_by(ReferentielScolaire.date_creation.desc(), ReferentielScolaire.id.desc())
    ).all()
    return rows[0] if rows else None


def _donnees_niveau(niveau: NiveauScolaire) -> dict:
    return {
        "id": niveau.id,
        "code": niveau.code,
        "libelle": niveau.libelle,
        "cycle": niveau.cycle,
        "ordre": niveau.ordre,
        "source_officielle": niveau.source_officielle,
    }


def _donnees_option(option: OptionScolaire, toutes_options: list[OptionScolaire]) -> dict:
    parents = {item.id: item for item in toutes_options}
    parent = parents.get(option.parent_option_id) if option.parent_option_id else None
    libelle_affiche = f"{parent.libelle} → {option.libelle}" if parent else option.libelle
    return {
        "id": option.id,
        "code": option.code,
        "libelle": option.libelle,
        "libelle_affiche": libelle_affiche,
        "type_option": option.type_option,
        "parent_option_id": option.parent_option_id,
        "source_officielle": option.source_officielle,
    }


@router.get("/referentiel")
def obtenir_referentiel_scolaire(session: Session = Depends(get_session)):
    referentiel = _referentiel_actif(session)
    if not referentiel:
        return {
            "version": None,
            "complet": False,
            "message": "Le catalogue scolaire n'est pas encore initialisé.",
            "sources": [],
            "niveaux": [],
        }

    niveaux = session.exec(
        select(NiveauScolaire)
        .where(
            NiveauScolaire.referentiel_id == referentiel.id,
            NiveauScolaire.est_actif == True,  # noqa: E712
            NiveauScolaire.statut_validation == "verifie",
        )
        .order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
    ).all()

    resultats = []
    for niveau in niveaux:
        options = session.exec(
            select(OptionScolaire)
            .where(
                OptionScolaire.referentiel_id == referentiel.id,
                OptionScolaire.niveau_id == niveau.id,
                OptionScolaire.est_active == True,  # noqa: E712
                OptionScolaire.statut_validation == "verifie",
            )
            .order_by(OptionScolaire.parent_option_id, OptionScolaire.libelle)
        ).all()
        resultats.append({
            **_donnees_niveau(niveau),
            "options": [_donnees_option(option, options) for option in options],
        })

    sources = sorted({
        item.source_officielle
        for item in niveaux
        if item.source_officielle
    } | {
        option.source_officielle
        for niveau in niveaux
        for option in session.exec(
            select(OptionScolaire).where(
                OptionScolaire.niveau_id == niveau.id,
                OptionScolaire.est_active == True,  # noqa: E712
                OptionScolaire.statut_validation == "verifie",
            )
        ).all()
        if option.source_officielle
    })

    complet = referentiel.statut == "complet"
    return {
        "version": {
            "id": referentiel.id,
            "code": referentiel.code,
            "libelle": referentiel.libelle,
            "annee_scolaire": referentiel.annee_scolaire,
            "statut": referentiel.statut,
        },
        "complet": complet,
        "message": None if complet else (
            "Inventaire initial partiel : les filières techniques/professionnelles "
            "et les disponibilités par établissement restent à vérifier."
        ),
        "sources": sources,
        "niveaux": resultats,
    }


@router.get("/niveaux")
def lister_niveaux_scolaires(
    cycle: Optional[str] = Query(default=None, pattern="^(college|lycee)$"),
    session: Session = Depends(get_session),
):
    referentiel = _referentiel_actif(session)
    if not referentiel:
        return []

    requete = select(NiveauScolaire).where(
        NiveauScolaire.referentiel_id == referentiel.id,
        NiveauScolaire.est_actif == True,  # noqa: E712
        NiveauScolaire.statut_validation == "verifie",
    )
    if cycle:
        requete = requete.where(NiveauScolaire.cycle == cycle)
    niveaux = session.exec(
        requete.order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
    ).all()
    return [_donnees_niveau(niveau) for niveau in niveaux]


@router.get("/niveaux/{niveau_id}/options")
def lister_options_scolaires(
    niveau_id: int,
    session: Session = Depends(get_session),
):
    referentiel = _referentiel_actif(session)
    niveau = session.get(NiveauScolaire, niveau_id)
    if (
        not referentiel
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or niveau.statut_validation != "verifie"
    ):
        return []

    options = session.exec(
        select(OptionScolaire)
        .where(
            OptionScolaire.referentiel_id == referentiel.id,
            OptionScolaire.niveau_id == niveau.id,
            OptionScolaire.est_active == True,  # noqa: E712
            OptionScolaire.statut_validation == "verifie",
        )
        .order_by(OptionScolaire.parent_option_id, OptionScolaire.libelle)
    ).all()
    return [_donnees_option(option, options) for option in options]


@router.get("/niveaux/{niveau_id}/matieres")
def lister_matieres_scolaires(
    niveau_id: int,
    option_id: Optional[int] = Query(default=None, ge=1),
    session: Session = Depends(get_session),
):
    """Liste les matières vérifiées pour une classe et une série/option."""
    referentiel = _referentiel_actif(session)
    niveau = session.get(NiveauScolaire, niveau_id)
    if (
        not referentiel
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or niveau.statut_validation != "verifie"
    ):
        return []

    options_compatibles: list[int] = []
    if option_id is not None:
        option = session.get(OptionScolaire, option_id)
        if (
            not option
            or option.referentiel_id != referentiel.id
            or option.niveau_id != niveau.id
            or not option.est_active
            or option.statut_validation != "verifie"
        ):
            return []
        options_compatibles.append(option.id)
        if option.parent_option_id is not None:
            parent = session.get(OptionScolaire, option.parent_option_id)
            if (
                not parent
                or parent.referentiel_id != referentiel.id
                or parent.niveau_id != niveau.id
                or parent.parent_option_id is not None
                or not parent.est_active
                or parent.statut_validation != "verifie"
            ):
                return []
            options_compatibles.append(parent.id)

    requete = (
        select(ProgrammeMatiereScolaire, MatiereScolaire)
        .join(MatiereScolaire, MatiereScolaire.id == ProgrammeMatiereScolaire.matiere_id)
        .where(
            ProgrammeMatiereScolaire.referentiel_id == referentiel.id,
            ProgrammeMatiereScolaire.niveau_id == niveau.id,
            ProgrammeMatiereScolaire.statut_validation == "verifie",
            MatiereScolaire.est_active == True,  # noqa: E712
            MatiereScolaire.statut_validation == "verifie",
        )
    )
    if options_compatibles:
        requete = requete.where(
            or_(
                ProgrammeMatiereScolaire.option_id.is_(None),
                ProgrammeMatiereScolaire.option_id.in_(options_compatibles),
            )
        )
    else:
        requete = requete.where(ProgrammeMatiereScolaire.option_id.is_(None))

    rows = session.exec(requete.order_by(MatiereScolaire.libelle)).all()
    par_id: dict[int, dict] = {}
    for programme, matiere in rows:
        entry = par_id.setdefault(matiere.id, {
            "id": matiere.id,
            "code": matiere.code,
            "libelle": matiere.libelle,
            "libelle_malagasy": matiere.libelle_malagasy,
            "obligatoire": programme.obligatoire,
            "source_officielle": programme.source_officielle or matiere.source_officielle,
        })
        if programme.obligatoire:
            entry["obligatoire"] = True
    return sorted(par_id.values(), key=lambda item: item["libelle"].casefold())


@router.get("/etablissements")
def rechercher_etablissements_scolaires(
    q: Optional[str] = Query(default=None, max_length=100),
    region: Optional[str] = Query(default=None, max_length=100),
    commune: Optional[str] = Query(default=None, max_length=100),
    limite: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """Recherche uniquement parmi les établissements actifs et vérifiés."""
    requete = select(EtablissementScolaire).where(
        EtablissementScolaire.est_actif == True,  # noqa: E712
        EtablissementScolaire.est_verifie == True,  # noqa: E712
    )
    if q and q.strip():
        requete = requete.where(EtablissementScolaire.nom.ilike(f"%{q.strip()}%"))
    if region and region.strip():
        requete = requete.where(EtablissementScolaire.region.ilike(region.strip()))
    if commune and commune.strip():
        requete = requete.where(EtablissementScolaire.commune.ilike(commune.strip()))

    etablissements = session.exec(
        requete.order_by(EtablissementScolaire.nom).limit(limite)
    ).all()
    return [
        {
            "id": item.id,
            "nom": item.nom,
            "type_etablissement": item.type_etablissement,
            "secteur": item.secteur,
            "region": item.region,
            "district": item.district,
            "commune": item.commune,
        }
        for item in etablissements
    ]
