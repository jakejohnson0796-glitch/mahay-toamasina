"""
Agregation des donnees du tableau de bord etudiant. Separe du router pour
garder celui-ci fin (responsabilite unique : le router orchestre la
requete HTTP, ce module sait comment lire les donnees).
"""
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

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
    """Cercles dont l'etudiant est membre, les plus recemment rejoints
    d'abord, avec le nombre reel de membres de chaque cercle (donnee
    deja en base, jamais remontee jusqu'ici)."""
    resultats = session.exec(
        select(MembreCercle, CercleEtude)
        .join(CercleEtude, MembreCercle.cercle_id == CercleEtude.id)
        .where(MembreCercle.utilisateur_id == utilisateur_id)
        .order_by(MembreCercle.date_adhesion.desc())
    ).all()

    infos = []
    for membre, cercle in resultats:
        nb_membres = len(
            session.exec(select(MembreCercle).where(MembreCercle.cercle_id == cercle.id)).all()
        )
        infos.append({"cercle": cercle, "date_adhesion": membre.date_adhesion, "nb_membres": nb_membres})
    return infos


def documents_consultes_recemment(session: Session, utilisateur_id: int) -> List[dict]:
    """Les derniers documents consultes par l'etudiant, un seul par
    document (la consultation la plus recente), les plus recents
    d'abord."""
    consultations = session.exec(
        select(ConsultationDocument)
        .where(ConsultationDocument.utilisateur_id == utilisateur_id)
        .order_by(ConsultationDocument.date_consultation.desc())
    ).all()

    vus = set()
    resultats = []
    for c in consultations:
        if c.document_id in vus:
            continue
        vus.add(c.document_id)
        document = session.get(Document, c.document_id)
        if document:
            resultats.append({"document": document, "date_consultation": c.date_consultation})
        if len(resultats) >= NB_DOCUMENTS_RECENTS:
            break
    return resultats


def quiz_completes(session: Session, utilisateur_id: int) -> List[TentativeQuiz]:
    """Tentatives de quiz deja soumises (score != None), les plus
    recentes d'abord."""
    return session.exec(
        select(TentativeQuiz)
        .where(TentativeQuiz.utilisateur_id == utilisateur_id)
        .where(TentativeQuiz.date_soumission != None)  # noqa: E711 (SQLAlchemy exige != None, pas "is not None")
        .order_by(TentativeQuiz.date_soumission.desc())
    ).all()


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
    """Documents approuves de la filiere de l'etudiant qu'il n'a pas
    encore consultes (jamais telecharges par lui, toutes consultations
    confondues -- pas seulement les NB_DOCUMENTS_RECENTS derniers).
    Rien d'invente : sans filiere renseignee, ou si tout est deja vu,
    la liste est simplement vide (etat vide cote template)."""
    if not utilisateur.filiere_id:
        return []

    ids_consultes = set(
        session.exec(
            select(ConsultationDocument.document_id).where(
                ConsultationDocument.utilisateur_id == utilisateur.id
            )
        ).all()
    )

    candidats = session.exec(
        select(Document)
        .where(Document.statut == StatutDocument.APPROUVE)
        .where(Document.filiere_id == utilisateur.filiere_id)
        .order_by(Document.date_upload.desc())
    ).all()

    return [d for d in candidats if d.id not in ids_consultes][:NB_RECOMMANDATIONS]


def echeances_a_venir(session: Session, utilisateur_id: int) -> List[dict]:
    """Devoirs a rendre (date_limite pas encore passee) pour les cours
    ou l'etudiant est inscrit, qu'il n'a pas encore rendus. C'est la
    SEULE source d'echeance reelle disponible aujourd'hui dans le
    modele de donnees : les seances de classe virtuelle n'ont pas de
    date planifiee a l'avance (Seance.date_debut_reelle n'est
    renseignee qu'au moment ou le professeur demarre reellement la
    session -- voir models.py), donc ce widget ne montre jamais de
    fausse seance a venir."""
    cours_ids = session.exec(
        select(InscriptionCours.cours_id).where(InscriptionCours.utilisateur_id == utilisateur_id)
    ).all()
    if not cours_ids:
        return []

    devoirs = session.exec(
        select(Devoir)
        .where(Devoir.cours_id.in_(cours_ids))
        .where(Devoir.date_limite != None)  # noqa: E711
        .where(Devoir.date_limite > datetime.utcnow())
        .order_by(Devoir.date_limite.asc())
    ).all()

    resultats = []
    for devoir in devoirs:
        deja_rendu = session.exec(
            select(RenduDevoir)
            .where(RenduDevoir.devoir_id == devoir.id)
            .where(RenduDevoir.utilisateur_id == utilisateur_id)
        ).first()
        if deja_rendu:
            continue
        cours = session.get(Cours, devoir.cours_id)
        if not cours:
            continue
        resultats.append({"devoir": devoir, "cours": cours})
        if len(resultats) >= NB_ECHEANCES:
            break
    return resultats


def donnees_dashboard(session: Session, utilisateur: Utilisateur) -> dict:
    """Tout ce qu'il faut pour afficher le tableau de bord etudiant en un
    seul appel depuis le router."""
    abonnement = subscription.obtenir_abonnement(session, utilisateur.id)
    if abonnement:
        abonnement = subscription.synchroniser_expiration(session, abonnement)

    cercles = cercles_rejoints(session, utilisateur.id)
    documents = documents_consultes_recemment(session, utilisateur.id)
    tentatives = quiz_completes(session, utilisateur.id)

    dernier_document: Optional[dict] = documents[0] if documents else None

    return {
        "abonnement": abonnement,
        "acces_premium": subscription.acces_premium_valide(abonnement),
        "jours_restants": subscription.jours_restants(abonnement),
        "cercles": cercles,
        "documents_recents": documents,
        "dernier_document": dernier_document,
        "dernier_document_delai": _delai_relatif(dernier_document["date_consultation"]) if dernier_document else None,
        "nb_cercles_rejoints": len(cercles),
        "nb_documents_consultes": len(
            session.exec(
                select(ConsultationDocument).where(ConsultationDocument.utilisateur_id == utilisateur.id)
            ).all()
        ),
        "nb_quiz_completes": len(tentatives),
        "activite_recente": activite_recente(session, utilisateur.id, documents, tentatives),
        "ressources_populaires": ressources_populaires(session, utilisateur),
        "recommandations": recommandations(session, utilisateur),
        "echeances_a_venir": echeances_a_venir(session, utilisateur.id),
    }
