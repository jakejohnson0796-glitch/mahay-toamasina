"""
Classe virtuelle : cours, inscriptions, séances, présence et salle LiveKit.
Le professeur organise les cours et les séances ; les étudiants inscrits
rejoignent une salle audio/vidéo sécurisée par un jeton limité à la séance.
Le tableau blanc collaboratif reste un canal distinct, avec ses propres
contrôles d'accès et une synchronisation persistée.
"""
import secrets
import json
import unicodedata
import csv
import io
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, Response
from sqlmodel import Session, select, or_

from ..database import get_session, engine
from ..client_ip import adresse_ip_client
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import (Cours, InscriptionCours, Seance, StatutSeance, PresenceSeance, Utilisateur, RoleUtilisateur, EtablissementPartenaire, EvenementTableauBlanc, TypeEvenementTableau, AutorisationEcritureTableau, Devoir, RenduDevoir, ProgressionNotion, FicheRevisionCours, StatutFicheRevisionCours, Notification, TypeNotification)
from ..auth import utilisateur_courant, session_utilisateur_valide
from ..livekit_tokens import generer_jeton_salle, livekit_configure, LiveKitNonConfigure, muter_micro_participant, expulser_participant
from ..config import parametres
from ..ws_manager import gestionnaire
from ..storage import sauvegarder_fichier, obtenir_url_telechargement, stockage_distant_actif, FichierInvalide, ouvrir_fichier_local, supprimer_fichier
from ..text_extraction import extraire_texte
from .. import classe_correction
from ..rate_limit import limite_depassee
from .. import gamification
from ..institution_access import (
    ROLE_RESPONSABLE, ROLES_PEDAGOGIQUES,
    est_inscrit_cours, institution_pour_cours, institutions_avec_role, lister_inscriptions_actives,
    peut_gerer_cours, peut_rejoindre_cours,
)
from .. import quiz as quiz_module
from .. import ai_queue, course_revision

router = APIRouter()


def _est_professeur(utilisateur: Optional[Utilisateur], session: Session) -> bool:
    if not utilisateur:
        return False
    if utilisateur.role in (RoleUtilisateur.PROFESSEUR, RoleUtilisateur.ADMIN):
        return True
    return bool(institutions_avec_role(session, utilisateur.id, ROLES_PEDAGOGIQUES))


def _peut_gerer_cours(
    cours: Cours, utilisateur: Optional[Utilisateur], session: Optional[Session] = None
) -> bool:
    """Vérifie le tenant ; sans session, conserve uniquement le cas historique sûr.

    Les routes passent toujours la session. Le mode sans session existe pour la
    compatibilité des anciens appels internes et échoue fermé pour tout cours
    institutionnel.
    """
    if session is not None:
        return peut_gerer_cours(session, cours, utilisateur)
    if not utilisateur:
        return False
    role_global = getattr(utilisateur.role, "value", utilisateur.role)
    if role_global == "admin":
        return True
    if getattr(cours, "affectation_institutionnelle_requise", False):
        return False
    if getattr(cours, "institution_id", None) is not None:
        return False
    return utilisateur.id == cours.professeur_id


def _est_inscrit(session: Session, cours_id: int, utilisateur_id: int) -> bool:
    """Une inscription seule ne suffit pas pour les cours institutionnels."""
    return est_inscrit_cours(session, cours_id, utilisateur_id)


def _generer_nom_salle(cours_id: int) -> str:
    # Prefixe lisible (utile en debug/logs LiveKit) + suffixe aleatoire
    # non devinable (defense en profondeur : meme si l'autorisation
    # d'acces est de toute facon revalidee par le jeton LiveKit signe
    # cote serveur, un nom de salle non predictible evite les tentatives
    # de connexion directe au hasard).
    return f"mahay-cours{cours_id}-{secrets.token_hex(6)}"





def _generer_code_invitation(session: Session) -> str:
    """Code partageable, facile à dicter, unique et non séquentiel."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(12):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        existe = session.exec(
            select(Cours).where(Cours.code_invitation == code)
        ).first()
        if not existe:
            return code
    raise RuntimeError("Impossible de générer un code de cours unique.")


def _normaliser_criteres_devoir(texte: Optional[str], bareme: float) -> list[dict]:
    """Format lisible : une ligne « critère | points maximum »."""
    criteres = []
    total = 0.0
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        if "|" not in ligne:
            raise ValueError("Chaque critère doit respecter le format « Nom | points ».")
        nom, points_bruts = ligne.rsplit("|", 1)
        nom = " ".join(nom.split())[:100]
        try:
            points = float(points_bruts.strip().replace(",", "."))
        except ValueError as erreur:
            raise ValueError(f"Points invalides pour le critère « {nom} ».") from erreur
        if not nom or not math.isfinite(points) or points <= 0 or points > bareme:
            raise ValueError(f"Le critère « {nom or 'sans nom'} » doit avoir un maximum positif inférieur au barème.")
        if any(item["nom"].casefold() == nom.casefold() for item in criteres):
            raise ValueError(f"Le critère « {nom} » est indiqué plusieurs fois.")
        criteres.append({"nom": nom, "points": round(points, 2)})
        total += points
        if len(criteres) > 12:
            raise ValueError("Un devoir ne peut pas contenir plus de 12 critères.")
    if total > bareme + 0.001:
        raise ValueError("La somme des critères dépasse le barème du devoir.")
    return criteres


def _lire_criteres_devoir(devoir: Devoir) -> list[dict]:
    try:
        donnees = json.loads(devoir.criteres_json or "[]")
        return donnees if isinstance(donnees, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _details_correction_rendu(rendu: RenduDevoir) -> str:
    try:
        details = json.loads(rendu.details_correction_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    return str(details.get("commentaire_criteres") or "") if isinstance(details, dict) else ""


def _valeur_csv_securisee(valeur) -> str:
    """Neutralise les cellules susceptibles d'être interprétées comme formule Excel."""
    texte = str(valeur or "")
    debut = texte.lstrip()
    if debut.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + texte
    return texte


def _peut_ecrire_tableau(session: Session, seance_id: int, cours: Cours, utilisateur: Utilisateur) -> bool:
    """Le prof proprietaire du cours (ou un admin) peut toujours ecrire.
    Un etudiant ne peut ecrire QUE s'il a ete explicitement autorise pour
    CETTE seance precise (voir AutorisationEcritureTableau) — verifie a
    chaque evenement recu sur le WebSocket, jamais fait confiance a
    l'etat affiche cote client (qui pourrait etre bidouille)."""
    if _peut_gerer_cours(cours, utilisateur, session):
        return True
    return session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur.id,
        )
    ).first() is not None


def _reconstituer_etat_tableau(session: Session, seance_id: int) -> list:
    """Rejoue le journal d'evenements dans l'ordre pour reconstituer
    l'etat VISIBLE actuel du tableau (necessaire pour qu'un etudiant qui
    rejoint en retard voie le tableau tel qu'il est, pas juste les
    evenements a partir de sa connexion). Voir EvenementTableauBlanc
    pour l'explication complete de cette approche append-only."""
    evenements = session.exec(
        select(EvenementTableauBlanc)
        .where(EvenementTableauBlanc.seance_id == seance_id)
        .order_by(EvenementTableauBlanc.date_creation)
    ).all()

    etat: dict = {}
    for e in evenements:
        if e.type_evenement == TypeEvenementTableau.EFFACER_TOUT:
            etat = {}
        elif e.type_evenement == TypeEvenementTableau.SUPPRESSION:
            etat.pop(e.element_id, None)
        else:
            etat[e.element_id] = {
                "type": e.type_evenement.value,
                "element_id": e.element_id,
                "utilisateur_id": e.utilisateur_id,
                "donnees": json.loads(e.donnees),
            }
    return list(etat.values())


