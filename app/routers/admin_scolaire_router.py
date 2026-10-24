"""Administration du référentiel scolaire national.

Les entrées créées dans l'interface restent non vérifiées tant qu'un
administrateur ne les a pas validées avec une source HTTPS exploitable.
Les API publiques ne publient que les lignes actives et vérifiées.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import re
import unicodedata

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, func, or_

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    CercleEtude,
    EtablissementScolaire,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
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


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


def _referentiel_courant(session: Session) -> Optional[ReferentielScolaire]:
    lignes = session.exec(
        select(ReferentielScolaire).order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).all()
    return lignes[0] if lignes else None


def _url_source_valide(source: str | None) -> bool:
    """N'accepte que des pages HTTPS du ministère malgache de l'Éducation."""
    if not source:
        return False
    try:
        parsed = urlparse(source.strip())
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    domaines_officiels = ("education.gov.mg", "metfp.gov.mg")
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
    referentiel = _referentiel_courant(session)
    niveau = session.get(NiveauScolaire, niveau_pk) if niveau_pk else None
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
    if not institution or not institution.est_active or not institution.est_verifie:
        return _erreur("etablissement_non_verifie")
    source = (source_officielle.strip() or entree.source_officielle).strip()[:500]
    if not _url_source_valide(source):
        return _erreur("source_https_requise")

    if entree.type_offre == "formation":
        parcours = session.get(ParcoursTechniqueProfessionnel, entree.parcours_etfp_id)
        if not parcours or not parcours.est_active or parcours.statut_validation != "verifie":
            return _erreur("offre_formation_invalide")
    else:
        referentiel = _referentiel_courant(session)
        niveau = session.get(NiveauScolaire, entree.niveau_scolaire_id)
        if (
            not referentiel or not niveau
            or niveau.referentiel_id != referentiel.id
            or not niveau.est_actif or niveau.statut_validation != "verifie"
        ):
            return _erreur("offre_niveau_invalide")
        if entree.type_offre == "serie":
            option = session.get(OptionScolaire, entree.option_scolaire_id)
            if (
                not option or option.niveau_id != niveau.id
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
