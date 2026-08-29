"""
Surface admin generale : page d'accueil recapitulative, statistiques,
moderation du salon (traitement des signalements), gestion des
utilisateurs (bannissement). Distinct de abonnement_router.py qui gere
deja /admin/abonnements (validation des paiements) — on ne duplique pas
cette partie, juste on y renvoie depuis la page d'accueil admin.
"""
import json
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, func

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..models import (
    Utilisateur, RoleUtilisateur, CercleEtude, MembreCercle, MessageCercle, SignalementMessage,
    DemandeAdhesionCercle, StatutDemandeAdhesion, Document, StatutDocument, TentativeQuiz, AbonnementEtudiant,
    StatutAbonnementEtudiant, SignalementQuestionQuiz, CodeSecours2FA, SessionTuteur,
    ConsultationDocument, Abonnement, StatutAbonnement, Cours, InscriptionCours, Seance, PresenceSeance,
    EvenementTableauBlanc, AutorisationEcritureTableau, Devoir, RenduDevoir,
    Feedback, ReponseFeedback, StatutFeedback,
)
from ..storage import supprimer_fichier
# Logique d'acceptation/refus reutilisee telle quelle depuis cercles_router.py
# (meme principe que _assurer_membres_admins deja importe dans
# admin_referentiel_router.py) : on evite de dupliquer la reverification de
# profil faite au moment du traitement d'une demande d'adhesion.
from .cercles_router import _traiter_acceptation_demande, _traiter_refus_demande
import secrets

router = APIRouter()


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


@router.get("/admin")
def page_accueil_admin(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    nb_signalements_en_attente = len(
        session.exec(select(SignalementMessage).where(SignalementMessage.traite == False)).all()  # noqa: E712
    )
    nb_signalements_quiz_en_attente = len(
        session.exec(select(SignalementQuestionQuiz).where(SignalementQuestionQuiz.traite == False)).all()  # noqa: E712
    )
    nb_abonnements_en_attente = len(
        session.exec(
            select(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.EN_ATTENTE)
        ).all()
    )
    nb_sponsors_en_attente = len(
        session.exec(
            select(Abonnement).where(Abonnement.statut == StatutAbonnement.EN_ATTENTE_PAIEMENT)
        ).all()
    )
    nb_demandes_adhesion_en_attente = len(
        session.exec(
            select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE)
        ).all()
    )
    # Feedbacks sans reponse : on exclut ceux deja masques (une reponse
    # n'y a plus vraiment sa place une fois l'avis retire de la vue
    # publique), meme logique que le calcul fait dans feedback_router.py.
    ids_feedback_avec_reponse = {
        r.feedback_id for r in session.exec(select(ReponseFeedback)).all()
    }
    nb_feedbacks_sans_reponse = len([
        f for f in session.exec(select(Feedback)).all()
        if f.id not in ids_feedback_avec_reponse and f.statut != StatutFeedback.MASQUE
    ])

    return templates.TemplateResponse(
        request,
        "admin_index.html",
        {
            "utilisateur": admin,
            "nb_signalements_en_attente": nb_signalements_en_attente,
            "nb_signalements_quiz_en_attente": nb_signalements_quiz_en_attente,
            "nb_abonnements_en_attente": nb_abonnements_en_attente,
            "nb_sponsors_en_attente": nb_sponsors_en_attente,
            "nb_demandes_adhesion_en_attente": nb_demandes_adhesion_en_attente,
            "nb_feedbacks_sans_reponse": nb_feedbacks_sans_reponse,
        },
    )