@router.get("/classe")
def liste_cours(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if utilisateur.role == RoleUtilisateur.ADMIN:
        cours_visibles = session.exec(select(Cours).order_by(Cours.date_creation.desc())).all()
    else:
        # Un compte peut être professeur dans un établissement et étudiant
        # dans un autre : on réunit les deux périmètres sans élargir les droits.
        ids_responsable = institutions_avec_role(
            session, utilisateur.id, (ROLE_RESPONSABLE,)
        )
        conditions_gestion = [Cours.professeur_id == utilisateur.id]
        if ids_responsable:
            conditions_gestion.append(Cours.institution_id.in_(ids_responsable))
        candidats_gestion = session.exec(
            select(Cours).where(or_(*conditions_gestion))
        ).all()
        cours_geres = [
            cours for cours in candidats_gestion
            if _peut_gerer_cours(cours, utilisateur, session)
        ]
        candidats_inscription = session.exec(
            select(Cours)
            .where(InscriptionCours.cours_id == Cours.id)
            .where(InscriptionCours.utilisateur_id == utilisateur.id)
        ).all()
        cours_etudies = [
            cours for cours in candidats_inscription
            if _est_inscrit(session, cours.id, utilisateur.id)
        ]
        cours_par_id = {cours.id: cours for cours in cours_geres}
        cours_par_id.update({cours.id: cours for cours in cours_etudies})
        cours_visibles = sorted(
            cours_par_id.values(),
            key=lambda cours: cours.date_creation,
            reverse=True,
        )

    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "classe",
        source_type="visite_classe",
        source_key=datetime.utcnow().date().isoformat(),
    )
    session.commit()

    return templates.TemplateResponse(
        request,
        "classe_liste.html",
        {
            "utilisateur": utilisateur,
            "cours_visibles": cours_visibles,
            "est_professeur": _est_professeur(utilisateur, session),
            "peut_rejoindre_cours": (
                utilisateur.role == RoleUtilisateur.ETUDIANT
                or bool(institutions_avec_role(session, utilisateur.id, ("etudiant",)))
            ),
            "institutions_creation": (
                session.exec(
                    select(EtablissementPartenaire)
                    .where(EtablissementPartenaire.id.in_(
                        institutions_avec_role(session, utilisateur.id, ROLES_PEDAGOGIQUES)
                    ))
                    .where(EtablissementPartenaire.est_actif == True)  # noqa: E712
                    .order_by(EtablissementPartenaire.nom)
                ).all()
                if institutions_avec_role(session, utilisateur.id, ROLES_PEDAGOGIQUES)
                else []
            ),
            "est_responsable_institution": bool(
                institutions_avec_role(session, utilisateur.id, (ROLE_RESPONSABLE,))
            ),
        },
    )


