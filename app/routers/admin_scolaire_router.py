"""Administration du référentiel scolaire national.

Les entrées créées dans l'interface restent non vérifiées tant qu'un
administrateur ne les a pas validées avec une source HTTPS exploitable.
Les API publiques ne publient que les lignes actives et vérifiées.
"""
from datetime import datetime
import json
from typing import Optional
from urllib.parse import urlparse
import re
import unicodedata

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, func, or_

from ..auth import utilisateur_courant
from ..permissions import est_administrateur_global
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    CercleEtude,
    CoefficientMatiereEtablissement,
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ParametresAcademiquesEtablissement,
    ParametresAcademiquesEvenement,
    OffreEtablissementScolaire,
    ParcoursTechniqueProfessionnel,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    StatutCercle,
    Utilisateur,
)
from ..cercles_scolaires import assurer_cercles_scolaires
from ..templating import templates

router = APIRouter()

# Dénombrement du répertoire officiel de la cartographie METFP observé le
# 24/10/2026. Ce n'est PAS une mesure des formations ouvertes cette année.
# Le rapprochement est affiché à l'administration afin de rendre les lacunes visibles.
SOURCE_METFP_COUVERTURE = "https://www.metfp.gov.mg/cartographie"
DATE_SNAPSHOT_METFP = "2026-10-24"
ETABLISSEMENTS_ATTENDUS_PAR_REGION = {
    "ALAOTRA MANGORO": 5,
    "AMBATOSOA": 2,
    "AMORON'I MANIA": 13,
    "ANALAMANGA": 22,
    "ANALANJIROFO": 4,
    "ANDROY": 2,
    "ANOSY": 8,
    "ATSIMO ANDREFANA": 7,
    "ATSIMO ATSINANANA": 5,
    "ATSINANANA": 5,
    "BETSIBOKA": 1,
    "BOENY": 9,
    "BONGOLAVA": 3,
    "DIANA": 7,
    "FITOVINANY": 3,
    "HAUTE MATSIATRA": 4,
    "IHOROMBE": 3,
    "ITASY": 3,
    "MELAKY": 1,
    "MENABE": 4,
    "SAVA": 7,
    "SOFIA": 6,
    "VAKINANKARATRA": 10,
    "VATOVAVY": 2,
}


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    return utilisateur if est_administrateur_global(utilisateur) else None


def _referentiel_courant(session: Session) -> Optional[ReferentielScolaire]:
    lignes = session.exec(
        select(ReferentielScolaire)
        .where(ReferentielScolaire.statut.notin_(("historique", "archive")))
        .order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).all()
    return lignes[0] if lignes else None


def _referentiel_du_niveau(
    session: Session, niveau: Optional[NiveauScolaire]
) -> Optional[ReferentielScolaire]:
    """Retourne la version qui porte réellement ce niveau, même si elle est ancienne."""
    if niveau is None:
        return None
    return session.get(ReferentielScolaire, niveau.referentiel_id)


def _url_source_valide(source: str | None) -> bool:
    """N'accepte que des pages HTTPS du ministère malgache de l'Éducation."""
    if not source:
        return False
    try:
        parsed = urlparse(source.strip())
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    domaines_officiels = ("education.gov.mg", "plateforme.education.mg", "metfp.gov.mg")
    domaine_officiel = any(
        hostname == domaine or hostname.endswith("." + domaine)
        for domaine in domaines_officiels
    )
    return parsed.scheme == "https" and domaine_officiel


def _rediriger(etat: str, identifiant: int | None = None) -> RedirectResponse:
    suffixe = f"&id={identifiant}" if identifiant is not None else ""
    return RedirectResponse(
        f"/admin/referentiel/scolaire?ok={etat}{suffixe}",
        status_code=303,
    )


def _erreur(code: str) -> RedirectResponse:
    return RedirectResponse(f"/admin/referentiel/scolaire?erreur={code}", status_code=303)


