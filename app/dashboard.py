"""
Agregation des donnees du tableau de bord etudiant. Separe du router pour
garder celui-ci fin (responsabilite unique : le router orchestre la
requete HTTP, ce module sait comment lire les donnees).
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select, func
from sqlalchemy import exists

from .models import (
    CercleEtude,
    MembreCercle,
    ConsultationDocument,
    Cours,
    Devoir,
    Document,
    InscriptionCours,
    RenduDevoir,
    StatutDocument,
    TentativeQuiz,
    Utilisateur,
)
from . import subscription

NB_DOCUMENTS_RECENTS = 5
NB_ACTIVITES_RECENTES = 5
NB_RESSOURCES_POPULAIRES = 4
NB_RECOMMANDATIONS = 4
NB_ECHEANCES = 4


def cercles_rejoints(session: Session, utilisateur_id: int) -> List[dict]:
    """Retourne uniquement les cercles visibles sur le dashboard (4 max)
    et leur nombre de membres, sans requête N+1."""
    membres = session.exec(
        select(MembreCercle, CercleEtude)
        .join(CercleEtude, MembreCercle.cercle_id == CercleEtude.id)
        .where(MembreCercle.utilisateur_id == utilisateur_id)
        .order_by(MembreCercle.date_adhesion.desc())
        .limit(4)
    ).all()

    if not membres:
        return []

    cercle_ids = [cercle.id for _, cercle in membres]
    comptes = {
        cercle_id: nb
        for cercle_id, nb in session.exec(
            select(MembreCercle.cercle_id, func.count(MembreCercle.id))
            .where(MembreCercle.cercle_id.in_(cercle_ids))
            .group_by(MembreCercle.cercle_id)
        ).all()
    }
    return [
        {
            "cercle": cercle,
            "date_adhesion": membre.date_adhesion,
            "nb_membres": int(comptes.get(cercle.id, 0)),
        }
        for membre, cercle in membres
    ]


def documents_consultes_recemment(session: Session, utilisateur_id: int) -> List[dict]:
    """Les 5 derniers documents distincts, calcules directement en SQL."""
    lignes = session.exec(
        select(
            ConsultationDocument.document_id,
            func.max(ConsultationDocument.date_consultation).label("date_consultation"),
        )
        .where(ConsultationDocument.utilisateur_id == utilisateur_id)
        .group_by(ConsultationDocument.document_id)
        .order_by(func.max(ConsultationDocument.date_consultation).desc())
        .limit(NB_DOCUMENTS_RECENTS)
    ).all()

    if not lignes:
        return []

    document_ids = [document_id for document_id, _ in lignes]
    documents = {
        doc.id: doc
        for doc in session.exec(select(Document).where(Document.id.in_(document_ids))).all()
    }
    return [
        {"document": documents[document_id], "date_consultation": date_consultation}
        for document_id, date_consultation in lignes
        if document_id in documents
    ]


def quiz_completes(session: Session, utilisateur_id: int) -> List[TentativeQuiz]:
    """Les 5 derniers quiz soumis uniquement : les compteurs et moyennes
    sont calcules séparément par SQL dans donnees_dashboard()."""
    return session.exec(
        select(TentativeQuiz)
        .where(TentativeQuiz.utilisateur_id == utilisateur_id)
        .where(TentativeQuiz.date_soumission != None)  # noqa: E711
        .order_by(TentativeQuiz.date_soumission.desc())
        .limit(max(NB_ACTIVITES_RECENTES, 5))
    ).all()


def quiz_stats(session: Session, utilisateur_id: int) -> tuple[int, int]:
    """Retourne count + score moyen sans charger le JSON des quiz."""
    total = session.exec(
        select(func.count())
        .select_from(TentativeQuiz)
        .where(TentativeQuiz.utilisateur_id == utilisateur_id)
        .where(TentativeQuiz.date_soumission != None)  # noqa: E711
    ).one()

    moyenne = session.exec(
        select(func.avg(TentativeQuiz.score * 100.0 / TentativeQuiz.nb_questions))
        .where(TentativeQuiz.utilisateur_id == utilisateur_id)
        .where(TentativeQuiz.date_soumission != None)  # noqa: E711
        .where(TentativeQuiz.score != None)  # noqa: E711
        .where(TentativeQuiz.nb_questions > 0)
    ).one()

    return int(total or 0), round(float(moyenne)) if moyenne is not None else 0


def jours_actifs_consecutifs(
    session: Session,
    utilisateur_id: int,
    tentatives_quiz: List[TentativeQuiz],
) -> int:
    """Calcule la regularite sans charger tous les champs des quiz.
    Les activites historiques sont bornees a 366 jours."""
    dates = {
        moment.date()
        for moment in session.exec(
            select(ConsultationDocument.date_consultation)
            .where(ConsultationDocument.utilisateur_id == utilisateur_id)
            .order_by(ConsultationDocument.date_consultation.desc())
            .limit(366)
        ).all()
    }
    dates.update(
        moment.date()
        for moment in session.exec(
            select(TentativeQuiz.date_soumission)
            .where(TentativeQuiz.utilisateur_id == utilisateur_id)
            .where(TentativeQuiz.date_soumission != None)  # noqa: E711
            .order_by(TentativeQuiz.date_soumission.desc())
            .limit(366)
        ).all()
        if moment
    )

    if not dates:
        return 0

    jour = datetime.utcnow().date()
    if jour not in dates:
        jour = max(dates)

    total = 0
    while jour in dates:
        total += 1
        jour -= timedelta(days=1)
    return total


def _delai_relatif(moment: datetime) -> str:
    """'il y a X minutes/heures/jours', pour affichage humain dans le
    fil d'activite."""
    ecart = datetime.utcnow() - moment
    secondes = ecart.total_seconds()
    if secondes < 60:
        return "a l'instant"
    minutes = int(secondes // 60)
    if minutes < 60:
        return f"il y a {minutes} min"
    heures = minutes // 60
    if heures < 24:
        return f"il y a {heures} h"
    jours = heures // 24
    return f"il y a {jours} j"


def activite_recente(
    session: Session,
    utilisateur_id: int,
    documents_recents: List[dict],
    tentatives_quiz: List[TentativeQuiz],
) -> List[dict]:
    """Fusionne les vraies sources d'activite deja disponibles
    (consultations de documents + quiz soumis), triees par date
    decroissante. Aucune activite n'est inventee : si aucune des deux
    sources n'a de donnees, la liste est vide et le template affiche un
    etat vide."""
    evenements = []
    for info in documents_recents:
        evenements.append({
            "type": "document",
            "titre": info["document"].titre,
            "detail": "Consulte",
            "date": info["date_consultation"],
        })
    for tentative in tentatives_quiz:
        evenements.append({
            "type": "quiz",
            "titre": f"Quiz — {tentative.matiere}",
            "detail": f"Score : {tentative.score}/{tentative.nb_questions}",
            "date": tentative.date_soumission,
        })
    evenements.sort(key=lambda e: e["date"], reverse=True)
    for e in evenements[:NB_ACTIVITES_RECENTES]:
        e["delai"] = _delai_relatif(e["date"])
    return evenements[:NB_ACTIVITES_RECENTES]


def ressources_populaires(session: Session, utilisateur: Utilisateur) -> List[Document]:
    """Documents approuves les plus telecharges (Document.nb_telechargements,
    deja incremente a chaque telechargement reel -- voir
    documents_router.py, aucun compteur invente ici). Priorite a la
    filiere de l'etudiant ; complete avec les documents populaires
    toutes filieres si besoin (filiere non renseignee, ou pas assez de
    documents populaires dans sa propre filiere)."""
    requete_base = select(Document).where(Document.statut == StatutDocument.APPROUVE)

    resultats: List[Document] = []
    if utilisateur.filiere_id:
        resultats = list(
            session.exec(
                requete_base.where(Document.filiere_id == utilisateur.filiere_id)
                .order_by(Document.nb_telechargements.desc())
                .limit(NB_RESSOURCES_POPULAIRES)
            ).all()
        )

    if len(resultats) < NB_RESSOURCES_POPULAIRES:
        deja_vus = {d.id for d in resultats}
        complement = session.exec(
            requete_base.order_by(Document.nb_telechargements.desc()).limit(
                NB_RESSOURCES_POPULAIRES + len(deja_vus)
            )
        ).all()
        for document in complement:
            if document.id in deja_vus:
                continue
            resultats.append(document)
            if len(resultats) >= NB_RESSOURCES_POPULAIRES:
                break

    return resultats[:NB_RESSOURCES_POPULAIRES]


def recommandations(session: Session, utilisateur: Utilisateur) -> List[Document]:
    """4 documents recents non consultes, selectionnes directement en SQL."""
    if not utilisateur.filiere_id:
        return []

    sous_requete = select(ConsultationDocument.document_id).where(
        ConsultationDocument.utilisateur_id == utilisateur.id
    )
    return list(
        session.exec(
            select(Document)
            .where(Document.statut == StatutDocument.APPROUVE)
            .where(Document.filiere_id == utilisateur.filiere_id)
            .where(~Document.id.in_(sous_requete))
            .order_by(Document.date_upload.desc())
            .limit(NB_RECOMMANDATIONS)
        ).all()
    )


def echeances_a_venir(session: Session, utilisateur_id: int) -> List[dict]:
    """4 devoirs a venir non rendus, sans N+1."""
    maintenant = datetime.utcnow()
    lignes = session.exec(
        select(Devoir, Cours)
        .join(InscriptionCours, InscriptionCours.cours_id == Devoir.cours_id)
        .join(Cours, Cours.id == Devoir.cours_id)
        .where(InscriptionCours.utilisateur_id == utilisateur_id)
        .where(Devoir.date_limite != None)  # noqa: E711
        .where(Devoir.date_limite > maintenant)
        .where(
            ~exists().where(
                (RenduDevoir.devoir_id == Devoir.id)
                & (RenduDevoir.utilisateur_id == utilisateur_id)
            )
        )
        .order_by(Devoir.date_limite.asc())
        .limit(NB_ECHEANCES)
    ).all()
    return [{"devoir": devoir, "cours": cours} for devoir, cours in lignes]


def donnees_dashboard(session: Session, utilisateur: Utilisateur) -> dict:
    """Agregation compacte du dashboard : peu de lignes SQL, pas de N+1,
    et aucun chargement massif des historiques/JSON."""
    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if abonnement:
        abonnement = subscription.synchroniser_expiration(session, abonnement)

    cercles = cercles_rejoints(session, utilisateur.id)
    documents = documents_consultes_recemment(session, utilisateur.id)
    tentatives = quiz_completes(session, utilisateur.id)
    tentative_en_cours = quiz_en_cours(session, utilisateur.id)

    nb_quiz_completes, score_moyen_quiz = quiz_stats(session, utilisateur.id)

    nb_documents_consultes = session.exec(
        select(func.count())
        .select_from(ConsultationDocument)
        .where(ConsultationDocument.utilisateur_id == utilisateur.id)
    ).one()

    nb_cercles_rejoints = session.exec(
        select(func.count())
        .select_from(MembreCercle)
        .where(MembreCercle.utilisateur_id == utilisateur.id)
    ).one()

    dernier_document: Optional[dict] = documents[0] if documents else None
    dernier_quiz: Optional[TentativeQuiz] = tentatives[0] if tentatives else None
    streak_jours = jours_actifs_consecutifs(session, utilisateur.id, tentatives)

    return {
        "abonnement": abonnement,
        "acces_premium": subscription.acces_premium_valide(abonnement),
        "jours_restants": subscription.jours_restants(abonnement),
        "cercles": cercles,
        "documents_recents": documents,
        "dernier_document": dernier_document,
        "dernier_document_delai": _delai_relatif(dernier_document["date_consultation"]) if dernier_document else None,
        "nb_cercles_rejoints": int(nb_cercles_rejoints or 0),
        "nb_documents_consultes": int(nb_documents_consultes or 0),
        "nb_quiz_completes": nb_quiz_completes,
        "dernier_quiz": dernier_quiz,
        "tentative_quiz_en_cours": tentative_en_cours,
        "score_moyen_quiz": score_moyen_quiz,
        "jours_actifs_consecutifs": streak_jours,
        "activite_recente": activite_recente(session, utilisateur.id, documents, tentatives),
        "ressources_populaires": ressources_populaires(session, utilisateur),
        "recommandations": recommandations(session, utilisateur),
        "echeances_a_venir": echeances_a_venir(session, utilisateur.id),
    }