@router.post("/classe/creer")
def creer_cours(
    request: Request,
    nom: str = Form(...),
    matiere: str = Form(...),
    niveau: str = Form(...),
    institution_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    objectifs: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not _est_professeur(utilisateur, session):
        return RedirectResponse("/classe", status_code=303)
    try:
        institution_cible = institution_pour_cours(session, utilisateur, institution_id)
    except ValueError:
        return RedirectResponse("/classe?erreur=institution_invalide#nouveau-cours", status_code=303)

    nom = " ".join((nom or "").split())
    matiere = " ".join((matiere or "").split())
    niveau = " ".join((niveau or "").split())
    if not nom or len(nom) > 120 or not matiere or len(matiere) > 100 or not niveau or len(niveau) > 80:
        return RedirectResponse("/classe?erreur=champs_cours_invalides#nouveau-cours", status_code=303)

    cours = Cours(
        nom=nom,
        matiere=matiere,
        niveau=niveau,
        description=(description or "").strip()[:3000] or None,
        objectifs=(objectifs or "").strip()[:3000] or None,
        professeur_id=utilisateur.id,
        institution_id=institution_cible,
        code_invitation=_generer_code_invitation(session),
    )
    session.add(cours)
    session.commit()
    session.refresh(cours)
    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.post("/classe/{cours_id}/modifier")
def modifier_cours(
    request: Request,
    cours_id: int,
    nom: str = Form(...),
    matiere: str = Form(...),
    niveau: str = Form(...),
    description: Optional[str] = Form(None),
    objectifs: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)

    nom = " ".join((nom or "").split())
    matiere = " ".join((matiere or "").split())
    niveau = " ".join((niveau or "").split())
    if not nom or len(nom) > 120 or not matiere or len(matiere) > 100 or not niveau or len(niveau) > 80:
        return RedirectResponse(f"/classe/{cours_id}?erreur=champs_cours_invalides#parametres-cours", status_code=303)

    cours.nom = nom
    cours.matiere = matiere
    cours.niveau = niveau
    cours.description = (description or "").strip()[:3000] or None
    cours.objectifs = (objectifs or "").strip()[:3000] or None
    session.add(cours)
    session.commit()
    return RedirectResponse(f"/classe/{cours_id}?cours=modifie#parametres-cours", status_code=303)


@router.post("/classe/{cours_id}/code-invitation/renouveler")
def renouveler_code_invitation(
    request: Request,
    cours_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if (
        not cours
        or cours.affectation_institutionnelle_requise
        or not _peut_gerer_cours(cours, utilisateur, session)
    ):
        return RedirectResponse("/classe", status_code=303)
    cours.code_invitation = _generer_code_invitation(session)
    session.add(cours)
    session.commit()
    return RedirectResponse(f"/classe/{cours_id}?code=renouvele#invitation-cours", status_code=303)


@router.post("/classe/rejoindre")
def rejoindre_cours_par_code(
    request: Request,
    code: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    host = adresse_ip_client(request)
    if limite_depassee(f"join-course:user:{utilisateur.id}", 10, 3600) or limite_depassee(f"join-course:ip:{host}", 30, 3600):
        return RedirectResponse("/classe?erreur=trop_de_tentatives", status_code=303)

    code_normalise = "".join((code or "").upper().split())
    if not code_normalise or len(code_normalise) > 12:
        return RedirectResponse("/classe?erreur=code_invalide#rejoindre-cours", status_code=303)
    cours = session.exec(select(Cours).where(Cours.code_invitation == code_normalise)).first()
    if not cours:
        return RedirectResponse("/classe?erreur=code_invalide#rejoindre-cours", status_code=303)
    if not peut_rejoindre_cours(session, cours, utilisateur):
        if cours.institution_id is None and utilisateur.role != RoleUtilisateur.ETUDIANT:
            return RedirectResponse("/classe?erreur=inscription_reservee", status_code=303)
        return RedirectResponse("/classe?erreur=etablissement_incompatible#rejoindre-cours", status_code=303)
    if not _est_inscrit(session, cours.id, utilisateur.id):
        session.add(InscriptionCours(cours_id=cours.id, utilisateur_id=utilisateur.id))
        session.commit()
        ai_queue.planifier_fiches_revision_cours(cours.id, utilisateur_id=utilisateur.id)
    return RedirectResponse(f"/classe/{cours.id}?inscription=confirmee", status_code=303)


@router.get("/classe/{cours_id}")
def detail_cours(request: Request, cours_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    inscrit = _est_inscrit(session, cours_id, utilisateur.id)

    if not peut_gerer and not inscrit:
        return RedirectResponse("/classe", status_code=303)

    # Les fiches privées manquantes sont planifiées après une clôture de
    # lecture, jamais générées dans la requête HTTP. Cela rattrape aussi les
    # séances déjà terminées avant l'arrivée d'un nouvel étudiant.
    if not peut_gerer:
        session.commit()
        fiches_existantes = session.exec(
            select(FicheRevisionCours).where(
                FicheRevisionCours.cours_id == cours_id,
                FicheRevisionCours.utilisateur_id == utilisateur.id,
            )
        ).all()
        sessions_avec_fiche = {fiche.seance_id for fiche in fiches_existantes}
        sessions_terminees = session.exec(
            select(Seance).where(
                Seance.cours_id == cours_id,
                Seance.statut == StatutSeance.TERMINEE,
            )
        ).all()
        for seance_terminee in sessions_terminees:
            if seance_terminee.id not in sessions_avec_fiche:
                ai_queue.planifier_fiche_revision_cours(
                    seance_terminee.id,
                    utilisateur.id,
                )
        session.expire_all()

    if (
        peut_gerer
        and not cours.affectation_institutionnelle_requise
        and not cours.code_invitation
    ):
        cours.code_invitation = _generer_code_invitation(session)
        session.add(cours)
        session.commit()
        session.refresh(cours)

    professeur = session.get(Utilisateur, cours.professeur_id)
    seances = session.exec(
        select(Seance).where(Seance.cours_id == cours_id).order_by(Seance.date_creation)
    ).all()

    fiches_revision_par_seance = {}
    if not peut_gerer:
        fiches_revision = session.exec(
            select(FicheRevisionCours).where(
                FicheRevisionCours.cours_id == cours_id,
                FicheRevisionCours.utilisateur_id == utilisateur.id,
            )
        ).all()
        fiches_revision_par_seance = {
            fiche.seance_id: fiche for fiche in fiches_revision
        }
    nb_etudiants = len(lister_inscriptions_actives(session, cours_id))
    requete_devoirs = select(Devoir).where(Devoir.cours_id == cours_id)
    if not peut_gerer:
        requete_devoirs = requete_devoirs.where(Devoir.archive == False)  # noqa: E712
    devoirs = session.exec(
        requete_devoirs.order_by(Devoir.date_creation.desc())
    ).all()

    mes_rendus_ids = set()
    if not peut_gerer and devoirs:
        mes_rendus = session.exec(
            select(RenduDevoir.devoir_id).where(
                RenduDevoir.utilisateur_id == utilisateur.id,
                RenduDevoir.devoir_id.in_([d.id for d in devoirs]),
            )
        ).all()
        mes_rendus_ids = set(mes_rendus)

    return templates.TemplateResponse(
        request,
        "classe_detail.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "professeur": professeur,
            "seances": seances,
            "nb_etudiants": nb_etudiants,
            "peut_gerer": peut_gerer,
            "devoirs": devoirs,
            "mes_rendus_ids": mes_rendus_ids,
            "fiches_revision_par_seance": fiches_revision_par_seance,
        },
    )



# Le radar reste volontairement collectif : aucun nom, score individuel ni
# export de données personnelles n'est exposé. Une notion n'apparaît qu'avec
# au moins trois étudiants disposant de données mesurées.
SEUIL_CONFIDENTIALITE_RADAR = 3


def _cle_academique(valeur: Optional[str]) -> str:
    texte = unicodedata.normalize("NFKD", valeur or "").casefold()
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere))
    return " ".join("".join(c if c.isalnum() else " " for c in texte).split())


def _cle_niveau(valeur: Optional[str]) -> str:
    """Normalise les libellés usuels du niveau pour éviter de croiser L1 et L2."""
    cle = _cle_academique(valeur)
    alias = {
        "licence 1": "l1",
        "premiere annee": "l1",
        "1ere annee": "l1",
        "licence 2": "l2",
        "deuxieme annee": "l2",
        "2eme annee": "l2",
        "licence 3": "l3",
        "troisieme annee": "l3",
        "3eme annee": "l3",
        "master 1": "m1",
        "master premiere annee": "m1",
        "master 2": "m2",
        "master deuxieme annee": "m2",
    }
    return alias.get(cle, cle)


def construire_radar_pedagogique(
    progressions: list[ProgressionNotion],
    effectif_inscrit: int,
) -> dict:
    """Produit un aperçu collectif, sans identifier les étudiants."""
    groupes: dict[str, dict] = {}
    etudiants_observes: set[int] = set()

    for progression in progressions:
        utilisateur_id = getattr(progression, "utilisateur_id", None)
        notion = (getattr(progression, "notion", "") or "").strip()
        cle = _cle_academique(notion)
        if utilisateur_id is None or not cle or not notion:
            continue
        diagnostic = quiz_module.diagnostiquer_maitrise(progression)
        etudiants_observes.add(int(utilisateur_id))
        groupe = groupes.setdefault(
            cle,
            {"notion": notion, "scores_par_etudiant": {}, "maitrises_prouvees": 0},
        )
        # Garde une seule observation par étudiant pour la même notion.
        precedente = groupe["scores_par_etudiant"].get(int(utilisateur_id))
        score = int(diagnostic.get("score", 0))
        if precedente is None or score < precedente:
            groupe["scores_par_etudiant"][int(utilisateur_id)] = score
        if diagnostic.get("maitrise_confirmee"):
            groupe["maitrises_prouvees"] += 1

    notions = []
    for groupe in groupes.values():
        scores = list(groupe["scores_par_etudiant"].values())
        observes = len(scores)
        if observes < SEUIL_CONFIDENTIALITE_RADAR:
            continue
        score_moyen = round(sum(scores) / observes)
        nb_fragiles = sum(1 for score in scores if score < 65)
        part_fragile = round(nb_fragiles * 100 / observes)
        if score_moyen < 50 or part_fragile >= 70:
            priorite = "Élevée"
            niveau_priorite = 0
        elif score_moyen < 65 or part_fragile >= 40:
            priorite = "À reprendre"
            niveau_priorite = 1
        elif score_moyen < 80:
            priorite = "À consolider"
            niveau_priorite = 2
        else:
            priorite = "À approfondir"
            niveau_priorite = 3

        if score_moyen < 50:
            action = (
                "Reprendre le prérequis avec un exemple guidé, faire verbaliser chaque étape, "
                "puis proposer trois questions faciles."
            )
        elif score_moyen < 65:
            action = (
                "Prévoir une micro-leçon de 5 à 10 minutes, un exemple corrigé et un quiz ciblé "
                "avant de passer au chapitre suivant."
            )
        elif score_moyen < 80:
            action = (
                "Faire résoudre un exercice de transfert et demander aux étudiants d'expliquer "
                "la méthode en binômes."
            )
        else:
            action = (
                "Proposer une application plus complexe et vérifier la maîtrise avec de nouvelles "
                "questions sur une autre séance."
            )

        notions.append({
            "notion": groupe["notion"],
            "effectif_observe": observes,
            "score_moyen": score_moyen,
            "nb_fragiles": nb_fragiles,
            "part_fragile": part_fragile,
            "maitrises_prouvees": min(observes, groupe["maitrises_prouvees"]),
            "priorite": priorite,
            "niveau_priorite": niveau_priorite,
            "action": action,
        })

    notions.sort(
        key=lambda item: (
            item["niveau_priorite"],
            -item["part_fragile"],
            item["score_moyen"],
            _cle_academique(item["notion"]),
        )
    )
    nb_eleves = max(0, int(effectif_inscrit or 0))
    nb_eleves_observes = len(etudiants_observes)
    return {
        "effectif_inscrit": nb_eleves,
        "effectif_observe": nb_eleves_observes,
        "couverture_pct": round(nb_eleves_observes * 100 / nb_eleves) if nb_eleves else 0,
        "nb_notions_mesurees": len(groupes),
        "nb_notions_affichables": len(notions),
        "notions": notions[:12],
        "seuil_confidentialite": SEUIL_CONFIDENTIALITE_RADAR,
    }


def construire_plan_reprise(cours: Cours, radar: dict) -> str:
    """Prépare un plan de cours éditable, sans prétendre qu'il a été généré par IA."""
    lignes = [
        f"PLAN DE REPRISE — {cours.nom}",
        f"Matière : {cours.matiere} · Niveau : {cours.niveau}",
        "",
        "Objectif : reprendre les notions pour lesquelles les résultats collectifs sont les plus fragiles.",
    ]
    notions = radar.get("notions", [])
    if notions:
        lignes.extend(["", "Ordre proposé pour la prochaine séance :"])
        for index, notion in enumerate(notions[:3], start=1):
            lignes.append(
                f"{index}. {notion['notion']} — score collectif {notion['score_moyen']} %, "
                f"{notion['part_fragile']} % des étudiants observés en difficulté."
            )
            lignes.append(f"   Action : {notion['action']}")
    else:
        lignes.extend([
            "",
            "Les données disponibles ne permettent pas encore d'afficher une notion précise.",
            "Faire un mini-diagnostic commun de 5 questions, vérifier les prérequis, puis relancer "
            "le radar après plusieurs étudiants actifs.",
        ])
    lignes.extend([
        "",
        "Vérification de sortie : proposer 3 à 5 questions nouvelles, demander une explication "
        "du raisonnement, puis refaire le point lors d'une autre séance.",
        "Note : cet aperçu est un indicateur d'aide à l'enseignement, pas une note ni un jugement "
        "sur un étudiant. Il ne remplace pas l'observation du professeur.",
    ])
    return "\n".join(lignes)


@router.get("/classe/{cours_id}/radar")
def radar_pedagogique_cours(
    request: Request,
    cours_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)
    if not _peut_gerer_cours(cours, utilisateur, session):
        # Le radar est une vue réservée au professeur propriétaire et aux admins.
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    inscriptions = lister_inscriptions_actives(session, cours_id)
    ids_etudiants = sorted({int(etudiant.id) for _, etudiant in inscriptions if etudiant.id is not None})
    progressions = []
    cle_matiere = _cle_academique(cours.matiere)
    if ids_etudiants and cle_matiere:
        lignes = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id.in_(ids_etudiants)
            )
        ).all()
        progressions_matiere = [
            ligne for ligne in lignes
            if _cle_academique(ligne.matiere) == cle_matiere
        ]
        cle_niveau = _cle_niveau(cours.niveau)
        # Ne jamais mélanger les cohortes de L1, L2, etc. Les lignes sans
        # niveau connu restent hors du radar, car leur attribution serait spéculative.
        progressions = [
            ligne for ligne in progressions_matiere
            if _cle_niveau(ligne.niveau) == cle_niveau
        ]

    radar = construire_radar_pedagogique(progressions, len(ids_etudiants))
    plan_reprise = construire_plan_reprise(cours, radar)
    return templates.TemplateResponse(
        request,
        "radar_pedagogique_classe.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "radar": radar,
            "plan_reprise": plan_reprise,
        },
    )


@router.get("/classe/{cours_id}/etudiants")
def liste_etudiants_cours(request: Request, cours_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    lignes = lister_inscriptions_actives(session, cours_id)
    inscriptions = [{"inscription": i, "utilisateur": u} for i, u in lignes]

    return templates.TemplateResponse(
        request,
        "classe_etudiants.html",
        {"utilisateur": utilisateur, "cours": cours, "inscriptions": inscriptions},
    )


@router.post("/classe/{cours_id}/etudiants/ajouter")
def ajouter_etudiant(
    request: Request,
    cours_id: int,
    telephone: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    cible = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone.strip())).first()
    if not cible:
        return RedirectResponse(f"/classe/{cours_id}/etudiants?erreur=utilisateur_introuvable", status_code=303)

    if not peut_rejoindre_cours(session, cours, cible):
        return RedirectResponse(f"/classe/{cours_id}/etudiants?erreur=etablissement_incompatible", status_code=303)
    if not _est_inscrit(session, cours_id, cible.id):
        session.add(InscriptionCours(cours_id=cours_id, utilisateur_id=cible.id))
        session.commit()
        ai_queue.planifier_fiches_revision_cours(
            cours_id,
            utilisateur_id=cible.id,
        )

    return RedirectResponse(f"/classe/{cours_id}/etudiants?ajoute=1", status_code=303)