@router.get("/admin/demandes-adhesion")
def page_demandes_adhesion(request: Request, session: Session = Depends(get_session)):
    """Vue globale (tous cercles confondus) des demandes d'adhesion en
    attente — jusqu'ici la SEULE facon de les voir etait d'ouvrir
    individuellement chaque cercle concerne via son menu "Options du
    cercle", ce qui les rendait invisibles pour un admin qui ne savait
    pas deja lequel en avait."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    lignes = session.exec(
        select(DemandeAdhesionCercle, Utilisateur, CercleEtude)
        .where(DemandeAdhesionCercle.statut == StatutDemandeAdhesion.EN_ATTENTE)
        .where(DemandeAdhesionCercle.utilisateur_id == Utilisateur.id)
        .where(DemandeAdhesionCercle.cercle_id == CercleEtude.id)
        .order_by(DemandeAdhesionCercle.date_creation)
    ).all()
    demandes = [{"demande": d, "utilisateur": u, "cercle": c} for d, u, c in lignes]

    return templates.TemplateResponse(
        request,
        "admin_demandes_adhesion_cercle.html",
        {"utilisateur": admin, "demandes": demandes},
    )


@router.post("/admin/demandes-adhesion/{demande_id}/accepter")
def accepter_demande_adhesion_admin(
    request: Request, demande_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    demande = session.get(DemandeAdhesionCercle, demande_id)
    cercle = session.get(CercleEtude, demande.cercle_id) if demande else None
    if not demande or not cercle:
        return RedirectResponse("/admin/demandes-adhesion", status_code=303)

    resultat = _traiter_acceptation_demande(session, cercle, demande, admin)
    if resultat == "profil_change":
        return RedirectResponse(f"/admin/demandes-adhesion?erreur=profil_change&demande={demande_id}", status_code=303)

    return RedirectResponse("/admin/demandes-adhesion", status_code=303)


@router.post("/admin/demandes-adhesion/{demande_id}/refuser")
def refuser_demande_adhesion_admin(
    request: Request, demande_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    demande = session.get(DemandeAdhesionCercle, demande_id)
    if demande:
        _traiter_refus_demande(session, demande, admin)

    return RedirectResponse("/admin/demandes-adhesion", status_code=303)


@router.get("/admin/stats")
def page_stats(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    nb_etudiants = session.exec(
        select(func.count()).select_from(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ETUDIANT)
    ).one()
    nb_essai_actif = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.ESSAI)
    ).one()
    nb_abonnes_actifs = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.ACTIF)
    ).one()
    nb_demandes_en_attente = session.exec(
        select(func.count()).select_from(AbonnementEtudiant).where(AbonnementEtudiant.statut == StatutAbonnementEtudiant.EN_ATTENTE)
    ).one()
    nb_documents_approuves = session.exec(
        select(func.count()).select_from(Document).where(Document.statut == StatutDocument.APPROUVE)
    ).one()
    nb_documents_en_attente = session.exec(
        select(func.count()).select_from(Document).where(Document.statut == StatutDocument.EN_ATTENTE)
    ).one()
    nb_quiz_realises = session.exec(
        select(func.count()).select_from(TentativeQuiz).where(TentativeQuiz.date_soumission.is_not(None))
    ).one()
    nb_cercles = session.exec(select(func.count()).select_from(CercleEtude)).one()
    nb_signalements_en_attente = session.exec(
        select(func.count()).select_from(SignalementMessage).where(SignalementMessage.traite == False)  # noqa: E712
    ).one()
    nb_signalements_quiz_en_attente = session.exec(
        select(func.count()).select_from(SignalementQuestionQuiz).where(SignalementQuestionQuiz.traite == False)  # noqa: E712
    ).one()

    # Matieres les plus demandees en quiz (top 5), calcule en Python sur un
    # petit GROUP BY — volume attendu trop faible pour justifier plus.
    lignes_matieres = session.exec(
        select(TentativeQuiz.matiere, func.count()).group_by(TentativeQuiz.matiere).order_by(func.count().desc())
    ).all()

    return templates.TemplateResponse(
        request,
        "admin_stats.html",
        {
            "utilisateur": admin,
            "nb_etudiants": nb_etudiants,
            "nb_essai_actif": nb_essai_actif,
            "nb_abonnes_actifs": nb_abonnes_actifs,
            "nb_demandes_en_attente": nb_demandes_en_attente,
            "nb_documents_approuves": nb_documents_approuves,
            "nb_documents_en_attente": nb_documents_en_attente,
            "nb_quiz_realises": nb_quiz_realises,
            "nb_cercles": nb_cercles,
            "nb_signalements_en_attente": nb_signalements_en_attente,
            "nb_signalements_quiz_en_attente": nb_signalements_quiz_en_attente,
            "top_matieres": lignes_matieres[:5],
        },
    )


@router.get("/admin/moderation-salon")
def page_moderation_salon(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    lignes = session.exec(
        select(SignalementMessage, MessageCercle, Utilisateur, CercleEtude)
        .where(SignalementMessage.traite == False)  # noqa: E712
        .where(SignalementMessage.message_id == MessageCercle.id)
        .where(SignalementMessage.signale_par_id == Utilisateur.id)
        .where(MessageCercle.cercle_id == CercleEtude.id)
        .order_by(SignalementMessage.date_signalement.desc())
    ).all()

    signalements = [
        {
            "signalement": s,
            "message": m,
            "signale_par": u,
            "cercle": c,
            "message_deja_supprime": m.supprime,
        }
        for s, m, u, c in lignes
    ]

    return templates.TemplateResponse(
        request,
        "admin_moderation_salon.html",
        {"utilisateur": admin, "signalements": signalements},
    )


@router.post("/admin/moderation-salon/{signalement_id}/supprimer-message")
def moderer_supprimer_message(request: Request, signalement_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementMessage, signalement_id)
    if signalement:
        message = session.get(MessageCercle, signalement.message_id)
        if message:
            message.supprime = True
            session.add(message)
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-salon", status_code=303)


@router.post("/admin/moderation-salon/{signalement_id}/rejeter")
def moderer_rejeter_signalement(request: Request, signalement_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementMessage, signalement_id)
    if signalement:
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-salon", status_code=303)


@router.get("/admin/moderation-quiz")
def page_moderation_quiz(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    lignes = session.exec(
        select(SignalementQuestionQuiz, TentativeQuiz, Utilisateur)
        .where(SignalementQuestionQuiz.traite == False)  # noqa: E712
        .where(SignalementQuestionQuiz.tentative_id == TentativeQuiz.id)
        .where(SignalementQuestionQuiz.signale_par_id == Utilisateur.id)
        .order_by(SignalementQuestionQuiz.date_signalement.desc())
    ).all()

    signalements = []
    for s, tentative, signale_par in lignes:
        try:
            question = json.loads(tentative.questions_json)[s.index_question]
        except (json.JSONDecodeError, IndexError, KeyError):
            question = None
        signalements.append({
            "signalement": s,
            "tentative": tentative,
            "signale_par": signale_par,
            "question": question,
        })

    return templates.TemplateResponse(
        request,
        "admin_moderation_quiz.html",
        {"utilisateur": admin, "signalements": signalements},
    )


@router.post("/admin/moderation-quiz/{signalement_id}/traiter")
def moderer_traiter_signalement_quiz(request: Request, signalement_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    signalement = session.get(SignalementQuestionQuiz, signalement_id)
    if signalement:
        signalement.traite = True
        session.add(signalement)
        session.commit()

    return RedirectResponse("/admin/moderation-quiz", status_code=303)


@router.get("/admin/utilisateurs")
def page_utilisateurs(request: Request, q: Optional[str] = None, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    requete = select(Utilisateur).order_by(Utilisateur.date_creation.desc())
    if q:
        terme = f"%{q.strip()}%"
        requete = requete.where((Utilisateur.nom.ilike(terme)) | (Utilisateur.telephone.ilike(terme)))
    utilisateurs = session.exec(requete).all()

    return templates.TemplateResponse(
        request,
        "admin_utilisateurs.html",
        {"utilisateur": admin, "utilisateurs": utilisateurs, "recherche": q or ""},
    )


@router.post("/admin/utilisateurs/{utilisateur_id}/bannir")
def bannir_utilisateur(request: Request, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    # Un admin ne peut pas se bannir lui-meme (garde-fou simple pour eviter
    # de se retrouver bloque hors de l'interface admin par erreur).
    if cible and cible.id != admin.id:
        cible.banni = True
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)


@router.post("/admin/utilisateurs/{utilisateur_id}/debannir")
def debannir_utilisateur(request: Request, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if cible:
        cible.banni = False
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)


@router.post("/admin/utilisateurs/{utilisateur_id}/promouvoir-professeur")
def promouvoir_professeur(request: Request, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """PROFESSEUR n'est jamais auto-attribuable a l'inscription (comme
    ADMIN) : seul un admin peut accorder ce role, ici. Evite qu'un
    utilisateur se declare professeur pour ouvrir des cours en son nom."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if cible and cible.role == RoleUtilisateur.ETUDIANT:
        cible.role = RoleUtilisateur.PROFESSEUR
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)


