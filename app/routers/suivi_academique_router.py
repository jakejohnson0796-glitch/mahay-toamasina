"""Carnet de notes, suivi des présences et rapports académiques."""
from __future__ import annotations
import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from ..auth import utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    Cours, Devoir, InscriptionCours, Notification, PointagePresence,
    PresenceSeance, RenduDevoir, RoleUtilisateur, Seance, StatutPointage,
    TypeNotification, Utilisateur,
)
from ..templating import templates

router = APIRouter()

def _peut_gerer(cours: Cours, utilisateur: Optional[Utilisateur]) -> bool:
    return bool(utilisateur and (
        utilisateur.role == RoleUtilisateur.ADMIN or utilisateur.id == cours.professeur_id
    ))

def _est_inscrit(session: Session, cours_id: int, utilisateur_id: int) -> bool:
    return session.exec(select(InscriptionCours).where(
        InscriptionCours.cours_id == cours_id,
        InscriptionCours.utilisateur_id == utilisateur_id,
    )).first() is not None

def normaliser_statut_pointage(valeur: str) -> StatutPointage:
    try:
        return StatutPointage((valeur or "").strip())
    except ValueError as erreur:
        raise ValueError("Statut de présence invalide.") from erreur

def calculer_moyenne_ponderee(rendus: list, devoirs: dict[int, Devoir], periode: Optional[str] = None) -> Optional[float]:
    """Moyenne sur 20 ; seules les notes officielles sont prises en compte."""
    numerateur = denominateur = 0.0
    cible = (periode or "").strip().casefold() if periode is not None else None
    for rendu in rendus:
        devoir = devoirs.get(rendu.devoir_id)
        if not devoir or rendu.note is None:
            continue
        nom_periode = (devoir.periode or "Sans période").strip()
        if cible is not None and nom_periode.casefold() != cible:
            continue
        try:
            bareme, coefficient, note = float(devoir.bareme), float(getattr(devoir, "coefficient", 1) or 1), float(rendu.note)
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(v) for v in (bareme, coefficient, note)) or bareme <= 0 or coefficient <= 0 or not 0 <= note <= bareme:
            continue
        numerateur += note / bareme * 20 * coefficient
        denominateur += coefficient
    return round(numerateur / denominateur, 2) if denominateur else None

def _construire_carnet(session: Session, cours: Cours, etudiants: list[Utilisateur], inclure_archives: bool) -> dict:
    q = select(Devoir).where(Devoir.cours_id == cours.id)
    if not inclure_archives:
        q = q.where(Devoir.archive == False)  # noqa: E712
    devoirs = session.exec(q.order_by(Devoir.date_creation, Devoir.id)).all()
    ids = [d.id for d in devoirs]
    rendus = session.exec(select(RenduDevoir).where(RenduDevoir.devoir_id.in_(ids)).order_by(RenduDevoir.date_rendu.desc())).all() if ids else []
    par_cle = {}
    for r in rendus:
        par_cle.setdefault((r.utilisateur_id, r.devoir_id), r)
    par_id = {d.id: d for d in devoirs}
    periodes = sorted({(d.periode or "Sans période").strip() or "Sans période" for d in devoirs}, key=str.casefold)
    lignes = []
    for etudiant in etudiants:
        propres = [par_cle[(etudiant.id, d.id)] for d in devoirs if (etudiant.id, d.id) in par_cle]
        notes = [{"devoir": d, "rendu": par_cle.get((etudiant.id, d.id))} for d in devoirs]
        moyennes_periode = [{"nom": p, "moyenne": calculer_moyenne_ponderee(propres, par_id, p)} for p in periodes]
        lignes.append({
            "utilisateur": etudiant, "notes": notes,
            "moyenne": calculer_moyenne_ponderee(propres, par_id),
            "moyennes_periode": moyennes_periode,
            "nb_rendus": len(propres), "nb_corriges": sum(1 for r in propres if r.note is not None),
        })
    moyennes = [l["moyenne"] for l in lignes if l["moyenne"] is not None]
    return {
        "devoirs": devoirs, "lignes": lignes, "periodes": periodes,
        "moyenne_classe": round(sum(moyennes) / len(moyennes), 2) if moyennes else None,
        "nb_etudiants": len(etudiants),
        "nb_rendus": sum(l["nb_rendus"] for l in lignes),
        "nb_corriges": sum(l["nb_corriges"] for l in lignes),
    }