@router.get("/admin/referentiel/scolaire")
def page_referentiel_scolaire(
    request: Request,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    referentiel = _referentiel_courant(session)
    niveaux = session.exec(
        select(NiveauScolaire).order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
    ).all()
    options = session.exec(
        select(OptionScolaire).order_by(
            OptionScolaire.niveau_id, OptionScolaire.parent_option_id, OptionScolaire.libelle
        )
    ).all()
    matieres = session.exec(select(MatiereScolaire).order_by(MatiereScolaire.libelle)).all()
    etablissements = session.exec(
        select(EtablissementScolaire).order_by(
            EtablissementScolaire.est_verifie,
            EtablissementScolaire.region,
            EtablissementScolaire.nom,
        )
    ).all()
    programmes = session.exec(
        select(ProgrammeMatiereScolaire).order_by(
            ProgrammeMatiereScolaire.statut_validation,
            ProgrammeMatiereScolaire.niveau_id,
            ProgrammeMatiereScolaire.id,
        )
    ).all()
    parcours_etfp = session.exec(
        select(ParcoursTechniqueProfessionnel).order_by(
            ParcoursTechniqueProfessionnel.statut_validation,
            ParcoursTechniqueProfessionnel.secteur,
            ParcoursTechniqueProfessionnel.filiere,
            ParcoursTechniqueProfessionnel.metier,
        )
    ).all()
    offres_etablissement = session.exec(
        select(OffreEtablissementScolaire).order_by(
            OffreEtablissementScolaire.statut_validation,
            OffreEtablissementScolaire.etablissement_id,
            OffreEtablissementScolaire.type_offre,
            OffreEtablissementScolaire.id,
        )
    ).all()

    lignes_couverture = session.exec(
        select(
            EtablissementScolaire.region,
            func.count(func.distinct(func.lower(func.trim(EtablissementScolaire.nom)))),
        )
        .where(
            EtablissementScolaire.region.is_not(None),
            EtablissementScolaire.est_actif == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
        )
        .group_by(EtablissementScolaire.region)
    ).all()
    recenses_par_region = {
        str(region).strip().upper(): int(total)
        for region, total in lignes_couverture
        if region
    }
    couverture_regions = [
        {
            "region": region,
            "attendus": attendu,
            "recenses": recenses_par_region.get(region, 0),
            "restants": max(0, attendu - recenses_par_region.get(region, 0)),
            "statut": (
                "À compléter"
                if recenses_par_region.get(region, 0) < attendu
                else (
                    "Écart à examiner"
                    if recenses_par_region.get(region, 0) > attendu
                    else "Compte rapproché"
                )
            ),
        }
        for region, attendu in ETABLISSEMENTS_ATTENDUS_PAR_REGION.items()
    ]
    etablissements_attendus_total = sum(ETABLISSEMENTS_ATTENDUS_PAR_REGION.values())
    etablissements_recenses_total = sum(row["recenses"] for row in couverture_regions)
    couverture_regions_manquantes = sum(row["restants"] for row in couverture_regions)
    regions_a_examiner = sum(row["statut"] == "Écart à examiner" for row in couverture_regions)

    niveaux_map = {item.id: item for item in niveaux}
    options_map = {item.id: item for item in options}
    matieres_map = {item.id: item for item in matieres}
    etablissements_map = {item.id: item for item in etablissements}
    parcours_etfp_map = {item.id: item for item in parcours_etfp}
    cercles_scolaires_actifs = session.exec(
        select(func.count()).select_from(CercleEtude).where(
            CercleEtude.portee_academique == "scolaire",
            CercleEtude.statut == StatutCercle.ACTIF,
        )
    ).one()
    cercles_scolaires_synchronises = session.exec(
        select(func.count()).select_from(CercleEtude).where(
            CercleEtude.portee_academique == "scolaire",
            CercleEtude.synchronise_referentiel == True,  # noqa: E712
            CercleEtude.statut == StatutCercle.ACTIF,
        )
    ).one()

    return templates.TemplateResponse(
        request,
        "admin_referentiel_scolaire.html",
        {
            "utilisateur": admin,
            "referentiel": referentiel,
            "niveaux": niveaux,
            "niveaux_map": niveaux_map,
            "options": options,
            "options_map": options_map,
            "matieres": matieres,
            "matieres_map": matieres_map,
            "etablissements": etablissements,
            "etablissements_map": etablissements_map,
            "programmes": programmes,
            "parcours_etfp": parcours_etfp,
            "parcours_etfp_map": parcours_etfp_map,
            "offres_etablissement": offres_etablissement,
            "couverture_regions": couverture_regions,
            "source_metfp_couverture": SOURCE_METFP_COUVERTURE,
            "date_snapshot_metfp": DATE_SNAPSHOT_METFP,
            "etablissements_attendus_total": etablissements_attendus_total,
            "etablissements_recenses_total": etablissements_recenses_total,
            "couverture_regions_manquantes": couverture_regions_manquantes,
            "regions_a_examiner": regions_a_examiner,
            "cercles_scolaires_actifs": cercles_scolaires_actifs,
            "cercles_scolaires_synchronises": cercles_scolaires_synchronises,
        },
    )


@router.post("/admin/referentiel/scolaire/cercles/synchroniser")
def synchroniser_cercles_scolaires(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Déclenche manuellement la réconciliation idempotente des cercles scolaires."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    rapport = assurer_cercles_scolaires(session)
    return RedirectResponse(
        "/admin/referentiel/scolaire"
        f"?ok=cercles_synchronises&cibles={int(rapport['cibles'] or 0)}"
        f"&crees={int(rapport['crees'] or 0)}"
        f"&reactives={int(rapport['reactives'] or 0)}"
        f"&actualises={int(rapport['actualises'] or 0)}"
        f"&archives={int(rapport['archives'] or 0)}"
        f"&preserves={int(rapport['preserves'] or 0)}",
        status_code=303,
    )


@router.post("/admin/referentiel/scolaire/etablissements/creer")
def creer_etablissement_scolaire(
    request: Request,
    nom: str = Form(...),
    code: str = Form(default=""),
    type_etablissement: str = Form(default="college_lycee"),
    secteur: str = Form(default="inconnu"),
    region: str = Form(default=""),
    district: str = Form(default=""),
    commune: str = Form(default=""),
    source_officielle: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    nom = " ".join(nom.split())[:180]
    code = "".join(ch for ch in code.strip().upper() if ch.isalnum() or ch in "-_")[:40]
    if len(nom) < 3:
        return _erreur("nom_etablissement_requis")
    if type_etablissement not in {
        "college", "lycee", "college_lycee", "lycee_technique", "professionnel",
        "centre_formation", "centre_formation_specialise",
    }:
        return _erreur("type_etablissement_invalide")
    if secteur not in {"public", "prive", "inconnu"}:
        return _erreur("secteur_invalide")
    if code:
        doublon = session.exec(
            select(EtablissementScolaire).where(EtablissementScolaire.code == code)
        ).all()
        if doublon:
            return _erreur("code_etablissement_deja_utilise")

    source = source_officielle.strip()[:500] or None
    entree = EtablissementScolaire(
        nom=nom,
        code=code or None,
        type_etablissement=type_etablissement,
        secteur=secteur,
        region=" ".join(region.split())[:120] or None,
        district=" ".join(district.split())[:120] or None,
        commune=" ".join(commune.split())[:120] or None,
        source_officielle=source,
        est_verifie=False,
        est_actif=True,
        date_creation=datetime.utcnow(),
        date_maj=datetime.utcnow(),
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("etablissement_ajoute", entree.id)


@router.post("/admin/referentiel/scolaire/etablissements/{etablissement_id}/valider")
def valider_etablissement_scolaire(
    request: Request,
    etablissement_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(EtablissementScolaire, etablissement_id)
    if not entree:
        return _erreur("etablissement_introuvable")
    if not _url_source_valide(entree.source_officielle):
        return _erreur("source_https_requise")
    entree.est_verifie = True
    entree.est_actif = True
    entree.date_maj = datetime.utcnow()
    session.add(entree)
    session.commit()
    return _rediriger("etablissement_valide", entree.id)


@router.post("/admin/referentiel/scolaire/etablissements/{etablissement_id}/desactiver")
def desactiver_etablissement_scolaire(
    request: Request,
    etablissement_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(EtablissementScolaire, etablissement_id)
    if not entree:
        return _erreur("etablissement_introuvable")
    entree.est_actif = False
    entree.date_maj = datetime.utcnow()
    session.add(entree)
    session.commit()
    return _rediriger("etablissement_desactive", entree.id)




def _code_interne(*parties: str) -> str:
    brut = "-".join(part for part in parties if part)
    ascii_brut = unicodedata.normalize("NFKD", brut).encode("ascii", "ignore").decode("ascii")
    code = re.sub(r"[^A-Za-z0-9]+", "-", ascii_brut).strip("-").upper()
    return code[:160]


def _entier_optionnel(valeur: str) -> int | None:
    if not valeur.strip():
        return None
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


@router.post("/admin/referentiel/scolaire/parcours-etfp/creer")
def creer_parcours_etfp(
    request: Request,
    secteur: str = Form(default=""),
    filiere: str = Form(default=""),
    metier: str = Form(...),
    source_officielle: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    secteur = " ".join(secteur.split())[:120]
    filiere = " ".join(filiere.split())[:180]
    metier = " ".join(metier.split())[:180]
    source = source_officielle.strip()[:500]
    if not metier:
        return _erreur("etfp_metier_requis")
    if not _url_source_valide(source):
        return _erreur("source_https_requise")
    code = _code_interne(secteur, filiere, metier)
    existing = session.exec(
        select(ParcoursTechniqueProfessionnel).where(
            ParcoursTechniqueProfessionnel.code == code
        )
    ).first()
    if existing:
        return _erreur("etfp_parcours_deja_existant")
    entree = ParcoursTechniqueProfessionnel(
        code=code,
        secteur=secteur or None,
        filiere=filiere or None,
        metier=metier,
        source_officielle=source,
        statut_validation="a_verifier",
        est_actif=False,
        date_creation=datetime.utcnow(),
        date_maj=datetime.utcnow(),
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("etfp_parcours_ajoute", entree.id)


@router.post("/admin/referentiel/scolaire/parcours-etfp/{parcours_id}/valider")
def valider_parcours_etfp(
    request: Request,
    parcours_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(ParcoursTechniqueProfessionnel, parcours_id)
    if not entree:
        return _erreur("etfp_parcours_introuvable")
    if not _url_source_valide(entree.source_officielle):
        return _erreur("source_https_requise")
    if not (entree.filiere or entree.metier):
        return _erreur("etfp_metier_requis")
    entree.statut_validation = "verifie"
    entree.est_actif = True
    entree.date_maj = datetime.utcnow()
    session.add(entree)
    session.commit()
    return _rediriger("etfp_parcours_valide", entree.id)



@router.post("/admin/referentiel/scolaire/offres/creer")
def creer_offre_etablissement(
    request: Request,
    etablissement_id: int = Form(...),
    type_offre: str = Form(...),
    niveau_id: str = Form(default=""),
    option_id: str = Form(default=""),
    matiere_id: str = Form(default=""),
    parcours_etfp_id: str = Form(default=""),
    annee_scolaire: str = Form(...),
    source_officielle: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    institution = session.get(EtablissementScolaire, etablissement_id)
    if not institution or not institution.est_actif or not institution.est_verifie:
        return _erreur("etablissement_non_verifie")
    if type_offre not in {"classe", "serie", "matiere", "formation"}:
        return _erreur("offre_type_invalide")
    annee = annee_scolaire.strip()
    match_annee = re.fullmatch(r"(\d{4})-(\d{4})", annee)
    if not match_annee or int(match_annee.group(2)) != int(match_annee.group(1)) + 1:
        return _erreur("offre_annee_invalide")
    source = source_officielle.strip()[:500]
    if not _url_source_valide(source):
        return _erreur("source_https_requise")

    niveau_pk = _entier_optionnel(niveau_id)
    option_pk = _entier_optionnel(option_id)
    matiere_pk = _entier_optionnel(matiere_id)
    parcours_pk = _entier_optionnel(parcours_etfp_id)
    niveau = session.get(NiveauScolaire, niveau_pk) if niveau_pk else None
    referentiel = _referentiel_du_niveau(session, niveau)
    option = session.get(OptionScolaire, option_pk) if option_pk else None
    matiere = session.get(MatiereScolaire, matiere_pk) if matiere_pk else None
    parcours = session.get(ParcoursTechniqueProfessionnel, parcours_pk) if parcours_pk else None

    if type_offre in {"classe", "serie", "matiere"}:
        if (
            not referentiel or not niveau
            or niveau.referentiel_id != referentiel.id
            or not niveau.est_actif or niveau.statut_validation != "verifie"
        ):
            return _erreur("offre_niveau_invalide")
        if type_offre == "classe" and (option_pk or matiere_pk or parcours_pk):
            return _erreur("offre_cible_invalide")
        if type_offre == "serie" and (
            not option or option.niveau_id != niveau.id
            or option.referentiel_id != referentiel.id
            or not option.est_active or option.statut_validation != "verifie"
            or matiere_pk or parcours_pk
        ):
            return _erreur("offre_serie_invalide")
        if type_offre == "matiere":
            if (
                not matiere or not matiere.est_active
                or matiere.statut_validation != "verifie" or parcours_pk
            ):
                return _erreur("offre_matiere_invalide")
            if option_pk and (
                not option or option.niveau_id != niveau.id
                or option.referentiel_id != referentiel.id
                or not option.est_active or option.statut_validation != "verifie"
            ):
                return _erreur("offre_serie_invalide")
            compatible_options = [option_pk] if option_pk else []
            if option and option.parent_option_id:
                compatible_options.append(option.parent_option_id)
            clauses = [ProgrammeMatiereScolaire.option_id.is_(None)]
            clauses.extend(
                ProgrammeMatiereScolaire.option_id == identifiant
                for identifiant in compatible_options
            )
            programmes = session.exec(
                select(ProgrammeMatiereScolaire).where(
                    ProgrammeMatiereScolaire.referentiel_id == referentiel.id,
                    ProgrammeMatiereScolaire.niveau_id == niveau.id,
                    ProgrammeMatiereScolaire.matiere_id == matiere.id,
                    ProgrammeMatiereScolaire.statut_validation == "verifie",
                    or_(*clauses),
                )
            ).all()
            if not programmes:
                return _erreur("offre_matiere_sans_programme")
    else:
        if (
            not parcours or not parcours.est_actif
            or parcours.statut_validation != "verifie"
            or niveau_pk or option_pk or matiere_pk
        ):
            return _erreur("offre_formation_invalide")

    if type_offre == "classe":
        code_offre = _code_interne("CLASSE", niveau.code)
    elif type_offre == "serie":
        code_offre = _code_interne("SERIE", niveau.code, option.code)
    elif type_offre == "matiere":
        code_offre = _code_interne(
            "MATIERE", niveau.code, option.code if option else "TRONC-COMMUN", matiere.code
        )
    else:
        code_offre = _code_interne("FORMATION", parcours.code)

    doublon = session.exec(
        select(OffreEtablissementScolaire).where(
            OffreEtablissementScolaire.etablissement_id == etablissement_id,
            OffreEtablissementScolaire.code_offre == code_offre,
            OffreEtablissementScolaire.annee_scolaire == annee,
            OffreEtablissementScolaire.est_active == True,  # noqa: E712
        )
    ).first()
    if doublon:
        return _erreur("offre_deja_existante")
    entree = OffreEtablissementScolaire(
        etablissement_id=etablissement_id,
        code_offre=code_offre,
        type_offre=type_offre,
        niveau_scolaire_id=niveau_pk,
        option_scolaire_id=option_pk,
        matiere_scolaire_id=matiere_pk,
        parcours_etfp_id=parcours_pk,
        annee_scolaire=annee,
        source_officielle=source,
        statut_validation="a_verifier",
        est_active=True,
        date_creation=datetime.utcnow(),
        date_maj=datetime.utcnow(),
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("offre_etablissement_ajoutee", entree.id)


@router.post("/admin/referentiel/scolaire/offres/{offre_id}/valider")
def valider_offre_etablissement(
    request: Request,
    offre_id: int,
    annee_scolaire: str = Form(...),
    source_officielle: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(OffreEtablissementScolaire, offre_id)
    if not entree or not entree.est_active:
        return _erreur("offre_etablissement_introuvable")
    annee = annee_scolaire.strip()
    match = re.fullmatch(r"(\d{4})-(\d{4})", annee)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        return _erreur("offre_annee_invalide")
    institution = session.get(EtablissementScolaire, entree.etablissement_id)
    if not institution or not institution.est_actif or not institution.est_verifie:
        return _erreur("etablissement_non_verifie")
    source = (source_officielle.strip() or entree.source_officielle).strip()[:500]
    if not _url_source_valide(source):
        return _erreur("source_https_requise")

    if entree.type_offre == "formation":
        parcours = session.get(ParcoursTechniqueProfessionnel, entree.parcours_etfp_id)
        if not parcours or not parcours.est_active or parcours.statut_validation != "verifie":
            return _erreur("offre_formation_invalide")
    else:
        niveau = session.get(NiveauScolaire, entree.niveau_scolaire_id)
        referentiel = _referentiel_du_niveau(session, niveau)
        if (
            not referentiel or not niveau
            or not niveau.est_actif or niveau.statut_validation != "verifie"
        ):
            return _erreur("offre_niveau_invalide")
        if entree.type_offre == "serie":
            option = session.get(OptionScolaire, entree.option_scolaire_id)
            if (
                not option or option.niveau_id != niveau.id
                or option.referentiel_id != referentiel.id
                or not option.est_active or option.statut_validation != "verifie"
            ):
                return _erreur("offre_serie_invalide")
        if entree.type_offre == "matiere":
            matiere = session.get(MatiereScolaire, entree.matiere_scolaire_id)
            if not matiere or not matiere.est_active or matiere.statut_validation != "verifie":
                return _erreur("offre_matiere_invalide")
            compatible = [ProgrammeMatiereScolaire.option_id.is_(None)]
            if entree.option_scolaire_id:
                compatible.append(
                    ProgrammeMatiereScolaire.option_id == entree.option_scolaire_id
                )
            programmes = session.exec(
                select(ProgrammeMatiereScolaire).where(
                    ProgrammeMatiereScolaire.referentiel_id == referentiel.id,
                    ProgrammeMatiereScolaire.niveau_id == niveau.id,
                    ProgrammeMatiereScolaire.matiere_id == matiere.id,
                    ProgrammeMatiereScolaire.statut_validation == "verifie",
                    or_(*compatible),
                )
            ).all()
            if not programmes:
                return _erreur("offre_matiere_sans_programme")

    doublon = session.exec(
        select(OffreEtablissementScolaire).where(
            OffreEtablissementScolaire.etablissement_id == entree.etablissement_id,
            OffreEtablissementScolaire.code_offre == entree.code_offre,
            OffreEtablissementScolaire.annee_scolaire == annee,
            OffreEtablissementScolaire.est_active == True,  # noqa: E712
            OffreEtablissementScolaire.id != entree.id,
        )
    ).first()
    if doublon:
        return _erreur("offre_deja_existante")
    entree.annee_scolaire = annee
    entree.source_officielle = source
    entree.statut_validation = "verifie"
    entree.valide_par_id = admin.id
    entree.date_validation = datetime.utcnow()
    entree.date_maj = datetime.utcnow()
    session.add(entree)
    session.commit()
    return _rediriger("offre_etablissement_validee", entree.id)



@router.post("/admin/referentiel/scolaire/offres/{offre_id}/desactiver")
def desactiver_offre_etablissement(
    request: Request,
    offre_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Archive une offre devenue obsolète sans effacer sa trace."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(OffreEtablissementScolaire, offre_id)
    if not entree:
        return _erreur("offre_etablissement_introuvable")
    entree.est_active = False
    entree.date_maj = datetime.utcnow()
    session.add(entree)
    session.commit()
    return _rediriger("offre_etablissement_archivee", entree.id)


@router.post("/admin/referentiel/scolaire/options/creer")
def creer_option_scolaire(
    request: Request,
    niveau_id: int = Form(...),
    parent_option_id: str = Form(default=""),
    code: str = Form(...),
    libelle: str = Form(...),
    type_option: str = Form(default="serie"),
    source_officielle: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    referentiel = _referentiel_courant(session)
    niveau = session.get(NiveauScolaire, niveau_id)
    if (
        not referentiel
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
    ):
        return _erreur("niveau_scolaire_invalide")
    code = "".join(ch for ch in code.strip().upper() if ch.isalnum() or ch in "-_")[:30]
    libelle = " ".join(libelle.split())[:160]
    if not code or len(libelle) < 2:
        return _erreur("option_champs_requis")
    if type_option not in {"serie", "option", "filiere", "specialite"}:
        return _erreur("type_option_invalide")
    parent_id = None
    if parent_option_id.strip():
        try:
            parent_id = int(parent_option_id)
        except ValueError:
            return _erreur("option_parente_invalide")
        parent = session.get(OptionScolaire, parent_id)
        if (
            not parent
            or parent.niveau_id != niveau.id
            or parent.referentiel_id != referentiel.id
            or parent.parent_option_id is not None
        ):
            return _erreur("option_parente_invalide")
    existantes = session.exec(
        select(OptionScolaire).where(
            OptionScolaire.niveau_id == niveau.id,
            OptionScolaire.code == code,
        )
    ).all()
    if existantes:
        return _erreur("option_deja_existante")
    entree = OptionScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        parent_option_id=parent_id,
        code=code,
        libelle=libelle,
        type_option=type_option,
        source_officielle=source_officielle.strip()[:500] or None,
        est_active=False,
        statut_validation="a_verifier",
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("option_ajoutee", entree.id)


@router.post("/admin/referentiel/scolaire/options/{option_id}/valider")
def valider_option_scolaire(
    request: Request,
    option_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(OptionScolaire, option_id)
    if not entree:
        return _erreur("option_introuvable")
    referentiel = _referentiel_courant(session)
    niveau = session.get(NiveauScolaire, entree.niveau_id)
    if (
        not referentiel
        or entree.referentiel_id != referentiel.id
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or niveau.statut_validation != "verifie"
    ):
        return _erreur("niveau_scolaire_invalide")
    if not _url_source_valide(entree.source_officielle):
        return _erreur("source_https_requise")
    if entree.parent_option_id is not None:
        parent = session.get(OptionScolaire, entree.parent_option_id)
        if (
            not parent
            or parent.niveau_id != entree.niveau_id
            or parent.referentiel_id != entree.referentiel_id
            or not parent.est_active
            or parent.statut_validation != "verifie"
        ):
            return _erreur("option_parente_non_validee")
    entree.est_active = True
    entree.statut_validation = "verifie"
    session.add(entree)
    session.commit()
    assurer_cercles_scolaires(session)
    return _rediriger("option_validee", entree.id)


@router.post("/admin/referentiel/scolaire/matieres/creer")
def creer_matiere_scolaire(
    request: Request,
    code: str = Form(...),
    libelle: str = Form(...),
    libelle_malagasy: str = Form(default=""),
    source_officielle: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    code = "".join(ch for ch in code.strip().upper() if ch.isalnum() or ch in "-_")[:40]
    libelle = " ".join(libelle.split())[:160]
    if not code or len(libelle) < 2:
        return _erreur("matiere_champs_requis")
    doublons = session.exec(
        select(MatiereScolaire).where(MatiereScolaire.code == code)
    ).all()
    if doublons:
        return _erreur("matiere_deja_existante")
    entree = MatiereScolaire(
        code=code,
        libelle=libelle,
        libelle_malagasy=" ".join(libelle_malagasy.split())[:160] or None,
        source_officielle=source_officielle.strip()[:500] or None,
        statut_validation="a_verifier",
        est_active=False,
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("matiere_ajoutee", entree.id)


@router.post("/admin/referentiel/scolaire/matieres/{matiere_id}/valider")
def valider_matiere_scolaire(
    request: Request,
    matiere_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(MatiereScolaire, matiere_id)
    if not entree:
        return _erreur("matiere_introuvable")
    if not _url_source_valide(entree.source_officielle):
        return _erreur("source_https_requise")
    entree.est_active = True
    entree.statut_validation = "verifie"
    session.add(entree)
    session.commit()
    assurer_cercles_scolaires(session)
    return _rediriger("matiere_validee", entree.id)


@router.post("/admin/referentiel/scolaire/programmes/creer")
def creer_association_programme_scolaire(
    request: Request,
    niveau_id: int = Form(...),
    option_id: str = Form(default=""),
    matiere_id: int = Form(...),
    obligatoire: str = Form(default="oui"),
    source_officielle: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    referentiel = _referentiel_courant(session)
    niveau = session.get(NiveauScolaire, niveau_id)
    matiere = session.get(MatiereScolaire, matiere_id)
    if (
        not referentiel
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or not matiere
    ):
        return _erreur("programme_scolaire_reference_invalide")
    option_pk = None
    if option_id.strip():
        try:
            option_pk = int(option_id)
        except ValueError:
            return _erreur("option_scolaire_invalide")
        option = session.get(OptionScolaire, option_pk)
        parent = (
            session.get(OptionScolaire, option.parent_option_id)
            if option and option.parent_option_id else None
        )
        if (
            not option
            or option.referentiel_id != referentiel.id
            or option.niveau_id != niveau.id
            or not option.est_active
            or option.statut_validation != "verifie"
            or (
                option.parent_option_id is not None
                and (
                    not parent
                    or parent.referentiel_id != referentiel.id
                    or parent.niveau_id != niveau.id
                    or parent.parent_option_id is not None
                    or not parent.est_active
                    or parent.statut_validation != "verifie"
                )
            )
        ):
            return _erreur("option_scolaire_invalide")
    existantes = session.exec(
        select(ProgrammeMatiereScolaire).where(
            ProgrammeMatiereScolaire.referentiel_id == referentiel.id,
            ProgrammeMatiereScolaire.niveau_id == niveau.id,
            ProgrammeMatiereScolaire.option_id == option_pk,
            ProgrammeMatiereScolaire.matiere_id == matiere.id,
        )
    ).all()
    if existantes:
        return _erreur("programme_scolaire_deja_existant")
    entree = ProgrammeMatiereScolaire(
        referentiel_id=referentiel.id,
        niveau_id=niveau.id,
        option_id=option_pk,
        matiere_id=matiere.id,
        obligatoire=obligatoire == "oui",
        source_officielle=source_officielle.strip()[:500] or None,
        statut_validation="a_verifier",
    )
    session.add(entree)
    session.commit()
    session.refresh(entree)
    return _rediriger("programme_scolaire_ajoute", entree.id)


@router.post("/admin/referentiel/scolaire/programmes/{programme_id}/valider")
def valider_association_programme_scolaire(
    request: Request,
    programme_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(ProgrammeMatiereScolaire, programme_id)
    if not entree:
        return _erreur("programme_scolaire_introuvable")
    referentiel = _referentiel_courant(session)
    niveau = session.get(NiveauScolaire, entree.niveau_id)
    matiere = session.get(MatiereScolaire, entree.matiere_id)
    if (
        not referentiel
        or entree.referentiel_id != referentiel.id
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or niveau.statut_validation != "verifie"
        or not matiere
        or not matiere.est_active
        or matiere.statut_validation != "verifie"
    ):
        return _erreur("programme_scolaire_reference_invalide")
    if not _url_source_valide(entree.source_officielle):
        return _erreur("source_https_requise")
    if entree.option_id is not None:
        option = session.get(OptionScolaire, entree.option_id)
        parent = (
            session.get(OptionScolaire, option.parent_option_id)
            if option and option.parent_option_id else None
        )
        if (
            not option
            or option.referentiel_id != entree.referentiel_id
            or option.niveau_id != entree.niveau_id
            or not option.est_active
            or option.statut_validation != "verifie"
            or (
                option.parent_option_id is not None
                and (
                    not parent
                    or parent.referentiel_id != entree.referentiel_id
                    or parent.niveau_id != entree.niveau_id
                    or parent.parent_option_id is not None
                    or not parent.est_active
                    or parent.statut_validation != "verifie"
                )
            )
        ):
            return _erreur("option_scolaire_invalide")
    entree.statut_validation = "verifie"
    session.add(entree)
    session.commit()
    assurer_cercles_scolaires(session)
    return _rediriger("programme_scolaire_valide", entree.id)


# ---------------------------------------------------------------------------
# Paramètres pédagogiques par établissement et année scolaire
# ---------------------------------------------------------------------------

def _periodes_configuration(texte: str) -> list[dict[str, str]] | None:
    """Lit une période par ligne au format CODE|Libellé, sans doublons."""
    periodes: list[dict[str, str]] = []
    codes_vus: set[str] = set()
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        morceaux = ligne.split("|", 1)
        if len(morceaux) != 2:
            return None
        code, libelle = (part.strip() for part in morceaux)
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,10}", code)
            or not 2 <= len(libelle) <= 50
            or code.casefold() in codes_vus
        ):
            return None
        codes_vus.add(code.casefold())
        periodes.append({"code": code, "libelle": libelle})
    return periodes if 1 <= len(periodes) <= 8 else None


def _rediriger_parametres(ok: str | None = None, erreur: str | None = None) -> RedirectResponse:
    suffixe = f"?erreur={erreur}" if erreur else (f"?ok={ok}" if ok else "")
    return RedirectResponse(f"/admin/parametres-academiques{suffixe}", status_code=303)


def _instantane_configuration_academique(
    configuration: ParametresAcademiquesEtablissement,
) -> dict:
    try:
        periodes = json.loads(configuration.periodes_json or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        periodes = []
    return {
        "calendrier": configuration.calendrier,
        "periodes": periodes if isinstance(periodes, list) else [],
        "note_maximale": float(configuration.note_maximale),
        "seuil_reussite": float(configuration.seuil_reussite),
        "est_actif": bool(configuration.est_actif),
    }


def _journaliser_parametres_academiques(
    session: Session,
    *,
    admin: Utilisateur,
    etablissement_id: int,
    annee_scolaire: str,
    action: str,
    entite_type: str,
    entite_id: int | None,
    avant: dict | None,
    apres: dict | None,
    contexte: dict | None = None,
) -> None:
    """Ajoute l'événement dans la même transaction que la modification métier."""
    contexte_complet = dict(contexte or {})
    etablissement = session.get(EtablissementScolaire, etablissement_id)
    contexte_complet.setdefault(
        "etablissement",
        etablissement.nom if etablissement else f"Établissement #{etablissement_id}",
    )
    details = {
        "avant": avant,
        "apres": apres,
        "contexte": contexte_complet,
    }
    session.add(
        ParametresAcademiquesEvenement(
            etablissement_id=etablissement_id,
            annee_scolaire=annee_scolaire,
            acteur_id=admin.id,
            acteur_nom=(admin.nom or "Administrateur")[:200],
            action=action,
            entite_type=entite_type,
            entite_id=entite_id,
            details_json=json.dumps(
                details, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
            date_evenement=datetime.utcnow(),
        )
    )


def _valeur_audit_affichable(valeur) -> str:
    if valeur is None:
        return "—"
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    if isinstance(valeur, (dict, list)):
        return json.dumps(valeur, ensure_ascii=False, sort_keys=True)
    return str(valeur)


@router.get("/admin/parametres-academiques")
def page_parametres_academiques(
    request: Request,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    etablissements = session.exec(
        select(EtablissementScolaire)
        .where(
            EtablissementScolaire.est_actif == True,  # noqa: E712
            EtablissementScolaire.est_verifie == True,  # noqa: E712
        )
        .order_by(EtablissementScolaire.nom)
    ).all()
    niveaux = session.exec(
        select(NiveauScolaire)
        .where(
            NiveauScolaire.est_actif == True,  # noqa: E712
            NiveauScolaire.statut_validation == "verifie",
        )
        .order_by(NiveauScolaire.ordre, NiveauScolaire.libelle)
    ).all()
    options = session.exec(
        select(OptionScolaire)
        .where(
            OptionScolaire.est_active == True,  # noqa: E712
            OptionScolaire.statut_validation == "verifie",
        )
        .order_by(OptionScolaire.libelle)
    ).all()
    matieres = session.exec(
        select(MatiereScolaire)
        .where(
            MatiereScolaire.est_active == True,  # noqa: E712
            MatiereScolaire.statut_validation == "verifie",
        )
        .order_by(MatiereScolaire.libelle)
    ).all()
    configurations = session.exec(
        select(ParametresAcademiquesEtablissement)
        .order_by(
            ParametresAcademiquesEtablissement.est_actif.desc(),
            ParametresAcademiquesEtablissement.annee_scolaire.desc(),
            ParametresAcademiquesEtablissement.id.desc(),
        )
        .limit(300)
    ).all()
    configurations_map = {item.id: item for item in configurations}
    etablissements_map = {item.id: item for item in etablissements}
    niveaux_map = {item.id: item for item in niveaux}
    options_map = {item.id: item for item in options}
    matieres_map = {item.id: item for item in matieres}
    coefficients = session.exec(
        select(CoefficientMatiereEtablissement)
        .order_by(CoefficientMatiereEtablissement.parametres_id.desc(),
                  CoefficientMatiereEtablissement.niveau_id,
                  CoefficientMatiereEtablissement.matiere_id)
        .limit(600)
    ).all()
    coefficients_affiches = [
        {
            "coefficient": item,
            "configuration": configurations_map.get(item.parametres_id),
            "etablissement": etablissements_map.get(
                configurations_map[item.parametres_id].etablissement_id
            ) if item.parametres_id in configurations_map else None,
            "niveau": niveaux_map.get(item.niveau_id),
            "option": options_map.get(item.option_id) if item.option_id else None,
            "matiere": matieres_map.get(item.matiere_id),
        }
        for item in coefficients
    ]
    periodes_par_configuration = {}
    for configuration in configurations:
        try:
            data = json.loads(configuration.periodes_json or "[]")
            periodes_par_configuration[configuration.id] = (
                data if isinstance(data, list) else []
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            periodes_par_configuration[configuration.id] = []

    return templates.TemplateResponse(
        request,
        "admin_parametres_academiques.html",
        {
            "utilisateur": admin,
            "etablissements": etablissements,
            "niveaux": niveaux,
            "options": options,
            "matieres": matieres,
            "configurations": configurations,
            "configurations_map": configurations_map,
            "coefficients_affiches": coefficients_affiches,
            "periodes_par_configuration": periodes_par_configuration,
            "erreur": request.query_params.get("erreur", ""),
            "succes": request.query_params.get("ok", ""),
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@router.post("/admin/parametres-academiques/annee/enregistrer")
def enregistrer_parametres_annee_scolaire(
    request: Request,
    etablissement_id: int = Form(...),
    annee_scolaire: str = Form(...),
    calendrier: str = Form(...),
    periodes: str = Form(...),
    note_maximale: float = Form(...),
    seuil_reussite: float = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    etablissement = session.get(EtablissementScolaire, etablissement_id)
    if not etablissement or not etablissement.est_actif or not etablissement.est_verifie:
        return _rediriger_parametres(erreur="etablissement_non_verifie")
    annee = annee_scolaire.strip()
    match = re.fullmatch(r"(\d{4})-(\d{4})", annee)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        return _rediriger_parametres(erreur="annee_invalide")
    if calendrier not in {"trimestre", "semestre", "personnalise"}:
        return _rediriger_parametres(erreur="calendrier_invalide")
    periodes_validees = _periodes_configuration(periodes)
    if not periodes_validees:
        return _rediriger_parametres(erreur="periodes_invalides")
    if (
        not 1 <= note_maximale <= 1000
        or not 0 <= seuil_reussite <= note_maximale
    ):
        return _rediriger_parametres(erreur="bareme_invalide")

    configuration = session.exec(
        select(ParametresAcademiquesEtablissement).where(
            ParametresAcademiquesEtablissement.etablissement_id == etablissement.id,
            ParametresAcademiquesEtablissement.annee_scolaire == annee,
        )
    ).first()
    est_creation = configuration is None
    etait_active = bool(configuration.est_actif) if configuration else False
    avant_configuration = (
        _instantane_configuration_academique(configuration)
        if configuration else None
    )
    maintenant = datetime.utcnow()
    if configuration:
        configuration.calendrier = calendrier
        configuration.periodes_json = json.dumps(
            periodes_validees, ensure_ascii=False, separators=(",", ":")
        )
        configuration.note_maximale = float(note_maximale)
        configuration.seuil_reussite = float(seuil_reussite)
        configuration.est_actif = True
        configuration.date_modification = maintenant
    else:
        configuration = ParametresAcademiquesEtablissement(
            etablissement_id=etablissement.id,
            annee_scolaire=annee,
            calendrier=calendrier,
            periodes_json=json.dumps(
                periodes_validees, ensure_ascii=False, separators=(",", ":")
            ),
            note_maximale=float(note_maximale),
            seuil_reussite=float(seuil_reussite),
            est_actif=True,
            date_creation=maintenant,
            date_modification=maintenant,
        )
        session.add(configuration)
        session.flush()

    autres = session.exec(
        select(ParametresAcademiquesEtablissement).where(
            ParametresAcademiquesEtablissement.etablissement_id == etablissement.id,
            ParametresAcademiquesEtablissement.id != configuration.id,
        )
    ).all()
    for ancienne in autres:
        if ancienne.est_actif:
            avant_ancienne = _instantane_configuration_academique(ancienne)
            ancienne.est_actif = False
            ancienne.date_modification = maintenant
            session.add(ancienne)
            _journaliser_parametres_academiques(
                session,
                admin=admin,
                etablissement_id=etablissement.id,
                annee_scolaire=ancienne.annee_scolaire,
                action="desactivation",
                entite_type="configuration",
                entite_id=ancienne.id,
                avant=avant_ancienne,
                apres=_instantane_configuration_academique(ancienne),
                contexte={"raison": "activation_d_une_autre_annee"},
            )

    session.add(configuration)
    session.flush()
    action_configuration = (
        "creation" if est_creation
        else ("activation" if not etait_active else "modification")
    )
    _journaliser_parametres_academiques(
        session,
        admin=admin,
        etablissement_id=etablissement.id,
        annee_scolaire=annee,
        action=action_configuration,
        entite_type="configuration",
        entite_id=configuration.id,
        avant=avant_configuration,
        apres=_instantane_configuration_academique(configuration),
        contexte={"etablissement": etablissement.nom},
    )
    session.commit()
    return _rediriger_parametres(ok="parametres_enregistres")


@router.post("/admin/parametres-academiques/coefficient/enregistrer")
def enregistrer_coefficient_matiere(
    request: Request,
    parametres_id: int = Form(...),
    niveau_id: int = Form(...),
    option_id: str = Form(default=""),
    matiere_id: int = Form(...),
    coefficient: float = Form(...),
    obligatoire: str = Form(default="oui"),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    configuration = session.get(ParametresAcademiquesEtablissement, parametres_id)
    niveau = session.get(NiveauScolaire, niveau_id)
    matiere = session.get(MatiereScolaire, matiere_id)
    if not configuration or not configuration.est_actif:
        return _rediriger_parametres(erreur="configuration_invalide")
    etablissement = session.get(EtablissementScolaire, configuration.etablissement_id)
    if not etablissement or not etablissement.est_verifie or not etablissement.est_actif:
        return _rediriger_parametres(erreur="etablissement_non_verifie")
    if (
        not niveau or not niveau.est_actif or niveau.statut_validation != "verifie"
        or not matiere or not matiere.est_active or matiere.statut_validation != "verifie"
    ):
        return _rediriger_parametres(erreur="programme_scolaire_invalide")

    option = None
    option_pk = None
    if option_id.strip():
        try:
            option_pk = int(option_id)
        except ValueError:
            return _rediriger_parametres(erreur="option_invalide")
        option = session.get(OptionScolaire, option_pk)
        if (
            not option or not option.est_active
            or option.statut_validation != "verifie"
            or option.niveau_id != niveau.id
        ):
            return _rediriger_parametres(erreur="option_invalide")

    # Le coefficient ne peut être créé que pour une matière du programme
    # effectivement validé pour cette classe/série.
    conditions_programme = [
        ProgrammeMatiereScolaire.referentiel_id == niveau.referentiel_id,
        ProgrammeMatiereScolaire.niveau_id == niveau.id,
        ProgrammeMatiereScolaire.matiere_id == matiere.id,
        ProgrammeMatiereScolaire.statut_validation == "verifie",
    ]
    if option_pk is not None:
        programme = session.exec(
            select(ProgrammeMatiereScolaire).where(
                *conditions_programme,
                ProgrammeMatiereScolaire.option_id == option_pk,
            ).limit(1)
        ).first()
        if not programme:
            programme = session.exec(
                select(ProgrammeMatiereScolaire).where(
                    *conditions_programme,
                    ProgrammeMatiereScolaire.option_id.is_(None),
                ).limit(1)
            ).first()
    else:
        programme = session.exec(
            select(ProgrammeMatiereScolaire).where(
                *conditions_programme,
                ProgrammeMatiereScolaire.option_id.is_(None),
            ).limit(1)
        ).first()
    if not programme:
        return _rediriger_parametres(erreur="programme_scolaire_invalide")

    if not 0.01 <= coefficient <= 100:
        return _rediriger_parametres(erreur="coefficient_invalide")

    filtres_coefficient = [
        CoefficientMatiereEtablissement.parametres_id == configuration.id,
        CoefficientMatiereEtablissement.niveau_id == niveau.id,
        CoefficientMatiereEtablissement.matiere_id == matiere.id,
    ]
    if option_pk is None:
        filtres_coefficient.append(CoefficientMatiereEtablissement.option_id.is_(None))
    else:
        filtres_coefficient.append(CoefficientMatiereEtablissement.option_id == option_pk)
    entree = session.exec(
        select(CoefficientMatiereEtablissement).where(*filtres_coefficient)
    ).first()
    avant_coefficient = (
        {
            "coefficient": float(entree.coefficient),
            "obligatoire": bool(entree.obligatoire),
        }
        if entree else None
    )
    est_creation = entree is None
    maintenant = datetime.utcnow()
    if entree:
        entree.coefficient = float(coefficient)
        entree.obligatoire = obligatoire == "oui"
        entree.date_modification = maintenant
    else:
        entree = CoefficientMatiereEtablissement(
            parametres_id=configuration.id,
            niveau_id=niveau.id,
            option_id=option_pk,
            matiere_id=matiere.id,
            coefficient=float(coefficient),
            obligatoire=obligatoire == "oui",
            date_creation=maintenant,
            date_modification=maintenant,
        )
    session.add(entree)
    session.flush()
    _journaliser_parametres_academiques(
        session,
        admin=admin,
        etablissement_id=etablissement.id,
        annee_scolaire=configuration.annee_scolaire,
        action="creation" if est_creation else "modification",
        entite_type="coefficient_matiere",
        entite_id=entree.id,
        avant=avant_coefficient,
        apres={
            "coefficient": float(entree.coefficient),
            "obligatoire": bool(entree.obligatoire),
        },
        contexte={
            "niveau_id": niveau.id,
            "niveau": niveau.libelle,
            "option_id": option.id if option else None,
            "option": option.libelle if option else None,
            "matiere_id": matiere.id,
            "matiere": matiere.libelle,
        },
    )
    session.commit()
    return _rediriger_parametres(ok="coefficient_enregistre")


@router.post("/admin/parametres-academiques/coefficient/{coefficient_id}/supprimer")
def supprimer_coefficient_matiere(
    request: Request,
    coefficient_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    entree = session.get(CoefficientMatiereEtablissement, coefficient_id)
    if not entree:
        return _rediriger_parametres(erreur="coefficient_introuvable")
    configuration = session.get(ParametresAcademiquesEtablissement, entree.parametres_id)
    etablissement = (
        session.get(EtablissementScolaire, configuration.etablissement_id)
        if configuration else None
    )
    if not configuration or not etablissement:
        return _rediriger_parametres(erreur="configuration_invalide")
    niveau = session.get(NiveauScolaire, entree.niveau_id)
    option = session.get(OptionScolaire, entree.option_id) if entree.option_id else None
    matiere = session.get(MatiereScolaire, entree.matiere_id)
    avant_coefficient = {
        "coefficient": float(entree.coefficient),
        "obligatoire": bool(entree.obligatoire),
    }
    contexte = {
        "niveau_id": entree.niveau_id,
        "niveau": niveau.libelle if niveau else None,
        "option_id": entree.option_id,
        "option": option.libelle if option else None,
        "matiere_id": entree.matiere_id,
        "matiere": matiere.libelle if matiere else None,
    }
    session.delete(entree)
    _journaliser_parametres_academiques(
        session,
        admin=admin,
        etablissement_id=etablissement.id,
        annee_scolaire=configuration.annee_scolaire,
        action="suppression",
        entite_type="coefficient_matiere",
        entite_id=coefficient_id,
        avant=avant_coefficient,
        apres=None,
        contexte=contexte,
    )
    session.commit()
    return _rediriger_parametres(ok="coefficient_supprime")




@router.get("/admin/parametres-academiques/historique")
def historique_parametres_academiques(
    request: Request,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    actions = (
        "creation", "modification", "activation", "desactivation", "suppression",
    )
    filtres = []
    etablissement_id = None
    valeur_etablissement = request.query_params.get("etablissement_id", "")
    if valeur_etablissement.isdecimal() and int(valeur_etablissement) > 0:
        etablissement_id = int(valeur_etablissement)
        filtres.append(
            ParametresAcademiquesEvenement.etablissement_id == etablissement_id
        )
    annee_scolaire = request.query_params.get("annee_scolaire", "").strip()
    if annee_scolaire and re.fullmatch(r"\d{4}-\d{4}", annee_scolaire):
        filtres.append(
            ParametresAcademiquesEvenement.annee_scolaire == annee_scolaire
        )
    action = request.query_params.get("action", "").strip()
    if action in actions:
        filtres.append(ParametresAcademiquesEvenement.action == action)
    else:
        action = ""

    try:
        page = max(1, min(int(request.query_params.get("page", "1")), 100000))
    except (TypeError, ValueError):
        page = 1
    limite = 50
    evenements = session.exec(
        select(ParametresAcademiquesEvenement)
        .where(*filtres)
        .order_by(
            ParametresAcademiquesEvenement.date_evenement.desc(),
            ParametresAcademiquesEvenement.id.desc(),
        )
        .offset((page - 1) * limite)
        .limit(limite + 1)
    ).all()
    page_suivante = len(evenements) > limite
    evenements = evenements[:limite]

    ids_etablissements = {item.etablissement_id for item in evenements}
    ids_acteurs = {item.acteur_id for item in evenements if item.acteur_id is not None}
    etablissements_page = (
        session.exec(
            select(EtablissementScolaire).where(
                EtablissementScolaire.id.in_(sorted(ids_etablissements))
            )
        ).all()
        if ids_etablissements else []
    )
    acteurs_page = (
        session.exec(
            select(Utilisateur).where(Utilisateur.id.in_(sorted(ids_acteurs)))
        ).all()
        if ids_acteurs else []
    )
    etablissements_map = {item.id: item for item in etablissements_page}
    acteurs_map = {item.id: item for item in acteurs_page}

    libelles_champs = {
        "calendrier": "Calendrier",
        "periodes": "Périodes",
        "note_maximale": "Barème maximal",
        "seuil_reussite": "Seuil de réussite",
        "est_actif": "Année active",
        "coefficient": "Coefficient",
        "obligatoire": "Matière obligatoire",
    }
    lignes = []
    for evenement in evenements:
        try:
            details = json.loads(evenement.details_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        avant = details.get("avant") if isinstance(details.get("avant"), dict) else {}
        apres = details.get("apres") if isinstance(details.get("apres"), dict) else {}
        changements = []
        for cle in sorted(set(avant) | set(apres)):
            changements.append({
                "champ": libelles_champs.get(cle, cle.replace("_", " ").capitalize()),
                "avant": _valeur_audit_affichable(avant.get(cle)),
                "apres": _valeur_audit_affichable(apres.get(cle)),
            })
        contexte = details.get("contexte")
        if not isinstance(contexte, dict):
            contexte = {}
        if evenement.entite_type == "coefficient_matiere":
            cible = "Coefficient de matière"
            precision_cible = " · ".join(
                str(contexte.get(cle))
                for cle in ("niveau", "option", "matiere")
                if contexte.get(cle)
            )
        else:
            cible = "Configuration annuelle"
            precision_cible = "Paramètres généraux de l'année scolaire"
        lignes.append({
            "evenement": evenement,
            "acteur_nom": evenement.acteur_nom or (
                acteurs_map[evenement.acteur_id].nom
                if evenement.acteur_id in acteurs_map else "Compte administrateur archivé"
            ),
            "etablissement_nom": contexte.get("etablissement") or (
                etablissements_map[evenement.etablissement_id].nom
                if evenement.etablissement_id in etablissements_map
                else f"Établissement #{evenement.etablissement_id}"
            ),
            "cible": cible,
            "precision_cible": precision_cible,
            "changements": changements,
            "raison": contexte.get("raison"),
        })

    etablissements = session.exec(
        select(EtablissementScolaire).order_by(EtablissementScolaire.nom).limit(500)
    ).all()
    url_precedente = (
        str(request.url.include_query_params(page=page - 1)) if page > 1 else None
    )
    url_suivante = (
        str(request.url.include_query_params(page=page + 1))
        if page_suivante else None
    )
    return templates.TemplateResponse(
        request,
        "admin_historique_parametres_academiques.html",
        {
            "utilisateur": admin,
            "lignes": lignes,
            "etablissements": etablissements,
            "filtre_etablissement_id": etablissement_id,
            "filtre_annee_scolaire": annee_scolaire,
            "filtre_action": action,
            "actions": actions,
            "page": page,
            "url_precedente": url_precedente,
            "url_suivante": url_suivante,
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