@router.post("/classe/{cours_id}/etudiants/{utilisateur_id}/retirer")
def retirer_etudiant(request: Request, cours_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    inscription = session.exec(
        select(InscriptionCours).where(
            InscriptionCours.cours_id == cours_id,
            InscriptionCours.utilisateur_id == utilisateur_id,
        )
    ).first()
    if inscription:
        session.delete(inscription)
        session.commit()

    return RedirectResponse(f"/classe/{cours_id}/etudiants", status_code=303)


@router.post("/classe/{cours_id}/seances/creer")
def creer_seance(
    request: Request,
    cours_id: int,
    titre: str = Form(...),
    description: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    seance = Seance(cours_id=cours_id, titre=titre, description=description or None, nom_salle_livekit=_generer_nom_salle(cours_id))
    session.add(seance)
    session.commit()

    return RedirectResponse(f"/classe/{cours_id}", status_code=303)


@router.post("/classe/seances/{seance_id}/demarrer")
def demarrer_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)

    if seance.statut == StatutSeance.PLANIFIEE:
        seance.statut = StatutSeance.EN_COURS
        seance.date_debut_reelle = datetime.utcnow()
        session.add(seance)
        session.commit()

    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.post("/classe/seances/{seance_id}/terminer")
def terminer_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)

    if seance.statut == StatutSeance.EN_COURS:
        seance.statut = StatutSeance.TERMINEE
        seance.date_fin_reelle = datetime.utcnow()
        session.add(seance)

        # Cloture toutes les presences encore ouvertes (participants qui
        # n'ont jamais explicitement "quitte" avant la fin de seance).
        maintenant = datetime.utcnow()
        presences_ouvertes = session.exec(
            select(PresenceSeance).where(PresenceSeance.seance_id == seance_id, PresenceSeance.heure_sortie == None)  # noqa: E711
        ).all()
        for p in presences_ouvertes:
            delta = (maintenant - p.heure_entree).total_seconds()
            p.duree_estimee_secondes += int(delta)
            p.heure_sortie = maintenant
            session.add(p)

        session.commit()
        ai_queue.planifier_fiches_revision_cours(
            cours.id,
            seance_id=seance_id,
        )

    return RedirectResponse(f"/classe/{cours.id}", status_code=303)