@router.post("/admin/utilisateurs/{utilisateur_id}/retrograder-etudiant")
def retrograder_etudiant(request: Request, utilisateur_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    """Retire le statut PROFESSEUR ou ADMIN d'un utilisateur (retour a
    ETUDIANT). Pour un ADMIN, deux garde-fous en plus du controle deja
    fait cote template (le bouton n'apparait pas sur sa propre ligne) :
    - un admin ne peut pas se retrograder lui-meme (meme logique que
      l'auto-bannissement plus haut) ;
    - impossible de retrograder le DERNIER admin restant, pour ne
      jamais se retrouver avec une plateforme sans aucun admin."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if not cible:
        return RedirectResponse("/admin/utilisateurs", status_code=303)

    if cible.role == RoleUtilisateur.PROFESSEUR:
        cible.role = RoleUtilisateur.ETUDIANT
        session.add(cible)
        session.commit()
    elif cible.role == RoleUtilisateur.ADMIN:
        if cible.id == admin.id:
            return RedirectResponse("/admin/utilisateurs?erreur=auto_retrogradation", status_code=303)
        nb_admins = len(session.exec(select(Utilisateur).where(Utilisateur.role == RoleUtilisateur.ADMIN)).all())
        if nb_admins <= 1:
            return RedirectResponse("/admin/utilisateurs?erreur=dernier_admin", status_code=303)
        cible.role = RoleUtilisateur.ETUDIANT
        session.add(cible)
        session.commit()

    return RedirectResponse("/admin/utilisateurs", status_code=303)


@router.get("/admin/utilisateurs/{utilisateur_id}/supprimer")
def page_confirmation_suppression(request: Request, utilisateur_id: int, session: Session = Depends(get_session)):
    """Page de confirmation avant suppression definitive. Liste les
    espaces POSSEDES par la cible (Cercles crees, Cours animes) pour que
    l'admin choisisse, POUR CHACUN, individuellement :
      - les reattribuer a un autre compte (le cercle/cours et tout son
        contenu — membres, messages, seances, devoirs — survit intact,
        seul le proprietaire change) ;
      - ou les supprimer definitivement avec tout leur contenu.
    Rien n'est modifie a cette etape (GET, pure lecture)."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if not cible or cible.id == admin.id:
        return RedirectResponse("/admin/utilisateurs", status_code=303)

    cercles_possedes = session.exec(select(CercleEtude).where(CercleEtude.createur_id == utilisateur_id)).all()
    cercles_info = []
    for c in cercles_possedes:
        nb_membres = len(session.exec(select(MembreCercle).where(MembreCercle.cercle_id == c.id)).all())
        nb_messages = len(session.exec(select(MessageCercle).where(MessageCercle.cercle_id == c.id)).all())
        cercles_info.append({"cercle": c, "nb_membres": nb_membres, "nb_messages": nb_messages})

    cours_possedes = session.exec(select(Cours).where(Cours.professeur_id == utilisateur_id)).all()
    cours_info = []
    for c in cours_possedes:
        nb_inscrits = len(session.exec(select(InscriptionCours).where(InscriptionCours.cours_id == c.id)).all())
        nb_seances = len(session.exec(select(Seance).where(Seance.cours_id == c.id)).all())
        cours_info.append({"cours": c, "nb_inscrits": nb_inscrits, "nb_seances": nb_seances})

    # Cibles de reattribution possibles : tout compte autre que la cible
    # elle-meme. Un cercle/cours peut techniquement etre reattribue a
    # n'importe qui (etudiant compris, comme une creation normale) —
    # seul le cas des Cours garde du sens surtout avec un PROFESSEUR/ADMIN,
    # mais on ne bloque pas plus que la creation normale ne le ferait deja.
    comptes_possibles = session.exec(
        select(Utilisateur).where(Utilisateur.id != utilisateur_id).order_by(Utilisateur.nom)
    ).all()

    return templates.TemplateResponse(
        request,
        "admin_supprimer_utilisateur.html",
        {
            "utilisateur": admin, "cible": cible,
            "cercles_info": cercles_info, "cours_info": cours_info,
            "comptes_possibles": comptes_possibles,
        },
    )


def _cascade_supprimer_cercle(session: Session, cercle_id: int) -> None:
    """Supprime definitivement un CercleEtude et tout son contenu propre
    (ordre = enfants avant parent, pour ne jamais laisser de cle
    etrangere orpheline)."""
    ids_messages = [
        m.id for m in session.exec(select(MessageCercle).where(MessageCercle.cercle_id == cercle_id)).all()
    ]
    if ids_messages:
        for signalement in session.exec(
            select(SignalementMessage).where(SignalementMessage.message_id.in_(ids_messages))
        ).all():
            session.delete(signalement)
    for message in session.exec(select(MessageCercle).where(MessageCercle.cercle_id == cercle_id)).all():
        if message.piece_jointe_chemin:
            supprimer_fichier(message.piece_jointe_chemin)
        session.delete(message)
    for demande in session.exec(
        select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.cercle_id == cercle_id)
    ).all():
        session.delete(demande)
    for membre in session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle_id)).all():
        session.delete(membre)
    cercle = session.get(CercleEtude, cercle_id)
    if cercle:
        session.delete(cercle)


