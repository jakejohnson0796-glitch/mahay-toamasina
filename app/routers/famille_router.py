"""Portail famille : accès borné aux rattachements vérifiés."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    Cours,
    Devoir,
    EvenementLienResponsableEleve,
    InscriptionCours,
    LienResponsableEleve,
    PointagePresence,
    RoleUtilisateur,
    RenduDevoir,
    Seance,
    StatutPointage,
    Utilisateur,
)
from ..telephone import TelephoneInvalide, normaliser_telephone
from ..templating import templates

router = APIRouter()

_TYPES_LIEN = {
    "parent": "Parent",
    "tuteur_legal": "Tuteur légal",
    "responsable_autorise": "Responsable autorisé",
}
_STATUTS_PRESENCE = ("present", "absent", "retard", "excuse")


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    admin = utilisateur_courant(request, session)
    if not admin or admin.role != RoleUtilisateur.ADMIN:
        return None
    return admin


def construire_portail_famille(session: Session, responsable_id: int) -> list[dict]:
    """Construit les seules données accessibles via les liens actifs du compte."""
    liens = session.exec(
        select(LienResponsableEleve)
        .where(
            LienResponsableEleve.responsable_id == responsable_id,
            LienResponsableEleve.statut == "actif",
        )
        .order_by(LienResponsableEleve.date_creation.desc())
    ).all()

    enfants = []
    for lien in liens:
        eleve = session.get(Utilisateur, lien.eleve_id)
        if not eleve or eleve.banni:
            continue

        inscriptions = session.exec(
            select(InscriptionCours).where(InscriptionCours.utilisateur_id == eleve.id)
        ).all()
        cours_ids = sorted({ligne.cours_id for ligne in inscriptions})
        cours_liste = (
            session.exec(select(Cours).where(Cours.id.in_(cours_ids)).order_by(Cours.nom)).all()
            if cours_ids else []
        )
        cours_infos = []

        for cours in cours_liste:
            devoirs = session.exec(
                select(Devoir).where(
                    Devoir.cours_id == cours.id,
                    Devoir.archive == False,  # noqa: E712
                ).order_by(Devoir.date_creation.desc())
            ).all()
            devoirs_par_id = {devoir.id: devoir for devoir in devoirs}
            rendus = []
            if devoirs_par_id:
                rendus = session.exec(
                    select(RenduDevoir)
                    .where(
                        RenduDevoir.utilisateur_id == eleve.id,
                        RenduDevoir.devoir_id.in_(list(devoirs_par_id)),
                        RenduDevoir.note.is_not(None),
                        RenduDevoir.date_correction.is_not(None),
                    )
                    .order_by(RenduDevoir.date_rendu.desc())
                ).all()

            notes = []
            total_pondere = 0.0
            poids_total = 0.0
            for rendu in rendus:
                devoir = devoirs_par_id.get(rendu.devoir_id)
                if not devoir or devoir.bareme <= 0 or rendu.note is None:
                    continue
                sur_vingt = round(float(rendu.note) / float(devoir.bareme) * 20, 2)
                poids = max(float(devoir.coefficient or 1), 0.1)
                total_pondere += sur_vingt * poids
                poids_total += poids
                notes.append({
                    "devoir": devoir,
                    "note": rendu.note,
                    "note_sur_20": sur_vingt,
                    "appreciation": rendu.appreciation_prof,
                    "date_correction": rendu.date_correction,
                })

            seances = session.exec(
                select(Seance).where(Seance.cours_id == cours.id)
            ).all()
            seance_ids = [seance.id for seance in seances]
            pointages = []
            if seance_ids:
                pointages = session.exec(
                    select(PointagePresence).where(
                        PointagePresence.utilisateur_id == eleve.id,
                        PointagePresence.seance_id.in_(seance_ids),
                    )
                ).all()
            compteurs = {statut: 0 for statut in _STATUTS_PRESENCE}
            for pointage in pointages:
                statut = pointage.statut.value if hasattr(pointage.statut, "value") else str(pointage.statut)
                if statut in compteurs:
                    compteurs[statut] += 1

            cours_infos.append({
                "cours": cours,
                "notes": notes[:8],
                "moyenne": round(total_pondere / poids_total, 2) if poids_total else None,
                "nb_notes": len(notes),
                "nb_seances": len(seances),
                "nb_pointages": sum(compteurs.values()),
                "presences": compteurs,
            })

        enfants.append({
            "eleve": eleve,
            "type_lien": _TYPES_LIEN.get(lien.type_lien, "Responsable"),
            "cours": cours_infos,
        })
    return enfants


def _page_admin(request: Request, session: Session, admin: Utilisateur, *, erreur: str | None = None, succes: str | None = None):
    liens = session.exec(
        select(LienResponsableEleve).order_by(LienResponsableEleve.date_creation.desc()).limit(150)
    ).all()
    evenements_bruts = session.exec(
        select(EvenementLienResponsableEleve)
        .order_by(EvenementLienResponsableEleve.date_evenement.desc())
        .limit(100)
    ).all()
    liens_evenements = []
    ids_liens_evenements = sorted({evenement.lien_id for evenement in evenements_bruts})
    if ids_liens_evenements:
        liens_evenements = session.exec(
            select(LienResponsableEleve).where(
                LienResponsableEleve.id.in_(ids_liens_evenements)
            )
        ).all()
    liens_par_id = {lien.id: lien for lien in [*liens, *liens_evenements]}
    ids_utilisateurs = {
        identifiant
        for lien in liens_par_id.values()
        for identifiant in (lien.responsable_id, lien.eleve_id, lien.verifie_par_id)
        if identifiant is not None
    }
    ids_utilisateurs.update(evenement.acteur_id for evenement in evenements_bruts)
    utilisateurs = {}
    if ids_utilisateurs:
        utilisateurs = {
            utilisateur.id: utilisateur
            for utilisateur in session.exec(
                select(Utilisateur).where(Utilisateur.id.in_(sorted(ids_utilisateurs)))
            ).all()
        }

    evenements = []
    for evenement in evenements_bruts:
        lien_evenement = liens_par_id.get(evenement.lien_id)
        evenements.append({
            "evenement": evenement,
            "responsable": utilisateurs.get(lien_evenement.responsable_id) if lien_evenement else None,
            "eleve": utilisateurs.get(lien_evenement.eleve_id) if lien_evenement else None,
            "acteur": utilisateurs.get(evenement.acteur_id),
        })
    lignes = []
    for lien in liens:
        lignes.append({
            "lien": lien,
            "responsable": utilisateurs.get(lien.responsable_id),
            "eleve": utilisateurs.get(lien.eleve_id),
            "verificateur": utilisateurs.get(lien.verifie_par_id),
            "type_lien": _TYPES_LIEN.get(lien.type_lien, lien.type_lien),
        })
    return templates.TemplateResponse(
        request,
        "admin_responsables_eleves.html",
        {
            "utilisateur": admin,
            "liens": lignes,
            "evenements": evenements,
            "erreur": erreur,
            "succes": succes,
        },
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.get("/famille")
def portail_famille(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if (
        utilisateur.role != RoleUtilisateur.RESPONSABLE
        or utilisateur.profil_souhaite != "responsable"
    ):
        return RedirectResponse("/dashboard", status_code=303)

    enfants = construire_portail_famille(session, utilisateur.id)
    return templates.TemplateResponse(
        request,
        "famille_portail.html",
        {"utilisateur": utilisateur, "enfants": enfants},
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.get("/admin/responsables-eleves")
def page_admin_responsables_eleves(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    erreurs = {
        "telephone": "Le numéro du responsable ou de l'élève doit être un mobile malgache valide.",
        "identifiant": "Renseignez soit le téléphone, soit l'identifiant institutionnel de l'élève (un seul des deux).",
        "comptes": "Compte responsable ou compte élève introuvable.",
        "profil": "Le compte parent doit avoir été créé avec le profil responsable légal.",
        "eleve": "Le compte ciblé doit être un compte élève distinct du responsable.",
        "preuve": "Confirmez que l'autorité légale a été vérifiée auprès de l'établissement.",
        "existant": "Ce rattachement est déjà actif.",
        "integrite": "Le rattachement n'a pas pu être enregistré. Vérifiez les comptes et réessayez.",
        "lien": "Le rattachement demandé est introuvable.",
    }
    succes = {
        "actif": "Le rattachement vérifié est actif.",
        "revoque": "L'accès du responsable a été révoqué.",
    }
    return _page_admin(
        request, session, admin,
        erreur=erreurs.get(request.query_params.get("erreur", "")),
        succes=succes.get(request.query_params.get("ok", "")),
    )


@router.post("/admin/responsables-eleves/associer")
def associer_responsable_eleve(
    request: Request,
    telephone_responsable: str = Form(...),
    telephone_eleve: str = Form(""),
    identifiant_eleve: str = Form(""),
    type_lien: str = Form("parent"),
    verification_confirmee: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    if verification_confirmee != "oui":
        return RedirectResponse("/admin/responsables-eleves?erreur=preuve", status_code=303)
    if type_lien not in _TYPES_LIEN:
        return RedirectResponse("/admin/responsables-eleves?erreur=integrite", status_code=303)

    identifiant_eleve_nettoye = (identifiant_eleve or "").strip()
    telephone_eleve_saisi = (telephone_eleve or "").strip()
    if bool(identifiant_eleve_nettoye) == bool(telephone_eleve_saisi):
        return RedirectResponse("/admin/responsables-eleves?erreur=identifiant", status_code=303)
    if len(identifiant_eleve_nettoye) > 160:
        return RedirectResponse("/admin/responsables-eleves?erreur=identifiant", status_code=303)

    try:
        telephone_parent = normaliser_telephone(telephone_responsable)
        telephone_enfant = (
            normaliser_telephone(telephone_eleve_saisi)
            if telephone_eleve_saisi else None
        )
    except TelephoneInvalide:
        return RedirectResponse("/admin/responsables-eleves?erreur=telephone", status_code=303)

    responsable = session.exec(
        select(Utilisateur).where(
            Utilisateur.telephone == telephone_parent,
            Utilisateur.profil_souhaite == "responsable",
        )
    ).first()
    eleve = session.exec(
        select(Utilisateur).where(
            Utilisateur.telephone == telephone_enfant
            if telephone_enfant else
            Utilisateur.identifiant_connexion == identifiant_eleve_nettoye
        )
    ).first()
    if not responsable or not eleve:
        return RedirectResponse("/admin/responsables-eleves?erreur=comptes", status_code=303)
    if responsable.role != RoleUtilisateur.RESPONSABLE:
        return RedirectResponse("/admin/responsables-eleves?erreur=profil", status_code=303)
    if (
        responsable.banni
        or eleve.banni
        or responsable.id == eleve.id
        or eleve.role != RoleUtilisateur.ETUDIANT
        or eleve.profil_souhaite != "eleve"
    ):
        return RedirectResponse("/admin/responsables-eleves?erreur=eleve", status_code=303)

    lien = session.exec(
        select(LienResponsableEleve).where(
            LienResponsableEleve.responsable_id == responsable.id,
            LienResponsableEleve.eleve_id == eleve.id,
        )
    ).first()
    maintenant = datetime.utcnow()
    if lien and lien.statut == "actif":
        return RedirectResponse("/admin/responsables-eleves?erreur=existant", status_code=303)

    action_auditee = "reactivation" if lien else "validation"
    if lien:
        lien.type_lien = type_lien
        lien.statut = "actif"
        lien.verifie_par_id = admin.id
        lien.date_verification = maintenant
        # Conserver la date de création et les champs de dernière révocation :
        # l'historique append-only ci-dessous garde chaque décision.
        session.add(lien)
    else:
        lien = LienResponsableEleve(
            responsable_id=responsable.id,
            eleve_id=eleve.id,
            type_lien=type_lien,
            statut="actif",
            verifie_par_id=admin.id,
            date_verification=maintenant,
            date_creation=maintenant,
        )
        session.add(lien)
    try:
        session.flush()
        session.add(EvenementLienResponsableEleve(
            lien_id=lien.id,
            acteur_id=admin.id,
            action=action_auditee,
            type_lien=type_lien,
            date_evenement=maintenant,
        ))
        session.commit()
    except IntegrityError:
        session.rollback()
        return RedirectResponse("/admin/responsables-eleves?erreur=integrite", status_code=303)
    return RedirectResponse("/admin/responsables-eleves?ok=actif", status_code=303)


@router.post("/admin/responsables-eleves/{lien_id}/revoquer")
def revoquer_lien_responsable_eleve(
    lien_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    lien = session.get(LienResponsableEleve, lien_id)
    if not lien:
        return RedirectResponse("/admin/responsables-eleves?erreur=lien", status_code=303)
    if lien.statut == "actif":
        lien.statut = "revoque"
        lien.revoque_par_id = admin.id
        lien.date_revocation = datetime.utcnow()
        session.add(lien)
        session.add(EvenementLienResponsableEleve(
            lien_id=lien.id,
            acteur_id=admin.id,
            action="revocation",
            type_lien=lien.type_lien,
            date_evenement=lien.date_revocation,
        ))
        session.commit()
    return RedirectResponse("/admin/responsables-eleves?ok=revoque", status_code=303)
