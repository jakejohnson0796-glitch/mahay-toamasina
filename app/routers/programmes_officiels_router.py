"""Administration du référentiel national des programmes EP/FRP."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import utilisateur_courant
from ..client_ip import adresse_ip_client
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    LeconReferentielle,
    MatiereScolaire,
    NiveauScolaire,
    OptionScolaire,
    ProgrammeMatiereScolaire,
    ReferentielScolaire,
    RoleUtilisateur,
    StatutLeconReferentielle,
    Utilisateur,
)
from ..models_programmes_officiels import (
    ElementProgrammeOfficiel,
    ProgrammeOfficielScolaire,
)
from ..programme_storage import (
    sauvegarder_programme_officiel,
    supprimer_programme_officiel,
    url_telechargement_programme,
    ouvrir_programme_officiel,
)
from ..programmes_officiels import (
    est_source_officielle,
    normaliser_code_element,
    proposer_structure_programme,
    extraction_validable_apres_controle_manuel,
)
from ..rate_limit import limite_depassee
from ..templating import templates
from ..text_extraction import ExtractionSaturee, extraire_texte
from ..upload_validation import valider_upload

router = APIRouter()
TAILLE_MAX_IMPORT = 20 * 1024 * 1024
EXTENSIONS_PROGRAMME = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
MIN_TEXTE_VALIDABLE = 80


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


def _redirect(etat: str, programme_id: Optional[int] = None) -> RedirectResponse:
    cible = f"/admin/programmes-officiels?etat={etat}"
    if programme_id is not None:
        cible = f"/admin/programmes-officiels/{programme_id}?etat={etat}"
    return RedirectResponse(cible, status_code=303)


def _association_valide(session: Session, programme_matiere_id: int):
    association = session.get(ProgrammeMatiereScolaire, programme_matiere_id)
    if not association or association.statut_validation != "verifie":
        return None
    niveau = session.get(NiveauScolaire, association.niveau_id)
    matiere = session.get(MatiereScolaire, association.matiere_id)
    option = (
        session.get(OptionScolaire, association.option_id)
        if association.option_id else None
    )
    referentiel = session.get(ReferentielScolaire, association.referentiel_id)
    if (
        not referentiel
        or referentiel.statut in {"historique", "archive"}
        or not niveau or not matiere
        or niveau.referentiel_id != association.referentiel_id
        or niveau.statut_validation != "verifie"
        or not niveau.est_actif
        or matiere.statut_validation != "verifie"
        or not matiere.est_active
        or (association.option_id and (
            not option
            or option.referentiel_id != association.referentiel_id
            or option.niveau_id != niveau.id
            or option.statut_validation != "verifie"
            or not option.est_active
        ))
    ):
        return None
    return association


def _libelle_association(session: Session, association: ProgrammeMatiereScolaire) -> str:
    niveau = session.get(NiveauScolaire, association.niveau_id)
    matiere = session.get(MatiereScolaire, association.matiere_id)
    option = session.get(OptionScolaire, association.option_id) if association.option_id else None
    morceaux = [
        niveau.libelle if niveau else "Niveau inconnu",
        option.libelle if option else "",
        matiere.libelle if matiere else "Matière inconnue",
    ]
    return " · ".join(part for part in morceaux if part)


def _extraire_depuis_stockage(chemin_fichier: str) -> str:
    """L'extraction passe par le stockage privé existant, avec OCR borné."""
    from ..storage import ouvrir_fichier_local

    with ouvrir_programme_officiel(chemin_fichier) as chemin_local:
        return extraire_texte(str(chemin_local))