def _cascade_supprimer_cours(session: Session, cours_id: int) -> None:
    """Supprime definitivement un Cours et tout son contenu propre
    (seances + tableau blanc + presences, devoirs + rendus, inscriptions)."""
    for seance in session.exec(select(Seance).where(Seance.cours_id == cours_id)).all():
        for evenement in session.exec(
            select(EvenementTableauBlanc).where(EvenementTableauBlanc.seance_id == seance.id)
        ).all():
            session.delete(evenement)
        for autorisation in session.exec(
            select(AutorisationEcritureTableau).where(AutorisationEcritureTableau.seance_id == seance.id)
        ).all():
            session.delete(autorisation)
        for presence in session.exec(
            select(PresenceSeance).where(PresenceSeance.seance_id == seance.id)
        ).all():
            session.delete(presence)
        session.delete(seance)

    for devoir in session.exec(select(Devoir).where(Devoir.cours_id == cours_id)).all():
        for rendu in session.exec(select(RenduDevoir).where(RenduDevoir.devoir_id == devoir.id)).all():
            if rendu.chemin_fichier:
                supprimer_fichier(rendu.chemin_fichier)
            session.delete(rendu)
        session.delete(devoir)

    for inscription in session.exec(select(InscriptionCours).where(InscriptionCours.cours_id == cours_id)).all():
        session.delete(inscription)

    cours = session.get(Cours, cours_id)
    if cours:
        session.delete(cours)


