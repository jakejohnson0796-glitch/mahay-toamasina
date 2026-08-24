"""
Donnees partagees entre /faq et /feedback.

Etape 13 du brief de refonte visuelle : les deux routes rendent
desormais la MEME interface fusionnee (aide_avis.html), chacune
affichant les deux colonnes cote a cote -- pas seulement celle qui lui
correspondait avant la fusion. Facteur commun ici plutot que duplique
dans faq_router.py ET feedback_router.py, pour n'avoir qu'un seul
endroit ou la regle de confidentialite absolue du brief est ecrite :

    "Afficher uniquement est_public == True. Ne jamais afficher un
    avis statut == MASQUE. Meme indirectement."

Les deux routers appellent ces fonctions ; aucun des deux ne
reconstruit sa propre requete sur Feedback.
"""
from typing import Optional

from sqlmodel import Session, select, func

from .models import (
    FAQ, CategorieFAQ, Feedback, ReponseFeedback, CategorieFeedback,
    StatutFeedback, Utilisateur,
)


def donnees_faq(session: Session, q: Optional[str], categorie: Optional[CategorieFAQ]):
    """Identique a l'ancienne requete de faq_router.py (comportement
    inchange, simplement deplacee ici pour etre appelee par les deux
    routers apres la fusion)."""
    requete = select(FAQ).where(FAQ.est_active == True)  # noqa: E712
    if categorie:
        requete = requete.where(FAQ.categorie == categorie)
    if q:
        motif = f"%{q.strip()}%"
        requete = requete.where((FAQ.question.ilike(motif)) | (FAQ.reponse.ilike(motif)))
    return session.exec(requete.order_by(FAQ.ordre_affichage, FAQ.id)).all()


def _prenom_public(nom: str) -> str:
    """Premier mot du champ `nom` (pas de champ prenom/pseudonyme
    separe dans Utilisateur). Utilise uniquement pour l'affichage
    public d'un avis quand l'utilisateur a explicitement choisi
    est_public=True."""
    return (nom or "").strip().split(" ")[0] or "Utilisateur"


def donnees_avis(session: Session, categorie: Optional[CategorieFeedback]):
    """Renvoie (avis_affiches, note_moyenne, total_avis).

    Regle de confidentialite ABSOLUE (section 19 du brief), appliquee
    ici une seule fois, dans les deux requetes ci-dessous (liste ET
    resume des notes) : uniquement est_public == True ET statut !=
    MASQUE -- jamais d'exception, jamais contournee par un parametre.
    Trie par categorie puis date pour permettre le "regroupement
    logique" demande par le brief (groupby cote template).
    """
    conditions = [Feedback.est_public == True, Feedback.statut != StatutFeedback.MASQUE]  # noqa: E712
    if categorie:
        conditions.append(Feedback.categorie == categorie)

    avis_publics = session.exec(
        select(Feedback).where(*conditions)
        .order_by(Feedback.categorie, Feedback.date_creation.desc())
        .limit(20)
    ).all()

    ids_avis = [a.id for a in avis_publics]
    reponses_par_feedback = {}
    if ids_avis:
        reponses = session.exec(
            select(ReponseFeedback).where(ReponseFeedback.feedback_id.in_(ids_avis))
        ).all()
        reponses_par_feedback = {r.feedback_id: r for r in reponses}

    avis_affiches = [
        {
            "feedback": a,
            "prenom": _prenom_public(session.get(Utilisateur, a.utilisateur_id).nom)
            if session.get(Utilisateur, a.utilisateur_id) else "Utilisateur",
            "reponse": reponses_par_feedback.get(a.id),
        }
        for a in avis_publics
    ]

    # Resume des notes (section 19 du brief) : moyenne calculee sur TOUS
    # les avis publics correspondant au filtre, pas seulement les 20
    # affiches -- memes conditions que ci-dessus (pas de limit ici),
    # donc la regle de confidentialite reste respectee a l'identique.
    total_avis, note_moyenne = session.exec(
        select(func.count(Feedback.id), func.avg(Feedback.note)).where(*conditions)
    ).first()

    return avis_affiches, (round(note_moyenne, 1) if note_moyenne else None), (total_avis or 0)