@router.get("/admin/programmes-officiels")
def page_programmes_officiels(
    request: Request,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    associations = session.exec(
        select(ProgrammeMatiereScolaire)
        .where(ProgrammeMatiereScolaire.statut_validation == "verifie")
        .order_by(ProgrammeMatiereScolaire.id.desc())
        .limit(300)
    ).all()
    programmes = session.exec(
        select(ProgrammeOfficielScolaire)
        .order_by(ProgrammeOfficielScolaire.date_import.desc())
        .limit(100)
    ).all()

    # Charge les dépendances en lots pour éviter des centaines de requêtes
    # lorsqu'un référentiel contient de nombreuses classes et matières.
    ids_associations = {a.id for a in associations}
    ids_associations.update(p.programme_matiere_id for p in programmes)
    associations_completes = session.exec(
        select(ProgrammeMatiereScolaire).where(
            ProgrammeMatiereScolaire.id.in_(ids_associations)
        )
    ).all() if ids_associations else []
    associations_map_obj = {a.id: a for a in associations_completes}
    niveaux_ids = {a.niveau_id for a in associations_completes}
    matieres_ids = {a.matiere_id for a in associations_completes}
    options_ids = {a.option_id for a in associations_completes if a.option_id}
    niveaux_map = {
        n.id: n for n in (
            session.exec(select(NiveauScolaire).where(NiveauScolaire.id.in_(niveaux_ids))).all()
            if niveaux_ids else []
        )
    }
    matieres_map = {
        m.id: m for m in (
            session.exec(select(MatiereScolaire).where(MatiereScolaire.id.in_(matieres_ids))).all()
            if matieres_ids else []
        )
    }
    options_map = {
        o.id: o for o in (
            session.exec(select(OptionScolaire).where(OptionScolaire.id.in_(options_ids))).all()
            if options_ids else []
        )
    }
    referentiels_ids = {a.referentiel_id for a in associations_completes}
    referentiels_map = {
        r.id: r for r in (
            session.exec(select(ReferentielScolaire).where(ReferentielScolaire.id.in_(referentiels_ids))).all()
            if referentiels_ids else []
        )
    }

    def association_valide_pour_page(association):
        niveau = niveaux_map.get(association.niveau_id)
        matiere = matieres_map.get(association.matiere_id)
        option = options_map.get(association.option_id) if association.option_id else None
        referentiel = referentiels_map.get(association.referentiel_id)
        return bool(
            referentiel and referentiel.statut not in {"historique", "archive"}
            and niveau and niveau.referentiel_id == association.referentiel_id
            and niveau.est_actif and niveau.statut_validation == "verifie"
            and matiere and matiere.est_active and matiere.statut_validation == "verifie"
            and (
                association.option_id is None
                or (option and option.referentiel_id == association.referentiel_id
                    and option.niveau_id == niveau.id
                    and option.est_active and option.statut_validation == "verifie")
            )
        )

    def libelle_pour_page(association):
        niveau = niveaux_map.get(association.niveau_id)
        matiere = matieres_map.get(association.matiere_id)
        option = options_map.get(association.option_id) if association.option_id else None
        return " · ".join(
            part for part in (
                niveau.libelle if niveau else "Niveau inconnu",
                option.libelle if option else "",
                matiere.libelle if matiere else "Matière inconnue",
            ) if part
        )

    associations_valides = [
        a for a in associations
        if a.id in associations_map_obj and association_valide_pour_page(a)
    ]
    associations_vues = [
        {"association": a, "libelle": libelle_pour_page(a)}
        for a in associations_valides
    ]
    associations_map = {
        identifiant: libelle_pour_page(association)
        for identifiant, association in associations_map_obj.items()
    }

    repartition = session.exec(
        select(
            ProgrammeOfficielScolaire.statut_validation,
            func.count(ProgrammeOfficielScolaire.id),
        ).group_by(ProgrammeOfficielScolaire.statut_validation)
    ).all()
    comptes_statuts = {statut: int(nombre) for statut, nombre in repartition}
    stats = {
        "total": sum(comptes_statuts.values()),
        "a_verifier": comptes_statuts.get("a_verifier", 0),
        "verifies": comptes_statuts.get("verifie", 0),
        "rejetes": comptes_statuts.get("rejete", 0),
    }

    # Une seule agrégation pour toute la couverture, au lieu de requêtes
    # répétées document/élément pour chacune des associations.
    couverture_ids = [a.id for a in associations_valides]
    couverture_stats = {}
    if couverture_ids:
        lignes_couverture = session.exec(
            select(
                ProgrammeOfficielScolaire.programme_matiere_id,
                func.count(func.distinct(ProgrammeOfficielScolaire.id)),
                func.count(ElementProgrammeOfficiel.id),
            )
            .select_from(ProgrammeOfficielScolaire)
            .outerjoin(
                ElementProgrammeOfficiel,
                (ElementProgrammeOfficiel.programme_id == ProgrammeOfficielScolaire.id)
                & (ElementProgrammeOfficiel.statut_validation == "verifie"),
            )
            .where(
                ProgrammeOfficielScolaire.programme_matiere_id.in_(couverture_ids),
                ProgrammeOfficielScolaire.statut_validation == "verifie",
            )
            .group_by(ProgrammeOfficielScolaire.programme_matiere_id)
        ).all()
        couverture_stats = {
            identifiant: (int(nb_documents), int(nb_elements))
            for identifiant, nb_documents, nb_elements in lignes_couverture
        }

    couverture = [
        {
            "libelle": libelle_pour_page(association),
            "documents": couverture_stats.get(association.id, (0, 0))[0],
            "elements": couverture_stats.get(association.id, (0, 0))[1],
        }
        for association in associations_valides
    ]

    return templates.TemplateResponse(
        request,
        "admin_programmes_officiels.html",
        {
            "utilisateur": admin,
            "programme": None,
            "programmes": programmes,
            "associations": associations_vues,
            "associations_map": associations_map,
            "stats": stats,
            "couverture": couverture,
            "etat": request.query_params.get("etat", ""),
            "erreur": request.query_params.get("erreur", ""),
        },
    )


@router.post("/admin/programmes-officiels/importer")
async def importer_programme_officiel(
    request: Request,
    intitule: str = Form(...),
    organisme_emetteur: str = Form(...),
    type_document: str = Form(...),
    programme_matiere_id: int = Form(...),
    version_officielle: str = Form(default=""),
    annee_publication: Optional[int] = Form(default=None),
    annee_scolaire: str = Form(default=""),
    source_url: str = Form(default=""),
    reference_source: str = Form(...),
    version_precedente_id: Optional[int] = Form(default=None),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    if limite_depassee(
        f"programmes-officiels:user:{admin.id}", 8, 3600
    ) or limite_depassee(
        f"programmes-officiels:ip:{adresse_ip_client(request)}", 16, 3600
    ):
        return _redirect("limite_import")

    titre = " ".join(intitule.split())[:250]
    organisme = " ".join(organisme_emetteur.split())[:180]
    type_document = type_document.strip().upper()
    version = " ".join(version_officielle.split())[:80]
    annee_scolaire = annee_scolaire.strip()[:20]
    source = source_url.strip()[:1200]
    reference = " ".join(reference_source.split())[:1200]

    if len(titre) < 5 or len(organisme) < 3 or len(reference) < 8:
        return _redirect("metadonnees_invalides")
    if type_document not in {"EP", "FRP", "AUTRE"}:
        return _redirect("type_document_invalide")
    if annee_publication is not None and not 1900 <= annee_publication <= datetime.utcnow().year + 1:
        return _redirect("annee_invalide")
    if source and not est_source_officielle(source):
        return _redirect("source_non_officielle")
    association = _association_valide(session, programme_matiere_id)
    if not association:
        return _redirect("association_non_verifiee")
    if version_precedente_id is not None:
        precedent = session.get(ProgrammeOfficielScolaire, version_precedente_id)
        if (
            not precedent
            or precedent.programme_matiere_id != programme_matiere_id
            or precedent.type_document != type_document
            or precedent.statut_validation != "verifie"
        ):
            return _redirect("version_precedente_invalide")

    nom_fichier = Path(fichier.filename or "programme").name
    extension = Path(nom_fichier).suffix.lower()
    if extension not in EXTENSIONS_PROGRAMME:
        return _redirect("format_non_accepte")

    contenu = await fichier.read(TAILLE_MAX_IMPORT + 1)
    try:
        mime = valider_upload(
            contenu, nom_fichier, TAILLE_MAX_IMPORT, EXTENSIONS_PROGRAMME
        )
    except ValueError:
        return _redirect("fichier_invalide")
    empreinte = hashlib.sha256(contenu).hexdigest()
    doublon = session.exec(
        select(ProgrammeOfficielScolaire).where(
            ProgrammeOfficielScolaire.empreinte_sha256 == empreinte
        )
    ).first()
    if doublon:
        return _redirect("fichier_deja_importe", doublon.id)

    reference_stockage = f"epfrp-{secrets.token_hex(20)}"
    chemin = None
    try:
        chemin = sauvegarder_programme_officiel(
            reference_stockage, nom_fichier, contenu, mime
        )
    except Exception:
        return _redirect("stockage_indisponible")

    try:
        try:
            texte = await asyncio.to_thread(_extraire_depuis_stockage, chemin)
        except Exception:
            texte = ""
        texte = (texte or "")[:300_000]
        nombre_caracteres = len(texte.strip())
        if nombre_caracteres >= MIN_TEXTE_VALIDABLE:
            statut_extraction = "extrait"
        elif nombre_caracteres:
            statut_extraction = "partiel"
        else:
            statut_extraction = "echec"

        programme = ProgrammeOfficielScolaire(
            code=f"{type_document}-{empreinte[:20].upper()}",
            intitule=titre,
            organisme_emetteur=organisme,
            type_document=type_document,
            annee_publication=annee_publication,
            annee_scolaire=annee_scolaire or None,
            version_officielle=version,
            programme_matiere_id=programme_matiere_id,
            source_url=source or None,
            reference_source=reference,
            nom_fichier_original=nom_fichier[:255],
            chemin_fichier=chemin,
            type_mime=mime,
            empreinte_sha256=empreinte,
            taille_octets=len(contenu),
            texte_extrait=texte,
            statut_extraction=statut_extraction,
            nombre_caracteres_extraits=nombre_caracteres,
            version_precedente_id=version_precedente_id,
            importe_par_id=admin.id,
        )
        session.add(programme)
        session.flush()

        suggestions = proposer_structure_programme(texte)
        noeuds_par_code = {}
        for suggestion in suggestions:
            parent_code = suggestion.get("parent_code")
            parent = noeuds_par_code.get(parent_code)
            element = ElementProgrammeOfficiel(
                programme_id=programme.id,
                parent_id=parent.id if parent else None,
                code=str(suggestion["code"])[:60],
                type_element=str(suggestion["type_element"]),
                titre=str(suggestion["titre"])[:240],
                contenu=str(suggestion.get("contenu") or "")[:100_000],
                ordre=int(suggestion.get("ordre") or 0),
                statut_validation="a_verifier",
            )
            session.add(element)
            session.flush()
            noeuds_par_code[element.code] = element

        session.commit()
        session.refresh(programme)
        return _redirect("import_reussi", programme.id)
    except Exception:
        session.rollback()
        if chemin:
            supprimer_programme_officiel(chemin)
        return _redirect("erreur_enregistrement")


@router.get("/admin/programmes-officiels/{programme_id}")
def detail_programme_officiel(
    request: Request,
    programme_id: int,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    if not programme:
        return _redirect("programme_introuvable")
    association = session.get(ProgrammeMatiereScolaire, programme.programme_matiere_id)
    elements = session.exec(
        select(ElementProgrammeOfficiel)
        .where(ElementProgrammeOfficiel.programme_id == programme.id)
        .order_by(ElementProgrammeOfficiel.ordre, ElementProgrammeOfficiel.id)
    ).all()
    parents = {e.id: e for e in elements}
    elements_vues = [
        {"element": e, "parent": parents.get(e.parent_id)}
        for e in elements
    ]
    return templates.TemplateResponse(
        request,
        "admin_programmes_officiels.html",
        {
            "utilisateur": admin,
            "programme": programme,
            "association_libelle": _libelle_association(session, association) if association else "Association inconnue",
            "elements": elements_vues,
            "etat": request.query_params.get("etat", ""),
            "erreur": request.query_params.get("erreur", ""),
        },
    )


@router.get("/admin/programmes-officiels/{programme_id}/fichier")
def telecharger_programme_officiel(
    request: Request,
    programme_id: int,
    session: Session = Depends(get_session),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    if not programme:
        return _redirect("programme_introuvable")
    url = url_telechargement_programme(programme.chemin_fichier)
    if url:
        return RedirectResponse(url, status_code=302)
    chemin = Path(programme.chemin_fichier)
    if not chemin.is_file():
        return _redirect("fichier_indisponible", programme.id)
    return FileResponse(
        str(chemin),
        filename=programme.nom_fichier_original,
        media_type=programme.type_mime,
    )


@router.post("/admin/programmes-officiels/{programme_id}/valider")
def valider_programme_officiel(
    request: Request,
    programme_id: int,
    motif_validation: str = Form(...),
    lecture_originale_confirmee: str = Form(default=""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.exec(
        select(ProgrammeOfficielScolaire)
        .where(ProgrammeOfficielScolaire.id == programme_id)
        .with_for_update()
    ).first()
    if not programme or programme.statut_validation != "a_verifier":
        return _redirect("programme_non_validable", programme_id)
    confirmation_original = lecture_originale_confirmee.strip().lower() in {"oui", "on", "true", "1"}
    if not extraction_validable_apres_controle_manuel(
        programme.nombre_caracteres_extraits, confirmation_original
    ):
        return _redirect("extraction_insuffisante", programme_id)
    if not (
        est_source_officielle(programme.source_url)
        or len(programme.reference_source.strip()) >= 20
    ):
        return _redirect("preuve_source_insuffisante", programme_id)
    motif = " ".join(motif_validation.split())
    if len(motif) < 50 or len(motif) > 4000:
        return _redirect("motif_trop_court", programme_id)
    if not _association_valide(session, programme.programme_matiere_id):
        return _redirect("association_non_verifiee", programme_id)

    programme.statut_validation = "verifie"
    programme.motif_validation = (
        motif + (" · Original consulté manuellement par l’administrateur." if confirmation_original and programme.nombre_caracteres_extraits < MIN_TEXTE_VALIDABLE else "")
    )[:4000]
    programme.verifie_par_id = admin.id
    programme.date_verification = datetime.utcnow()
    session.add(programme)
    session.commit()
    return _redirect("programme_valide", programme.id)


@router.post("/admin/programmes-officiels/{programme_id}/rejeter")
def rejeter_programme_officiel(
    request: Request,
    programme_id: int,
    motif_validation: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    motif = " ".join(motif_validation.split())
    if not programme or programme.statut_validation != "a_verifier" or len(motif) < 30:
        return _redirect("rejet_invalide", programme_id)
    programme.statut_validation = "rejete"
    programme.motif_validation = motif[:4000]
    programme.verifie_par_id = admin.id
    programme.date_verification = datetime.utcnow()
    session.add(programme)
    session.commit()
    return _redirect("programme_rejete", programme.id)


@router.post("/admin/programmes-officiels/{programme_id}/elements/creer")
def creer_element_programme(
    request: Request,
    programme_id: int,
    type_element: str = Form(...),
    titre: str = Form(...),
    contenu: str = Form(default=""),
    parent_id: Optional[int] = Form(default=None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    titre_nettoye = " ".join(titre.split())[:240]
    contenu_nettoye = contenu.strip()[:100_000]
    if (
        not programme or programme.statut_validation != "verifie"
        or type_element not in {"chapitre", "lecon", "rubrique", "objectif"}
        or len(titre_nettoye) < 3
    ):
        return _redirect("element_invalide", programme_id)
    parent = session.get(ElementProgrammeOfficiel, parent_id) if parent_id else None
    if parent_id and (not parent or parent.programme_id != programme.id):
        return _redirect("parent_invalide", programme_id)
    ordre = len(session.exec(
        select(ElementProgrammeOfficiel).where(
            ElementProgrammeOfficiel.programme_id == programme.id
        )
    ).all()) + 1
    element = ElementProgrammeOfficiel(
        programme_id=programme.id,
        parent_id=parent.id if parent else None,
        code=normaliser_code_element(titre_nettoye, ordre),
        type_element=type_element,
        titre=titre_nettoye,
        contenu=contenu_nettoye,
        ordre=ordre,
    )
    session.add(element)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return _redirect("code_element_existant", programme_id)
    return _redirect("element_ajoute", programme_id)


@router.post("/admin/programmes-officiels/{programme_id}/elements/{element_id}/valider")
def valider_element_programme(
    request: Request,
    programme_id: int,
    element_id: int,
    motif_validation: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    element = session.get(ElementProgrammeOfficiel, element_id)
    motif = " ".join(motif_validation.split())
    if (
        not programme or programme.statut_validation != "verifie"
        or not element or element.programme_id != programme.id
        or element.statut_validation != "a_verifier"
        or len(motif) < 30 or len(motif) > 2000
    ):
        return _redirect("element_non_validable", programme_id)

    if element.type_element == "lecon":
        association = _association_valide(session, programme.programme_matiere_id)
        if not association:
            return _redirect("association_non_verifiee", programme_id)
        parent = session.get(ElementProgrammeOfficiel, element.parent_id) if element.parent_id else None
        if element.parent_id and (
            not parent
            or parent.programme_id != programme.id
            or parent.statut_validation != "verifie"
        ):
            return _redirect("parent_non_verifie", programme_id)

        # Retrouve le chapitre supérieur même si le document comporte des
        # rubriques intermédiaires ; la chaîne reste bornée et liée au même EP/FRP.
        chapitre = ""
        ancetre = parent
        profondeur = 0
        while ancetre and profondeur < 20:
            if ancetre.programme_id != programme.id or ancetre.statut_validation != "verifie":
                return _redirect("hierarchie_non_verifiee", programme_id)
            if ancetre.type_element == "chapitre":
                chapitre = ancetre.titre
                break
            ancetre = (
                session.get(ElementProgrammeOfficiel, ancetre.parent_id)
                if ancetre.parent_id else None
            )
            profondeur += 1
        if ancetre and profondeur >= 20:
            return _redirect("hierarchie_trop_profonde", programme_id)

        code_lecon = f"PO{programme.id}-E{element.id}"
        lecon = LeconReferentielle(
            programme_matiere_id=programme.programme_matiere_id,
            code=code_lecon[:40],
            chapitre=chapitre[:200],
            titre=element.titre[:240],
            objectifs_pedagogiques="",
            source_officielle=(
                programme.source_url
                or f"Document officiel : {programme.reference_source}"
            )[:1200],
            reference_source=(
                f"{programme.type_document} · {programme.organisme_emetteur} · "
                f"{programme.reference_source} · version {programme.version_officielle or 'non précisée'}"
            )[:1000],
            statut_validation=StatutLeconReferentielle.VERIFIEE.value,
            cree_par_id=admin.id,
            valide_par_id=admin.id,
            date_validation=datetime.utcnow(),
            motif_validation=motif[:2000],
            statut_publication="non_publie",
        )
        session.add(lecon)
        session.flush()
        element.lecon_referentielle_id = lecon.id

    element.statut_validation = "verifie"
    element.motif_validation = motif
    element.valide_par_id = admin.id
    element.date_validation = datetime.utcnow()
    session.add(element)
    session.commit()
    return _redirect("element_valide", programme.id)


@router.post("/admin/programmes-officiels/{programme_id}/elements/{element_id}/rejeter")
def rejeter_element_programme(
    request: Request,
    programme_id: int,
    element_id: int,
    motif_validation: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)
    programme = session.get(ProgrammeOfficielScolaire, programme_id)
    element = session.get(ElementProgrammeOfficiel, element_id)
    motif = " ".join(motif_validation.split())
    if (
        not programme or not element or element.programme_id != programme_id
        or programme.statut_validation != "verifie"
        or element.statut_validation != "a_verifier" or len(motif) < 30
    ):
        return _redirect("rejet_element_invalide", programme_id)
    element.statut_validation = "rejete"
    element.motif_validation = motif[:2000]
    element.valide_par_id = admin.id
    element.date_validation = datetime.utcnow()
    session.add(element)
    session.commit()
    return _redirect("element_rejete", programme_id)