@router.get("/mes-notes")
def page_mes_notes(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    inscriptions = session.exec(select(InscriptionCours).where(InscriptionCours.utilisateur_id == utilisateur.id)).all()
    ids = sorted({i.cours_id for i in inscriptions})
    cours_map = {c.id: c for c in session.exec(select(Cours).where(Cours.id.in_(ids))).all()} if ids else {}
    informations = []
    for cid in ids:
        cours = cours_map.get(cid)
        if cours:
            informations.append({"cours": cours, **_construire_carnet(session, cours, [utilisateur], False)})
    return templates.TemplateResponse(request, "mes_notes.html", {"utilisateur": utilisateur, "cours_info": informations})

@router.get("/mes-presences")
def page_mes_presences(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    pointages = session.exec(select(PointagePresence).where(
        PointagePresence.utilisateur_id == utilisateur.id
    ).order_by(PointagePresence.date_maj.desc())).all()
    compteurs = {s.value: 0 for s in StatutPointage}
    lignes, cache_seances, cache_cours = [], {}, {}
    for p in pointages:
        if p.statut == StatutPointage.A_RENSEIGNER:
            continue
        compteurs[p.statut.value] += 1
        seance = cache_seances.get(p.seance_id)
        if p.seance_id not in cache_seances:
            seance = session.get(Seance, p.seance_id)
            cache_seances[p.seance_id] = seance
        if not seance:
            continue
        cours = cache_cours.get(seance.cours_id)
        if seance.cours_id not in cache_cours:
            cours = session.get(Cours, seance.cours_id)
            cache_cours[seance.cours_id] = cours
        if cours:
            lignes.append({"pointage": p, "seance": seance, "cours": cours})
    return templates.TemplateResponse(request, "mes_presences.html", {
        "utilisateur": utilisateur, "lignes": lignes, "compteurs": compteurs,
    })

@router.get("/classe/{cours_id}/carnet-notes")
def page_carnet_notes(cours_id: int, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    cours = session.get(Cours, cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)
    professeur = _peut_gerer(cours, utilisateur)
    if not professeur and not _est_inscrit(session, cours_id, utilisateur.id):
        return RedirectResponse("/classe", status_code=303)
    if professeur:
        etudiants = session.exec(select(Utilisateur).join(
            InscriptionCours, InscriptionCours.utilisateur_id == Utilisateur.id
        ).where(InscriptionCours.cours_id == cours_id).order_by(Utilisateur.nom)).all()
    else:
        etudiants = [utilisateur]
    carnet = _construire_carnet(session, cours, etudiants, professeur)
    return templates.TemplateResponse(request, "carnet_notes.html", {
        "utilisateur": utilisateur, "cours": cours, "peut_gerer": professeur, **carnet,
    })

@router.get("/classe/{cours_id}/rapport-academique")
def page_rapport_academique(cours_id: int, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)
    etudiants = session.exec(select(Utilisateur).join(
        InscriptionCours, InscriptionCours.utilisateur_id == Utilisateur.id
    ).where(InscriptionCours.cours_id == cours_id).order_by(Utilisateur.nom)).all()
    carnet = _construire_carnet(session, cours, etudiants, True)
    seances = session.exec(select(Seance).where(Seance.cours_id == cours_id)).all()
    ids_seances = [s.id for s in seances]
    pointages = session.exec(select(PointagePresence).where(PointagePresence.seance_id.in_(ids_seances))).all() if ids_seances else []
    stats_presence = {s.value: 0 for s in StatutPointage}
    for p in pointages:
        stats_presence[p.statut.value] += 1
    stats_devoirs = []
    for d in carnet["devoirs"]:
        r = [item["rendu"] for line in carnet["lignes"] for item in line["notes"] if item["devoir"].id == d.id and item["rendu"]]
        notes = [x.note / d.bareme * 20 for x in r if x.note is not None]
        stats_devoirs.append({"devoir": d, "nb_rendus": len(r), "nb_corriges": len(notes), "moyenne": round(sum(notes)/len(notes), 2) if notes else None})
    return templates.TemplateResponse(request, "rapport_academique.html", {
        "utilisateur": utilisateur, "cours": cours, "carnet": carnet,
        "stats_presence": stats_presence, "stats_devoirs": stats_devoirs, "nb_seances": len(seances),
    })

@router.get("/classe/seances/{seance_id}/registre-presences")
def page_registre_presences(seance_id: int, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    seance = session.get(Seance, seance_id)
    cours = session.get(Cours, seance.cours_id) if seance else None
    if not seance or not cours or not _peut_gerer(cours, utilisateur):
        return RedirectResponse("/classe", status_code=303)
    etudiants = session.exec(select(Utilisateur).join(
        InscriptionCours, InscriptionCours.utilisateur_id == Utilisateur.id
    ).where(InscriptionCours.cours_id == cours.id).order_by(Utilisateur.nom)).all()
    pointages = session.exec(select(PointagePresence).where(PointagePresence.seance_id == seance_id)).all()
    par_etudiant = {p.utilisateur_id: p for p in pointages}
    connexions = session.exec(select(PresenceSeance).where(PresenceSeance.seance_id == seance_id)).all()
    durees = {}
    for p in connexions:
        durees[p.utilisateur_id] = durees.get(p.utilisateur_id, 0) + max(0, p.duree_estimee_secondes)
    lignes = [{"utilisateur": e, "pointage": par_etudiant.get(e.id), "duree_secondes": durees.get(e.id, 0)} for e in etudiants]
    return templates.TemplateResponse(request, "registre_presences.html", {
        "utilisateur": utilisateur, "cours": cours, "seance": seance, "lignes": lignes,
    })

@router.post("/classe/seances/{seance_id}/registre-presences/pointage")
def enregistrer_pointage(
    seance_id: int, request: Request, utilisateur_id: int = Form(...),
    statut: str = Form(...), justificatif: Optional[str] = Form(None),
    session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf),
):
    auteur = utilisateur_courant(request, session)
    seance = session.get(Seance, seance_id)
    cours = session.get(Cours, seance.cours_id) if seance else None
    if not seance or not cours or not _peut_gerer(cours, auteur):
        return RedirectResponse("/classe", status_code=303)
    if not _est_inscrit(session, cours.id, utilisateur_id):
        return RedirectResponse(f"/classe/seances/{seance_id}/registre-presences?erreur=etudiant", status_code=303)
    try:
        statut_valide = normaliser_statut_pointage(statut)
    except ValueError:
        return RedirectResponse(f"/classe/seances/{seance_id}/registre-presences?erreur=statut", status_code=303)
    pointage = session.exec(select(PointagePresence).where(
        PointagePresence.seance_id == seance_id,
        PointagePresence.utilisateur_id == utilisateur_id,
    )).first()
    ancien = pointage.statut if pointage else None
    if not pointage:
        pointage = PointagePresence(seance_id=seance_id, utilisateur_id=utilisateur_id)
    pointage.statut = statut_valide
    pointage.justificatif = (justificatif or "").strip()[:1200] or None
    pointage.saisi_par_id = auteur.id
    pointage.date_maj = datetime.utcnow()
    session.add(pointage)
    if statut_valide in {StatutPointage.ABSENT, StatutPointage.RETARD, StatutPointage.EXCUSE} and ancien != statut_valide:
        session.add(Notification(
            destinataire_id=utilisateur_id, type_notification=TypeNotification.STATUT_PRESENCE,
            contenu=f"Ton statut de présence à la séance « {seance.titre} » ({cours.nom}) a été mis à jour : {statut_valide.value}.",
            acteur_id=auteur.id, url_destination="/mes-presences",
        ))
    session.commit()
    return RedirectResponse(f"/classe/seances/{seance_id}/registre-presences?enregistre=1", status_code=303)