@router.get("/classe/revisions/{fiche_id}")
def consulter_fiche_revision_cours(
    request: Request,
    fiche_id: int,
    session: Session = Depends(get_session),
):
    """Lit la fiche dans le navigateur ; les fiches de progression restent privées."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    fiche = session.get(FicheRevisionCours, fiche_id)
    if (
        not fiche
        or fiche.utilisateur_id != utilisateur.id
        or not _est_inscrit(session, fiche.cours_id, utilisateur.id)
    ):
        return RedirectResponse("/classe", status_code=303)

    if (
        fiche.statut == StatutFicheRevisionCours.TERMINEE
        and fiche.version_generation != course_revision.VERSION_GENERATION
    ):
        # Une seule fiche est régénérée quand l'étudiant l'ouvre ; les autres
        # fiches historiques ne sont pas toutes remises en file à la fois.
        ai_queue.planifier_fiche_revision_cours(fiche.seance_id, utilisateur.id)
        session.expire_all()
        fiche = session.get(FicheRevisionCours, fiche_id)
        if not fiche:
            return RedirectResponse("/classe", status_code=303)

    if fiche.statut != StatutFicheRevisionCours.TERMINEE or not fiche.contenu_json:
        return RedirectResponse(
            f"/classe/{fiche.cours_id}?fiche=en_cours#seances",
            status_code=303,
        )

    cours = session.get(Cours, fiche.cours_id)
    seance = session.get(Seance, fiche.seance_id)
    if not cours or not seance:
        return RedirectResponse("/classe", status_code=303)

    try:
        contenu = course_revision.normaliser_fiche_revision(
            json.loads(fiche.contenu_json)
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return RedirectResponse(
            f"/classe/{cours.id}?fiche=indisponible#seances",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "classe_revision.html",
        {
            "utilisateur": utilisateur,
            "cours": cours,
            "seance": seance,
            "fiche_revision": fiche,
            "fiche_contenu": contenu,
        },
    )


@router.get("/classe/revisions/{fiche_id}/telecharger/{format_fichier}")
def telecharger_fiche_revision_cours(
    request: Request,
    fiche_id: int,
    format_fichier: str,
    session: Session = Depends(get_session),
):
    """Télécharge la fiche personnelle de l'étudiant propriétaire."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if format_fichier not in {"pdf", "docx"}:
        return RedirectResponse("/classe", status_code=303)

    fiche = session.get(FicheRevisionCours, fiche_id)
    if (
        not fiche
        or fiche.utilisateur_id != utilisateur.id
        or not _est_inscrit(session, fiche.cours_id, utilisateur.id)
    ):
        # Réponse uniforme : ne révèle pas si une fiche privée existe.
        return RedirectResponse("/classe", status_code=303)

    if (
        fiche.statut == StatutFicheRevisionCours.TERMINEE
        and fiche.version_generation != course_revision.VERSION_GENERATION
    ):
        # Une seule fiche est régénérée quand l'étudiant l'ouvre ; les autres
        # fiches historiques ne sont pas toutes remises en file à la fois.
        ai_queue.planifier_fiche_revision_cours(fiche.seance_id, utilisateur.id)
        session.expire_all()
        fiche = session.get(FicheRevisionCours, fiche_id)
        if not fiche:
            return RedirectResponse("/classe", status_code=303)

    if fiche.statut != StatutFicheRevisionCours.TERMINEE or not fiche.contenu_json:
        return RedirectResponse(
            f"/classe/{fiche.cours_id}?fiche=en_cours#seances",
            status_code=303,
        )

    cours = session.get(Cours, fiche.cours_id)
    seance = session.get(Seance, fiche.seance_id)
    if not cours or not seance:
        return RedirectResponse("/classe", status_code=303)

    try:
        contenu = json.loads(fiche.contenu_json)
        contenu = course_revision.normaliser_fiche_revision(contenu)
    except (TypeError, ValueError, json.JSONDecodeError):
        return RedirectResponse(
            f"/classe/{cours.id}?fiche=indisponible#seances",
            status_code=303,
        )

    if format_fichier == "pdf":
        octets = course_revision.generer_pdf(
            contenu, cours, seance, utilisateur.nom
        )
        media_type = "application/pdf"
        extension = "pdf"
    else:
        octets = course_revision.generer_docx(
            contenu, cours, seance, utilisateur.nom
        )
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"

    nom_fichier = f"mitaridala-revision-cours-{cours.id}-seance-{seance.id}.{extension}"
    return Response(
        content=octets,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{nom_fichier}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/classe/revisions/{fiche_id}/relancer")
def relancer_fiche_revision_cours(
    request: Request,
    fiche_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Autorise uniquement l'étudiant concerné à relancer sa fiche en échec."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    fiche = session.get(FicheRevisionCours, fiche_id)
    if (
        not fiche
        or fiche.utilisateur_id != utilisateur.id
        or not _est_inscrit(session, fiche.cours_id, utilisateur.id)
    ):
        return RedirectResponse("/classe", status_code=303)

    if fiche.statut != StatutFicheRevisionCours.ECHOUEE:
        return RedirectResponse(f"/classe/{fiche.cours_id}#seances", status_code=303)

    ai_queue.planifier_fiche_revision_cours(
        fiche.seance_id,
        utilisateur.id,
        forcer=True,
    )
    return RedirectResponse(
        f"/classe/{fiche.cours_id}?fiche=relancee#seances",
        status_code=303,
    )


@router.post("/classe/seances/{seance_id}/rejoindre")
def rejoindre_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if seance.statut != StatutSeance.EN_COURS:
        return RedirectResponse(f"/classe/{cours.id}?erreur=seance_non_demarree", status_code=303)

    # Une seule présence ouverte par étudiant et séance. Les doubles clics
    # et renvois du formulaire ne doivent pas créer plusieurs entrées
    # simultanées ni gonfler la durée de présence.
    presence_ouverte = session.exec(
        select(PresenceSeance)
        .where(PresenceSeance.seance_id == seance_id)
        .where(PresenceSeance.utilisateur_id == utilisateur.id)
        .where(PresenceSeance.heure_sortie == None)  # noqa: E711
        .order_by(PresenceSeance.heure_entree.desc())
    ).first()
    if not presence_ouverte:
        session.add(PresenceSeance(seance_id=seance_id, utilisateur_id=utilisateur.id))
        session.commit()

    return RedirectResponse(f"/classe/seances/{seance_id}/salle", status_code=303)


@router.get("/classe/seances/{seance_id}/salle")
def salle_virtuelle(request: Request, seance_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if seance.statut != StatutSeance.EN_COURS:
        return RedirectResponse(f"/classe/{cours.id}?erreur=seance_non_demarree", status_code=303)

    if not livekit_configure():
        return templates.TemplateResponse(
            request,
            "classe_salle.html",
            {
                "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
                "erreur_livekit": "La classe virtuelle audio/video n'est pas encore configuree sur ce serveur (variables LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET manquantes).",
                "jeton_livekit": None, "url_livekit": None,
            },
        )

    try:
        jeton_livekit = generer_jeton_salle(
            nom_salle=seance.nom_salle_livekit,
            utilisateur_id=utilisateur.id,
            nom_affiche=utilisateur.nom,
            peut_publier=True,
            peut_partager_ecran=peut_gerer,
        )
    except LiveKitNonConfigure as erreur:
        return templates.TemplateResponse(
            request,
            "classe_salle.html",
            {
                "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
                "erreur_livekit": str(erreur), "jeton_livekit": None, "url_livekit": None,
            },
        )

    return templates.TemplateResponse(
        request,
        "classe_salle.html",
        {
            "utilisateur": utilisateur, "cours": cours, "seance": seance, "peut_gerer": peut_gerer,
            "erreur_livekit": None, "jeton_livekit": jeton_livekit, "url_livekit": parametres.livekit_url,
        },
    )


@router.post("/classe/seances/{seance_id}/quitter")
def quitter_seance(request: Request, seance_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)

    # Ferme toutes les éventuelles présences ouvertes : cela répare aussi
    # les doublons historiques créés avant l'idempotence de "Rejoindre".
    presences_ouvertes = session.exec(
        select(PresenceSeance)
        .where(PresenceSeance.seance_id == seance_id)
        .where(PresenceSeance.utilisateur_id == utilisateur.id)
        .where(PresenceSeance.heure_sortie == None)  # noqa: E711
        .order_by(PresenceSeance.heure_entree.desc())
    ).all()
    if presences_ouvertes:
        maintenant = datetime.utcnow()
        for index, presence in enumerate(presences_ouvertes):
            # Si d'anciens doublons existent, ne compter la durée que sur
            # l'entrée la plus récente pour éviter de doubler le temps.
            if index == 0:
                duree = (maintenant - presence.heure_entree).total_seconds()
                presence.duree_estimee_secondes += max(0, int(duree))
            presence.heure_sortie = maintenant
            session.add(presence)
        session.commit()

    return RedirectResponse(f"/classe/{seance.cours_id}", status_code=303)


def _seance_et_cours_geres(session: Session, seance_id: int, utilisateur: Optional[Utilisateur]):
    """Charge la seance + son cours et verifie que l'appelant peut gerer
    CE cours precis. Retourne (seance, cours) ou (None, message_erreur)
    -- factorise la meme suite de verifications deja dupliquee 6x dans ce
    fichier pour salle_virtuelle/tableau/etc., utilisee ici pour les 2
    nouvelles routes de moderation ci-dessous."""
    if not utilisateur:
        return None, ("Non connecte.", 401)
    seance = session.get(Seance, seance_id)
    if not seance:
        return None, ("Seance introuvable.", 404)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return None, ("Action reservee au professeur de ce cours.", 403)
    return (seance, cours), None


@router.post("/classe/seances/{seance_id}/salle/muter/{utilisateur_id}")
async def muter_participant_salle(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Coupe le micro d'un participant precis, a la demande du professeur
    (ou d'un admin) gerant ce cours. Repond en JSON et non par une
    redirection : appelee en fetch() depuis classe_salle.html PENDANT
    la seance -- une navigation de page couperait la Room LiveKit du
    professeur lui-meme (meme raison que le tableau blanc, voir la note
    a ce sujet dans classe_salle.html)."""
    utilisateur = utilisateur_courant(request, session)
    resultat, erreur = _seance_et_cours_geres(session, seance_id, utilisateur)
    if erreur:
        message, code = erreur
        return JSONResponse({"erreur": message}, status_code=code)
    seance, _cours = resultat

    if not livekit_configure():
        return JSONResponse({"erreur": "LiveKit n'est pas configure sur ce serveur."}, status_code=503)

    coupe = await muter_micro_participant(seance.nom_salle_livekit, str(utilisateur_id))
    return JSONResponse({"coupe": coupe})


@router.post("/classe/seances/{seance_id}/salle/expulser/{utilisateur_id}")
async def expulser_participant_salle(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Retire immediatement un participant de la salle audio/video.
    Repond en JSON, memes raisons que muter_participant_salle ci-dessus.
    N'empeche pas de rejoindre a nouveau (voir la note sur
    expulser_participant dans livekit_tokens.py) : c'est une mesure
    ponctuelle de moderation en seance, pas un bannissement du cours."""
    utilisateur = utilisateur_courant(request, session)
    resultat, erreur = _seance_et_cours_geres(session, seance_id, utilisateur)
    if erreur:
        message, code = erreur
        return JSONResponse({"erreur": message}, status_code=code)
    seance, _cours = resultat

    # Garde-fou serveur en plus de celui cote JS (qui ne montre pas le
    # bouton sur sa propre tuile) : sans ca, un clic malencontreux
    # couperait la Room du professeur lui-meme.
    if utilisateur_id == utilisateur.id:
        return JSONResponse({"erreur": "Impossible de vous expulser vous-meme."}, status_code=400)

    if not livekit_configure():
        return JSONResponse({"erreur": "LiveKit n'est pas configure sur ce serveur."}, status_code=503)

    await expulser_participant(seance.nom_salle_livekit, str(utilisateur_id))
    return JSONResponse({"expulse": True})


@router.get("/classe/seances/{seance_id}/presences")
def voir_presences(request: Request, seance_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    lignes = session.exec(
        select(PresenceSeance, Utilisateur)
        .where(PresenceSeance.seance_id == seance_id)
        .where(PresenceSeance.utilisateur_id == Utilisateur.id)
        .order_by(PresenceSeance.heure_entree)
    ).all()
    presences = [{"presence": p, "utilisateur": u} for p, u in lignes]

    return templates.TemplateResponse(
        request,
        "classe_presences.html",
        {"utilisateur": utilisateur, "cours": cours, "seance": seance, "presences": presences},
    )


def _donnees_tableau(session: Session, seance_id: int, request: Request):
    """Logique commune aux deux routes de rendu du tableau blanc (page
    autonome /tableau et fragment AJAX /tableau/fragment) : verifie les
    droits d'acces et prepare le contexte de template. Factorisee ici pour
    que les deux routes restent strictement identiques en termes de
    permissions — seul le template de sortie differe (page complete vs
    fragment injectable). Retourne soit une RedirectResponse (acces
    refuse), soit (contexte, seance, cours)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303), None, None

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303), None, None
    cours = session.get(Cours, seance.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303), None, None

    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303), None, None

    etat_initial = _reconstituer_etat_tableau(session, seance_id)

    autorises = []
    if peut_gerer:
        lignes = session.exec(
            select(AutorisationEcritureTableau, Utilisateur)
            .where(AutorisationEcritureTableau.seance_id == seance_id)
            .where(AutorisationEcritureTableau.utilisateur_id == Utilisateur.id)
        ).all()
        autorises = [{"utilisateur_id": u.id, "nom": u.nom} for _, u in lignes]

        # Liste des inscrits pour le menu "autoriser quelqu'un" — exclut
        # ceux deja autorises pour ne pas les proposer deux fois.
        deja_autorises_ids = {a["utilisateur_id"] for a in autorises}
        lignes_inscrits = lister_inscriptions_actives(session, cours.id)
        inscrits_non_autorises = [
            {"utilisateur_id": u.id, "nom": u.nom} for _, u in lignes_inscrits if u.id not in deja_autorises_ids
        ]
    else:
        inscrits_non_autorises = []

    peut_ecrire = _peut_ecrire_tableau(session, seance_id, cours, utilisateur)

    # echapper_pour_script() : json.dumps() n'echappe jamais "</script>",
    # et ce JSON est injecte tel quel a l'INTERIEUR d'une balise <script>
    # (voir classe_tableau_fragment.html) -- pas via JSON.parse() sur un
    # texte recu separement. Un evenement de tableau contient du texte
    # libre tape par un etudiant autorise a ecrire (outil "Texte", voir
    # le prompt() cote client) : sans cet echappement, "</script><script>
    # ...</script>" dans ce texte casse hors du <script> d'origine et
    # execute du JS arbitraire pour quiconque ouvre ensuite ce tableau
    # (y compris le prof ou un admin) -- XSS stocke exploitable via le
    # jeton CSRF, expose globalement dans la page, que ce script peut
    # alors lire pour forger n'importe quelle requete au nom de la
    # victime. \u003c/\u003e/\u0026 restent des sequences JSON valides
    # (JSON.parse et l'evaluation JS les decodent normalement en <, >,
    # &) mais n'apparaissent jamais comme caracteres HTML litteraux dans
    # la page -- "</script>" ne peut donc plus jamais s'y former.
    etat_initial_json = (
        json.dumps(etat_initial)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    contexte = {
        "utilisateur": utilisateur, "cours": cours, "seance": seance,
        "peut_gerer": peut_gerer, "peut_ecrire": peut_ecrire,
        "etat_initial_json": etat_initial_json,
        "autorises": autorises, "inscrits_non_autorises": inscrits_non_autorises,
    }
    return contexte, seance, cours


@router.get("/classe/seances/{seance_id}/tableau")
def page_tableau(request: Request, seance_id: int, session: Session = Depends(get_session)):
    resultat, seance, cours = _donnees_tableau(session, seance_id, request)
    if seance is None:
        return resultat  # RedirectResponse (acces refuse / non connecte)
    return templates.TemplateResponse(request, "classe_tableau.html", resultat)


@router.get("/classe/seances/{seance_id}/tableau/fragment")
def fragment_tableau(request: Request, seance_id: int, session: Session = Depends(get_session)):
    """Meme contenu que page_tableau(), mais rendu SANS le template de
    base (pas de <html>/<head>/nav) : c'est ce fragment que
    classe_salle.html charge via fetch() et injecte dans son panneau
    tableau blanc, pour eviter toute navigation de page qui detruirait la
    Room LiveKit (voir commentaire dans classe_salle.html)."""
    resultat, seance, cours = _donnees_tableau(session, seance_id, request)
    if seance is None:
        return resultat  # RedirectResponse (acces refuse / non connecte)
    return templates.TemplateResponse(request, "classe_tableau_fragment.html", resultat)


@router.post("/classe/seances/{seance_id}/tableau/autoriser/{utilisateur_id}")
async def autoriser_ecriture_tableau(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    if not _est_inscrit(session, cours.id, utilisateur_id):
        return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)

    deja = session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur_id,
        )
    ).first()
    if not deja:
        session.add(AutorisationEcritureTableau(seance_id=seance_id, utilisateur_id=utilisateur_id))
        session.commit()

    # Informe en temps reel le concerne (et tout le monde, pour mettre a
    # jour l'affichage "qui peut ecrire" cote prof) sans qu'il ait besoin
    # de recharger la page.
    await gestionnaire.diffuser(f"tableau-{seance_id}", {"type": "permission", "utilisateur_id": utilisateur_id, "autorise": True})

    return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)


@router.post("/classe/seances/{seance_id}/tableau/revoquer/{utilisateur_id}")
async def revoquer_ecriture_tableau(request: Request, seance_id: int, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    seance = session.get(Seance, seance_id)
    if not seance:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, seance.cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{seance.cours_id if cours else ''}", status_code=303)

    autorisation = session.exec(
        select(AutorisationEcritureTableau).where(
            AutorisationEcritureTableau.seance_id == seance_id,
            AutorisationEcritureTableau.utilisateur_id == utilisateur_id,
        )
    ).first()
    if autorisation:
        session.delete(autorisation)
        session.commit()

    await gestionnaire.diffuser(f"tableau-{seance_id}", {"type": "permission", "utilisateur_id": utilisateur_id, "autorise": False})

    return RedirectResponse(f"/classe/seances/{seance_id}/tableau", status_code=303)


@router.websocket("/classe/seances/{seance_id}/tableau/ws")
async def tableau_ws(websocket: WebSocket, seance_id: int):
    """Synchronisation temps reel du tableau blanc. Reutilise le meme
    gestionnaire de connexions que le chat des cercles (app/ws_manager.py),
    avec une cle de salle distincte ("tableau-{id}") pour ne jamais se
    melanger avec les salons de cercles d'etude qui partagent le meme
    objet gestionnaire.

    Chaque evenement recu est REVALIDE cote serveur avant d'etre persiste
    et diffuse (type reconnu, permission d'ecriture a l'instant present —
    pas seulement a la connexion, puisqu'elle peut etre revoquee en
    cours de route) : un client qui bidouillerait son JS ne peut pas
    dessiner sans autorisation reelle, seulement casser sa propre
    experience locale."""
    with Session(engine) as session:
        user_id = websocket.session.get("user_id")
        if not user_id:
            await websocket.close(code=4401)
            return

        utilisateur = session.get(Utilisateur, user_id)
        if not utilisateur or not session_utilisateur_valide(websocket.session, utilisateur):
            await websocket.close(code=4401)
            return

        seance = session.get(Seance, seance_id)
        if not seance:
            await websocket.close(code=4404)
            return
        cours = session.get(Cours, seance.cours_id)
        if not cours:
            await websocket.close(code=4404)
            return

        peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
        if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
            await websocket.close(code=4403)
            return

        cle_salle = f"tableau-{seance_id}"
        await gestionnaire.connecter(cle_salle, websocket, utilisateur.id, utilisateur.nom)

        try:
            while True:
                brut = await websocket.receive_json()
                if limite_depassee(f"ws-tableau:user:{utilisateur.id}:{seance_id}", 240, 60):
                    continue
                type_evt = brut.get("type")

                if type_evt not in ("trait", "forme", "texte", "suppression", "effacer_tout"):
                    continue  # type inconnu, ignore silencieusement

                # Revalidation de permission a CHAQUE evenement (pas
                # seulement a la connexion) : une autorisation revoquee
                # entre-temps doit bloquer immediatement, pas seulement
                # apres une reconnexion.
                with Session(engine) as session_fraiche:
                    utilisateur_frais = session_fraiche.get(Utilisateur, utilisateur.id)
                    seance_fraiche = session_fraiche.get(Seance, seance_id)
                    cours_frais = (
                        session_fraiche.get(Cours, seance_fraiche.cours_id)
                        if seance_fraiche
                        else None
                    )
                    if (
                        not utilisateur_frais
                        or not session_utilisateur_valide(websocket.session, utilisateur_frais)
                        or utilisateur_frais.banni
                        or not seance_fraiche
                        or not cours_frais
                    ):
                        await websocket.close(code=4401)
                        break

                    # L'inscription et le role sont relus a chaque evenement :
                    # une revocation en cours de session doit prendre effet
                    # sans attendre une nouvelle connexion WebSocket.
                    peut_gerer_frais = _peut_gerer_cours(cours_frais, utilisateur_frais, session_fraiche)
                    if not peut_gerer_frais and not _est_inscrit(
                        session_fraiche, cours_frais.id, utilisateur_frais.id
                    ):
                        await websocket.close(code=4403)
                        break

                    if not _peut_ecrire_tableau(
                        session_fraiche, seance_fraiche.id, cours_frais, utilisateur_frais
                    ):
                        continue

                    if type_evt == "effacer_tout" and not peut_gerer_frais:
                        # Effacer TOUT le tableau reste reserve au
                        # prof/admin, meme pour un etudiant autorise a
                        # dessiner — un etudiant autorise peut ajouter et
                        # annuler SES PROPRES traits, pas rayer le travail
                        # de tout le monde.
                        continue

                    element_id = str(brut.get("element_id", ""))[:100]
                    if not element_id:
                        continue

                    if type_evt == "suppression":
                        # Un etudiant ne peut supprimer QUE ses propres
                        # elements ; le prof/admin peut supprimer
                        # n'importe lequel (moderation).
                        if not peut_gerer_frais:
                            evenement_original = session_fraiche.exec(
                                select(EvenementTableauBlanc)
                                .where(EvenementTableauBlanc.seance_id == seance_id)
                                .where(EvenementTableauBlanc.element_id == element_id)
                                .where(EvenementTableauBlanc.type_evenement != TypeEvenementTableau.SUPPRESSION)
                                .order_by(EvenementTableauBlanc.date_creation.desc())
                            ).first()
                            if not evenement_original or evenement_original.utilisateur_id != utilisateur.id:
                                continue

                    donnees = brut.get("donnees", {})
                    try:
                        donnees_json = json.dumps(donnees)[:20000]  # borne la taille d'un evenement
                    except (TypeError, ValueError):
                        continue

                    evenement = EvenementTableauBlanc(
                        seance_id=seance_id,
                        utilisateur_id=utilisateur.id,
                        type_evenement=TypeEvenementTableau(type_evt),
                        element_id=element_id,
                        donnees=donnees_json,
                    )
                    session_fraiche.add(evenement)
                    session_fraiche.commit()

                await gestionnaire.diffuser(cle_salle, {
                    "type": type_evt,
                    "element_id": element_id,
                    "utilisateur_id": utilisateur.id,
                    "donnees": donnees,
                })
        except WebSocketDisconnect:
            pass
        finally:
            gestionnaire.deconnecter(cle_salle, websocket)


# ============================================================
# Devoirs & rendus
# ============================================================

@router.post("/classe/{cours_id}/devoirs/creer")
def creer_devoir(
    request: Request,
    cours_id: int,
    titre: str = Form(...),
    description: Optional[str] = Form(None),
    date_limite: Optional[str] = Form(None),
    bareme: str = Form("20"),
    coefficient: str = Form("1"),
    periode: Optional[str] = Form(None),
    criteres: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse(f"/classe/{cours_id}", status_code=303)

    titre = " ".join((titre or "").split())
    try:
        bareme_valide = float((bareme or "20").replace(",", "."))
        coefficient_valide = float((coefficient or "1").replace(",", "."))
        if (not titre or len(titre) > 180 or not 1 <= bareme_valide <= 1000
                or not math.isfinite(coefficient_valide) or not 0.1 <= coefficient_valide <= 10):
            raise ValueError
        periode_validee = " ".join((periode or "").split())[:40] or None
        criteres_valides = _normaliser_criteres_devoir(criteres, bareme_valide)
    except ValueError:
        return RedirectResponse(f"/classe/{cours_id}?erreur=devoir_invalide#devoir-create-title", status_code=303)

    date_limite_parsee = None
    if date_limite:
        try:
            date_limite_parsee = datetime.fromisoformat(date_limite)
        except ValueError:
            return RedirectResponse(f"/classe/{cours_id}?erreur=date_invalide#devoir-create-title", status_code=303)

    devoir = Devoir(
        cours_id=cours_id,
        titre=titre,
        description=(description or "").strip()[:6000] or None,
        date_limite=date_limite_parsee,
        bareme=round(bareme_valide, 2),
        coefficient=round(coefficient_valide, 2),
        periode=periode_validee,
        criteres_json=json.dumps(criteres_valides, ensure_ascii=False) if criteres_valides else None,
    )
    session.add(devoir)
    session.commit()
    session.refresh(devoir)
    for inscription, etudiant in lister_inscriptions_actives(session, cours_id):
        session.add(Notification(
            destinataire_id=etudiant.id,
            cours_id=cours_id,
            type_notification=TypeNotification.NOUVEAU_DEVOIR,
            contenu=f"Nouveau devoir « {devoir.titre} » dans le cours « {cours.nom} ».",
            acteur_id=utilisateur.id,
            url_destination=f"/classe/devoirs/{devoir.id}",
        ))
    session.commit()
    return RedirectResponse(f"/classe/{cours_id}?devoir=cree", status_code=303)


@router.get("/classe/devoirs/{devoir_id}")
def detail_devoir(request: Request, devoir_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    devoir = session.get(Devoir, devoir_id)
    if not devoir:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, devoir.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    if not peut_gerer and not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if not peut_gerer and devoir.archive:
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)
    delai_depasse = bool(devoir.date_limite and datetime.utcnow() > devoir.date_limite)
    peut_rendre = not peut_gerer and not delai_depasse and not devoir.est_clos and not devoir.archive

    mon_rendu = None
    mon_rendu_details = ""
    if not peut_gerer:
        mon_rendu = session.exec(
            select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id, RenduDevoir.utilisateur_id == utilisateur.id)
        ).first()
        if mon_rendu:
            mon_rendu_details = _details_correction_rendu(mon_rendu)

    rendus = []
    if peut_gerer:
        ids_etudiants_actifs = [
            etudiant.id for _, etudiant in lister_inscriptions_actives(session, cours.id)
        ]
        lignes = session.exec(
            select(RenduDevoir, Utilisateur)
            .where(RenduDevoir.devoir_id == devoir_id)
            .where(RenduDevoir.utilisateur_id == Utilisateur.id)
            .where(RenduDevoir.utilisateur_id.in_(ids_etudiants_actifs))
            .order_by(RenduDevoir.date_rendu.desc())
        ).all() if ids_etudiants_actifs else []
        rendus = []
        for rendu, etudiant in lignes:
            try:
                suggestion_ia = json.loads(rendu.correction_ia_json or "null")
            except (TypeError, ValueError, json.JSONDecodeError):
                suggestion_ia = None
            rendus.append({
                "rendu": rendu,
                "utilisateur": etudiant,
                "suggestion_ia": suggestion_ia,
                "details_correction": _details_correction_rendu(rendu),
            })

    return templates.TemplateResponse(
        request,
        "classe_devoir.html",
        {
            "utilisateur": utilisateur, "cours": cours, "devoir": devoir, "peut_gerer": peut_gerer,
            "delai_depasse": delai_depasse, "peut_rendre": peut_rendre,
            "mon_rendu": mon_rendu, "mon_rendu_details": mon_rendu_details, "rendus": rendus,
            "criteres_devoir": _lire_criteres_devoir(devoir),
        },
    )


@router.post("/classe/devoirs/{devoir_id}/modifier")
def modifier_devoir(
    request: Request,
    devoir_id: int,
    titre: str = Form(...),
    description: Optional[str] = Form(None),
    date_limite: Optional[str] = Form(None),
    bareme: str = Form("20"),
    coefficient: str = Form("1"),
    periode: Optional[str] = Form(None),
    criteres: Optional[str] = Form(None),
    etat: str = Form("ouvert"),
    archivage: str = Form("actif"),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    devoir = session.get(Devoir, devoir_id)
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not devoir or not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)

    titre = " ".join((titre or "").split())
    try:
        bareme_valide = float((bareme or "").replace(",", "."))
        coefficient_valide = float((coefficient or "1").replace(",", "."))
        if (not titre or len(titre) > 180 or not 1 <= bareme_valide <= 1000
                or not math.isfinite(coefficient_valide) or not 0.1 <= coefficient_valide <= 10):
            raise ValueError
        periode_validee = " ".join((periode or "").split())[:40] or None
        criteres_valides = _normaliser_criteres_devoir(criteres, bareme_valide)
    except ValueError:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=devoir_invalide#modifier-devoir", status_code=303)

    rendus_deja_notes = session.exec(
        select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id)
    ).all()
    if any(
        rendu.note is not None and rendu.note > bareme_valide
        for rendu in rendus_deja_notes
    ):
        return RedirectResponse(
            f"/classe/devoirs/{devoir_id}?erreur=bareme_note_existante#modifier-devoir",
            status_code=303,
        )

    date_limite_parsee = None
    if date_limite:
        try:
            date_limite_parsee = datetime.fromisoformat(date_limite)
        except ValueError:
            return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=date_invalide#modifier-devoir", status_code=303)

    devoir.titre = titre
    devoir.description = (description or "").strip()[:6000] or None
    devoir.date_limite = date_limite_parsee
    devoir.bareme = round(bareme_valide, 2)
    devoir.coefficient = round(coefficient_valide, 2)
    devoir.periode = periode_validee
    devoir.criteres_json = json.dumps(criteres_valides, ensure_ascii=False) if criteres_valides else None
    devoir.est_clos = etat == "ferme"
    devoir.archive = archivage == "archive"
    session.add(devoir)
    session.commit()
    return RedirectResponse(f"/classe/devoirs/{devoir_id}?modifie=1", status_code=303)


@router.post("/classe/devoirs/{devoir_id}/supprimer")
def supprimer_devoir(
    request: Request,
    devoir_id: int,
    confirmation: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    devoir = session.get(Devoir, devoir_id)
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not devoir or not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)
    if confirmation != "SUPPRIMER":
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=confirmation_requise", status_code=303)

    rendus = session.exec(select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id)).all()
    fichiers_a_supprimer = [rendu.chemin_fichier for rendu in rendus if rendu.chemin_fichier]
    for rendu in rendus:
        session.delete(rendu)
    session.delete(devoir)
    session.commit()
    for chemin in fichiers_a_supprimer:
        try:
            supprimer_fichier(chemin)
        except Exception:
            # Le devoir et ses rendus sont déjà supprimés en base ; le
            # nettoyage du stockage reste best-effort et ne bloque pas.
            pass
    return RedirectResponse(f"/classe/{cours.id}?devoir=supprime", status_code=303)


@router.get("/classe/{cours_id}/notes.csv")
def exporter_notes_cours(
    request: Request,
    cours_id: int,
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    cours = session.get(Cours, cours_id)
    if not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)

    devoirs = session.exec(
        select(Devoir).where(Devoir.cours_id == cours_id).order_by(Devoir.date_creation)
    ).all()
    inscriptions = sorted(
        lister_inscriptions_actives(session, cours_id),
        key=lambda ligne: (ligne[1].nom or "").casefold(),
    )
    ids_devoirs = [devoir.id for devoir in devoirs]
    rendus = session.exec(
        select(RenduDevoir).where(RenduDevoir.devoir_id.in_(ids_devoirs))
    ).all() if ids_devoirs else []
    par_etudiant_devoir = {(rendu.utilisateur_id, rendu.devoir_id): rendu for rendu in rendus}

    sortie = io.StringIO()
    sortie.write("\ufeff")
    writer = csv.writer(sortie)
    writer.writerow(["Étudiant", "Cours", "Devoir", "Période", "Coefficient", "Note", "Barème", "Date de rendu", "Date de correction", "Appréciation"])
    for _inscription, etudiant in inscriptions:
        for devoir in devoirs:
            rendu = par_etudiant_devoir.get((etudiant.id, devoir.id))
            writer.writerow([
                _valeur_csv_securisee(etudiant.nom),
                _valeur_csv_securisee(cours.nom),
                _valeur_csv_securisee(devoir.titre),
                _valeur_csv_securisee(devoir.periode or "Sans période"),
                devoir.coefficient,
                rendu.note if rendu and rendu.note is not None else "",
                devoir.bareme,
                rendu.date_rendu.strftime("%Y-%m-%d %H:%M") if rendu else "",
                rendu.date_correction.strftime("%Y-%m-%d %H:%M") if rendu and rendu.date_correction else "",
                _valeur_csv_securisee(rendu.appreciation_prof) if rendu else "",
            ])
    return Response(
        content=sortie.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="notes-cours-{cours_id}.csv"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/classe/devoirs/rendus/{rendu_id}/aide-correction")
def aide_correction_ia(
    request: Request,
    rendu_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    rendu = session.get(RenduDevoir, rendu_id)
    devoir = session.get(Devoir, rendu.devoir_id) if rendu else None
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not rendu or not devoir or not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)
    if limite_depassee(f"correction-ia:user:{utilisateur.id}", 5, 3600):
        return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=limite_ia#rendus", status_code=303)

    try:
        with ouvrir_fichier_local(rendu.chemin_fichier) as chemin_local:
            texte_copie = extraire_texte(str(chemin_local))
        if len((texte_copie or "").strip()) < 80:
            return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=texte_illisible#rendus", status_code=303)
        criteres = _lire_criteres_devoir(devoir)
        suggestion = classe_correction.generer_suggestion_correction(
            titre=devoir.titre,
            consigne=devoir.description or "",
            bareme=devoir.bareme,
            criteres=criteres,
            texte_copie=texte_copie,
            commentaire_etudiant=rendu.commentaire or "",
        )
        suggestion["generee_le"] = datetime.utcnow().isoformat()
        rendu.correction_ia_json = json.dumps(suggestion, ensure_ascii=False)
        session.add(rendu)
        session.commit()
    except RuntimeError:
        return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=ia_indisponible#rendus", status_code=303)
    except Exception:
        return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=correction_impossible#rendus", status_code=303)
    return RedirectResponse(f"/classe/devoirs/{devoir.id}?ia=proposee#rendus", status_code=303)


@router.post("/classe/devoirs/{devoir_id}/rendre")
def rendre_devoir(
    request: Request,
    devoir_id: int,
    commentaire: Optional[str] = Form(None),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    devoir = session.get(Devoir, devoir_id)
    if not devoir:
        return RedirectResponse("/classe", status_code=303)
    cours = session.get(Cours, devoir.cours_id)
    if not cours:
        return RedirectResponse("/classe", status_code=303)

    # Rendre un devoir est reserve aux etudiants inscrits — un
    # professeur/admin gere le devoir, il ne "rend" pas de copie.
    if not _est_inscrit(session, cours.id, utilisateur.id):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    host = adresse_ip_client(request)
    if limite_depassee(f"upload-devoir:user:{utilisateur.id}", 10, 3600) or limite_depassee(f"upload-devoir:ip:{host}", 25, 3600):
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=trop_de_depots", status_code=303)

    if devoir.archive or devoir.est_clos:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=devoir_ferme", status_code=303)
    if devoir.date_limite and datetime.utcnow() > devoir.date_limite:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=delai_depasse", status_code=303)

    reference = f"devoir{devoir_id}_etu{utilisateur.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    try:
        chemin_stocke = sauvegarder_fichier(fichier, reference)
    except FichierInvalide as erreur:
        return RedirectResponse(f"/classe/devoirs/{devoir_id}?erreur=fichier_invalide", status_code=303)

    # Un seul rendu "vivant" par etudiant : un nouveau depot ecrase le
    # precedent (mais garde le meme enregistrement, donc perd la note
    # deja donnee si l'etudiant re-rend apres correction — comportement
    # voulu : la nouvelle copie doit etre re-corrigee, pas heriter d'une
    # note qui ne correspond plus au contenu rendu).
    rendu_existant = session.exec(
        select(RenduDevoir).where(RenduDevoir.devoir_id == devoir_id, RenduDevoir.utilisateur_id == utilisateur.id)
    ).first()
    ancien_chemin = rendu_existant.chemin_fichier if rendu_existant else None
    if rendu_existant:
        rendu_existant.chemin_fichier = chemin_stocke
        rendu_existant.nom_fichier_original = fichier.filename or "rendu"
        rendu_existant.commentaire = (commentaire or "").strip()[:1500] or None
        rendu_existant.date_rendu = datetime.utcnow()
        rendu_existant.note = None
        rendu_existant.appreciation_prof = None
        rendu_existant.details_correction_json = None
        rendu_existant.correction_ia_json = None
        rendu_existant.date_correction = None
        session.add(rendu_existant)
    else:
        session.add(RenduDevoir(
            devoir_id=devoir_id, utilisateur_id=utilisateur.id, chemin_fichier=chemin_stocke,
            nom_fichier_original=fichier.filename or "rendu", commentaire=commentaire or None,
        ))
    session.commit()
    if ancien_chemin and ancien_chemin != chemin_stocke:
        try:
            supprimer_fichier(ancien_chemin)
        except Exception:
            pass

    return RedirectResponse(f"/classe/devoirs/{devoir_id}?rendu=1", status_code=303)


@router.get("/classe/devoirs/rendus/{rendu_id}/telecharger")
def telecharger_rendu(request: Request, rendu_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    rendu = session.get(RenduDevoir, rendu_id)
    if not rendu:
        return RedirectResponse("/classe", status_code=303)
    devoir = session.get(Devoir, rendu.devoir_id)
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not devoir or not cours:
        return RedirectResponse("/classe", status_code=303)

    # Le prof/admin du cours peut telecharger n'importe quel rendu ;
    # l'etudiant peut seulement telecharger LE SIEN (jamais celui d'un
    # camarade, meme en devinant l'id).
    peut_gerer = _peut_gerer_cours(cours, utilisateur, session)
    if not peut_gerer and (
        rendu.utilisateur_id != utilisateur.id
        or not _est_inscrit(session, cours.id, utilisateur.id)
    ):
        return RedirectResponse(f"/classe/{cours.id}", status_code=303)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(rendu.chemin_fichier))
    return FileResponse(rendu.chemin_fichier, filename=rendu.nom_fichier_original)


@router.post("/classe/devoirs/rendus/{rendu_id}/noter")
def noter_rendu(
    request: Request,
    rendu_id: int,
    note: str = Form(...),
    appreciation_prof: Optional[str] = Form(None),
    details_correction: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    rendu = session.get(RenduDevoir, rendu_id)
    devoir = session.get(Devoir, rendu.devoir_id) if rendu else None
    cours = session.get(Cours, devoir.cours_id) if devoir else None
    if not rendu or not devoir or not cours or not _peut_gerer_cours(cours, utilisateur, session):
        return RedirectResponse("/classe", status_code=303)

    try:
        note_validee = float((note or "").replace(",", "."))
    except ValueError:
        return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=note_invalide#rendus", status_code=303)
    if not math.isfinite(note_validee) or note_validee < 0 or note_validee > devoir.bareme:
        return RedirectResponse(f"/classe/devoirs/{devoir.id}?erreur=note_hors_bareme#rendus", status_code=303)

    ancienne_note = rendu.note
    details = (details_correction or "").strip()[:4000]
    rendu.note = round(note_validee, 2)
    rendu.appreciation_prof = (appreciation_prof or "").strip()[:1800] or None
    rendu.details_correction_json = json.dumps(
        {"commentaire_criteres": details}, ensure_ascii=False
    ) if details else None
    rendu.date_correction = datetime.utcnow()
    session.add(rendu)
    if ancienne_note is None or ancienne_note != rendu.note:
        session.add(Notification(
            destinataire_id=rendu.utilisateur_id,
            cours_id=cours.id,
            type_notification=TypeNotification.NOTE_PUBLIEE,
            contenu=f"Ta note pour « {devoir.titre} » dans « {cours.nom} » est disponible.",
            acteur_id=utilisateur.id,
            url_destination=f"/classe/devoirs/{devoir.id}",
        ))
    session.commit()
    return RedirectResponse(f"/classe/devoirs/{devoir.id}?correction=validee#rendus", status_code=303)