@router.post("/admin/utilisateurs/{utilisateur_id}/supprimer")
async def supprimer_utilisateur(
    request: Request,
    utilisateur_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Suppression DEFINITIVE et EN CASCADE d'un compte.

    Les espaces qu'il POSSEDE (Cercles crees, Cours animes) sont traites
    selon le choix fait sur la page de confirmation, recu ici via les
    champs de formulaire "cercle_{id}" et "cours_{id}" :
      - valeur "supprimer"          -> l'espace et tout son contenu propre
                                        sont effaces (voir les fonctions
                                        _cascade_supprimer_* ci-dessus) ;
      - valeur "reattribuer:<id>"   -> l'espace change juste de
                                        proprietaire (createur_id /
                                        professeur_id), rien d'autre n'est
                                        touche ; le nouveau proprietaire est
                                        ajoute comme membre s'il ne l'etait
                                        pas deja (cas des Cercles).
    Tout ce qui appartient PERSONNELLEMENT a la cible (et n'est possede
    par personne d'autre) est ensuite supprime pour de vrai : tentatives
    de quiz, sessions avec le tuteur IA, consultations de documents,
    codes de secours 2FA, adhesions/inscriptions dans les espaces des
    AUTRES, presences en classe, traces sur le tableau blanc, devoirs
    rendus (fichier compris), messages postes dans les cercles des
    autres, abonnement sponsor/etudiant.

    Ce que l'on NE cascade PAS jusqu'a la suppression, par choix
    deliberé pour ne pas casser l'historique d'AUTRES utilisateurs :
      - Document.uploader_id -> reattribue a l'admin qui supprime (le
        document reste consultable ; supprimer un document precis reste
        possible individuellement via /moderation) ;
      - AbonnementEtudiant.valide_par_admin_id et
        DemandeAdhesionCercle.traite_par_id (appartiennent a un AUTRE
        utilisateur) -> mis a None, la decision/l'historique reste mais
        sans plus referencer un compte supprime.

    Enfin la ligne Utilisateur elle-meme est supprimee — plus aucune
    reference vers utilisateur_id ne doit subsister a ce stade, sans
    quoi la suppression echouera sur une contrainte de cle etrangere
    (ce qui, dans ce cas, est volontairement une garde-fou : mieux vaut
    une erreur explicite qu'une ligne orpheline silencieuse)."""
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/", status_code=303)

    cible = session.get(Utilisateur, utilisateur_id)
    if not cible or cible.id == admin.id:
        return RedirectResponse("/admin/utilisateurs", status_code=303)

    formulaire = await request.form()
    donnees = formulaire

    # --- 1. Cercles possedes : reattribution ou suppression, au choix ---
    for cercle in session.exec(select(CercleEtude).where(CercleEtude.createur_id == utilisateur_id)).all():
        choix = donnees.get(f"cercle_{cercle.id}", "supprimer")
        if choix.startswith("reattribuer:"):
            nouveau_proprietaire_id = int(choix.split(":", 1)[1])
            cercle.createur_id = nouveau_proprietaire_id
            session.add(cercle)
            deja_membre = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == cercle.id,
                    MembreCercle.utilisateur_id == nouveau_proprietaire_id,
                )
            ).first()
            if not deja_membre:
                session.add(MembreCercle(cercle_id=cercle.id, utilisateur_id=nouveau_proprietaire_id))
        else:
            _cascade_supprimer_cercle(session, cercle.id)
    session.commit()

    # --- 2. Cours possedes : reattribution ou suppression, au choix ---
    for cours in session.exec(select(Cours).where(Cours.professeur_id == utilisateur_id)).all():
        choix = donnees.get(f"cours_{cours.id}", "supprimer")
        if choix.startswith("reattribuer:"):
            cours.professeur_id = int(choix.split(":", 1)[1])
            session.add(cours)
        else:
            _cascade_supprimer_cours(session, cours.id)
    session.commit()

    # --- 3. Contenu personnel de la cible dans les espaces des AUTRES ---
    for membre in session.exec(select(MembreCercle).where(MembreCercle.utilisateur_id == utilisateur_id)).all():
        session.delete(membre)
    for demande in session.exec(
        select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(demande)
    # Demandes traitees PAR la cible dans un cercle qu'elle ne possede
    # pas forcement : on garde la demande (historique du cercle), on
    # retire juste la reference au compte supprime.
    for demande_traitee in session.exec(
        select(DemandeAdhesionCercle).where(DemandeAdhesionCercle.traite_par_id == utilisateur_id)
    ).all():
        demande_traitee.traite_par_id = None
        session.add(demande_traitee)

    ids_messages_restants = [
        m.id for m in session.exec(select(MessageCercle).where(MessageCercle.auteur_id == utilisateur_id)).all()
    ]
    if ids_messages_restants:
        for signalement in session.exec(
            select(SignalementMessage).where(SignalementMessage.message_id.in_(ids_messages_restants))
        ).all():
            session.delete(signalement)
    for message in session.exec(select(MessageCercle).where(MessageCercle.auteur_id == utilisateur_id)).all():
        if message.piece_jointe_chemin:
            supprimer_fichier(message.piece_jointe_chemin)
        session.delete(message)
    for signalement_envoye in session.exec(
        select(SignalementMessage).where(SignalementMessage.signale_par_id == utilisateur_id)
    ).all():
        session.delete(signalement_envoye)

    for inscription in session.exec(
        select(InscriptionCours).where(InscriptionCours.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(inscription)
    for presence in session.exec(
        select(PresenceSeance).where(PresenceSeance.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(presence)
    for evenement in session.exec(
        select(EvenementTableauBlanc).where(EvenementTableauBlanc.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(evenement)
    for autorisation in session.exec(
        select(AutorisationEcritureTableau).where(AutorisationEcritureTableau.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(autorisation)
    for rendu in session.exec(select(RenduDevoir).where(RenduDevoir.utilisateur_id == utilisateur_id)).all():
        if rendu.chemin_fichier:
            supprimer_fichier(rendu.chemin_fichier)
        session.delete(rendu)

    ids_tentatives = [
        t.id for t in session.exec(select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur_id)).all()
    ]
    if ids_tentatives:
        for signalement_quiz in session.exec(
            select(SignalementQuestionQuiz).where(SignalementQuestionQuiz.tentative_id.in_(ids_tentatives))
        ).all():
            session.delete(signalement_quiz)
    for tentative in session.exec(select(TentativeQuiz).where(TentativeQuiz.utilisateur_id == utilisateur_id)).all():
        session.delete(tentative)
    for signalement_quiz_envoye in session.exec(
        select(SignalementQuestionQuiz).where(SignalementQuestionQuiz.signale_par_id == utilisateur_id)
    ).all():
        session.delete(signalement_quiz_envoye)

    for session_tuteur in session.exec(
        select(SessionTuteur).where(SessionTuteur.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(session_tuteur)
    for consultation in session.exec(
        select(ConsultationDocument).where(ConsultationDocument.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(consultation)
    for abonnement_sponsor in session.exec(
        select(Abonnement).where(Abonnement.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(abonnement_sponsor)
    for abonnement_etudiant in session.exec(
        select(AbonnementEtudiant).where(AbonnementEtudiant.utilisateur_id == utilisateur_id)
    ).all():
        session.delete(abonnement_etudiant)
    # Un admin AUTRE que la cible a pu valider l'abonnement de tiers ;
    # si c'est la cible elle-meme qui a valide des abonnements d'AUTRES
    # etudiants, on garde ces enregistrements (utiles a l'historique) et
    # on retire juste la reference au compte supprime.
    for abonnement_valide_par_cible in session.exec(
        select(AbonnementEtudiant).where(AbonnementEtudiant.valide_par_admin_id == utilisateur_id)
    ).all():
        abonnement_valide_par_cible.valide_par_admin_id = None
        session.add(abonnement_valide_par_cible)

    for code in session.exec(select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur_id)).all():
        session.delete(code)

    # Documents deposes par la cible : on ne les supprime pas (ce sont
    # des ressources utiles a d'autres etudiants) — reattribues a
    # l'admin qui effectue la suppression, comme un cercle/cours
    # "reattribuer" par defaut. Utiliser /moderation pour en supprimer
    # un precis si besoin.
    for document in session.exec(select(Document).where(Document.uploader_id == utilisateur_id)).all():
        document.uploader_id = admin.id
        session.add(document)

    session.commit()

    # --- 4. La ligne Utilisateur elle-meme, en tout dernier ---
    session.delete(cible)
    session.commit()

    return RedirectResponse("/admin/utilisateurs?supprime=1", status_code=303)
