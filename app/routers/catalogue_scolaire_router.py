"""Page publique du catalogue scolaire et ETFP.

Le catalogue public ne montre que les établissements et offres vérifiés.
Le statut partiel du référentiel reste visible tant que la couverture nationale
et les offres réelles par établissement n'ont pas été complétées.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session, func, or_, select

from ..database import get_session
from ..models import (
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OffreEtablissementScolaire,
    OptionScolaire,
    ParcoursTechniqueProfessionnel,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
)
from ..templating import templates

router = APIRouter()


def _referentiel_courant(session: Session) -> Optional[ReferentielScolaire]:
    return session.exec(
        select(ReferentielScolaire).order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).first()


@router.get("/catalogue-scolaire")
def page_catalogue_scolaire(
    request: Request,
    q: Optional[str] = Query(default=None, max_length=100),
    region: Optional[str] = Query(default=None, max_length=100),
    type_offre: Optional[str] = Query(default=None, pattern="^(classe|serie|matiere|formation)$"),
    annee_scolaire: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{4}$"),
    session: Session = Depends(get_session),
):
    referentiel = _referentiel_courant(session)
    if referentiel:
        niveaux = session.exec(
            select(NiveauScolaire).where(
                NiveauScolaire.referentiel_id == referentiel.id,
                NiveauScolaire.est_actif == True,  # noqa: E712
                NiveauScolaire.statut_validation == "verifie",
            ).order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
        ).all()
        options = session.exec(
            select(OptionScolaire).where(
                OptionScolaire.referentiel_id == referentiel.id,
                OptionScolaire.est_active == True,  # noqa: E712
                OptionScolaire.statut_validation == "verifie",
            ).order_by(OptionScolaire.niveau_id, OptionScolaire.libelle)
        ).all()
    else:
        niveaux, options = [], []

    matieres = session.exec(
        select(MatiereScolaire).where(
            MatiereScolaire.est_active == True,  # noqa: E712
            MatiereScolaire.statut_validation == "verifie",
        ).order_by(MatiereScolaire.libelle)
    ).all()
    parcours_etfp = session.exec(
        select(ParcoursTechniqueProfessionnel).where(
            ParcoursTechniqueProfessionnel.est_actif == True,  # noqa: E712
            ParcoursTechniqueProfessionnel.statut_validation == "verifie",
        ).order_by(
            ParcoursTechniqueProfessionnel.secteur,
            ParcoursTechniqueProfessionnel.filiere,
            ParcoursTechniqueProfessionnel.metier,
        )
    ).all()

    years = session.exec(
        select(OffreEtablissementScolaire.annee_scolaire)
        .join(
            EtablissementScolaire,
            EtablissementScolaire.id == OffreEtablissementScolaire.etablissement_id,
        )
        .where(
            OffreEtablissementScolaire.est_active == True,  # noqa: E712
            OffreEtablissementScolaire.statut_validation == "verifie",
            OffreEtablissementScolaire.annee_scolaire.is_not(None),
            EtablissementScolaire.est_active == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
        )
        .distinct()
        .order_by(OffreEtablissementScolaire.annee_scolaire.desc())
    ).all()
    annee = annee_scolaire or (years[0] if years else None)

    requete = (
        select(
            OffreEtablissementScolaire,
            EtablissementScolaire,
            NiveauScolaire,
            OptionScolaire,
            MatiereScolaire,
            ParcoursTechniqueProfessionnel,
        )
        .join(
            EtablissementScolaire,
            EtablissementScolaire.id == OffreEtablissementScolaire.etablissement_id,
        )
        .outerjoin(
            NiveauScolaire,
            NiveauScolaire.id == OffreEtablissementScolaire.niveau_scolaire_id,
        )
        .outerjoin(
            OptionScolaire,
            OptionScolaire.id == OffreEtablissementScolaire.option_scolaire_id,
        )
        .outerjoin(
            MatiereScolaire,
            MatiereScolaire.id == OffreEtablissementScolaire.matiere_scolaire_id,
        )
        .outerjoin(
            ParcoursTechniqueProfessionnel,
            ParcoursTechniqueProfessionnel.id == OffreEtablissementScolaire.parcours_etfp_id,
        )
        .where(
            OffreEtablissementScolaire.est_active == True,  # noqa: E712
            OffreEtablissementScolaire.statut_validation == "verifie",
            EtablissementScolaire.est_active == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
        )
    )
    if annee:
        requete = requete.where(OffreEtablissementScolaire.annee_scolaire == annee)
    else:
        requete = requete.where(OffreEtablissementScolaire.id == -1)
    if type_offre:
        requete = requete.where(OffreEtablissementScolaire.type_offre == type_offre)
    if region and region.strip():
        requete = requete.where(EtablissementScolaire.region.ilike(region.strip()))
    if q and q.strip():
        terme = f"%{q.strip()}%"
        requete = requete.where(
            or_(
                EtablissementScolaire.nom.ilike(terme),
                EtablissementScolaire.region.ilike(terme),
                EtablissementScolaire.commune.ilike(terme),
                NiveauScolaire.libelle.ilike(terme),
                OptionScolaire.libelle.ilike(terme),
                MatiereScolaire.libelle.ilike(terme),
                ParcoursTechniqueProfessionnel.secteur.ilike(terme),
                ParcoursTechniqueProfessionnel.filiere.ilike(terme),
                ParcoursTechniqueProfessionnel.metier.ilike(terme),
            )
        )
    rows = session.exec(
        requete.order_by(
            EtablissementScolaire.region,
            EtablissementScolaire.nom,
            OffreEtablissementScolaire.type_offre,
        ).limit(100)
    ).all()

    offres = []
    for offre, institution, niveau, option, matiere, parcours in rows:
        if offre.type_offre == "formation":
            cible = " · ".join(
                part for part in (
                    parcours.secteur if parcours else None,
                    parcours.filiere if parcours else None,
                    parcours.metier if parcours else None,
                ) if part
            )
        elif offre.type_offre == "matiere":
            cible = " · ".join(
                part for part in (
                    niveau.libelle if niveau else None,
                    option.libelle if option else None,
                    matiere.libelle if matiere else None,
                ) if part
            )
        elif offre.type_offre == "serie":
            cible = " · ".join(
                part for part in (
                    niveau.libelle if niveau else None,
                    option.libelle if option else None,
                ) if part
            )
        else:
            cible = niveau.libelle if niveau else "Classe"
        offres.append({
            "type": offre.type_offre,
            "annee": offre.annee_scolaire,
            "cible": cible,
            "etablissement": institution.nom,
            "region": institution.region,
            "commune": institution.commune,
            "source": offre.source_officielle,
        })

    etab_requete = select(EtablissementScolaire).where(
        EtablissementScolaire.est_actif == True,  # noqa: E712
        EtablissementScolaire.est_verifie == True,  # noqa: E712
    )
    if region and region.strip():
        etab_requete = etab_requete.where(EtablissementScolaire.region.ilike(region.strip()))
    if q and q.strip():
        terme = f"%{q.strip()}%"
        etab_requete = etab_requete.where(
            or_(
                EtablissementScolaire.nom.ilike(terme),
                EtablissementScolaire.region.ilike(terme),
                EtablissementScolaire.commune.ilike(terme),
            )
        )
    etablissements = session.exec(
        etab_requete.order_by(EtablissementScolaire.region, EtablissementScolaire.nom).limit(100)
    ).all()
    regions = session.exec(
        select(EtablissementScolaire.region)
        .where(
            EtablissementScolaire.est_active == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
            EtablissementScolaire.region.is_not(None),
        )
        .distinct()
        .order_by(EtablissementScolaire.region)
    ).all()

    nb_programmes_verifies = session.exec(
        select(func.count()).select_from(ProgrammeMatiereScolaire).where(
            ProgrammeMatiereScolaire.referentiel_id == referentiel.id if referentiel else False,
            ProgrammeMatiereScolaire.statut_validation == "verifie",
        )
    ).one() if referentiel else 0

    return templates.TemplateResponse(
        request,
        "catalogue_scolaire.html",
        {
            "referentiel": referentiel,
            "niveaux": niveaux,
            "options": options,
            "matieres": matieres,
            "parcours_etfp": parcours_etfp,
            "etablissements": etablissements,
            "regions": regions,
            "offres": offres,
            "annees": years,
            "annee_selectionnee": annee,
            "q": q or "",
            "region_selectionnee": region or "",
            "type_offre_selectionne": type_offre or "",
            "nb_programmes_verifies": nb_programmes_verifies,
            "nb_etablissements": len(etablissements),
        },
    )
