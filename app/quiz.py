"""
Logique metier du Quiz IA par theme (matiere/niveau/difficulte), separee
du router pour la meme raison que subscription.py et dashboard.py :
le router orchestre la requete HTTP, ce module sait generer/corriger un
quiz et calculer les statistiques.
"""
import json
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

from .models import TentativeQuiz, Utilisateur
from . import ai_quiz

NIVEAUX = ["L1", "L2", "L3", "M1", "M2"]
DIFFICULTES = ["Facile", "Moyen", "Difficile"]
NB_QUESTIONS_POSSIBLES = [5, 10, 15, 20]


def creer_tentative(
    session: Session,
    utilisateur: Utilisateur,
    matiere: str,
    niveau: str,
    difficulte: str,
    nb_questions: int,
) -> TentativeQuiz:
    """Genere les questions via l'IA et cree la tentative (pas encore
    repondue). Meme en cas d'echec de generation, on cree quand meme la
    tentative avec le message d'erreur comme unique 'question' — ca reste
    coherent avec le comportement existant de generer_quiz_depuis_texte,
    et evite un ecran d'erreur brut."""
    questions = ai_quiz.generer_quiz_par_theme(matiere, niveau, difficulte, nb_questions)

    tentative = TentativeQuiz(
        utilisateur_id=utilisateur.id,
        matiere=matiere,
        niveau=niveau,
        difficulte=difficulte,
        nb_questions=len(questions),
        questions_json=json.dumps(questions, ensure_ascii=False),
    )
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def questions(tentative: TentativeQuiz) -> List[dict]:
    return json.loads(tentative.questions_json)


def reponses(tentative: TentativeQuiz) -> Optional[List[Optional[int]]]:
    if not tentative.reponses_json:
        return None
    return json.loads(tentative.reponses_json)


def corriger(session: Session, tentative: TentativeQuiz, reponses_soumises: List[Optional[int]]) -> TentativeQuiz:
    """Calcule le score en comparant les reponses soumises aux bonnes
    reponses, et fige la tentative (elle devient un resultat d'historique
    consultable, plus modifiable)."""
    qs = questions(tentative)
    score = sum(
        1
        for i, q in enumerate(qs)
        if i < len(reponses_soumises) and reponses_soumises[i] == q.get("index_bonne_reponse")
    )
    tentative.reponses_json = json.dumps(reponses_soumises)
    tentative.score = score
    tentative.date_soumission = datetime.utcnow()
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def historique(session: Session, utilisateur_id: int) -> List[TentativeQuiz]:
    """Tentatives terminees, les plus recentes d'abord."""
    return session.exec(
        select(TentativeQuiz)
        .where(TentativeQuiz.utilisateur_id == utilisateur_id, TentativeQuiz.date_soumission.is_not(None))
        .order_by(TentativeQuiz.date_soumission.desc())
    ).all()


def statistiques(tentatives_terminees: List[TentativeQuiz]) -> dict:
    """Stats simples calculees en Python sur l'historique deja charge —
    pas besoin d'une requete d'agregation SQL separee pour ces volumes."""
    if not tentatives_terminees:
        return {"nb_quiz": 0, "score_moyen_pourcent": 0, "meilleure_matiere": None}

    nb_quiz = len(tentatives_terminees)
    total_pourcent = sum(
        (t.score / t.nb_questions * 100) if t.nb_questions else 0 for t in tentatives_terminees
    )
    score_moyen = round(total_pourcent / nb_quiz)

    par_matiere: dict = {}
    for t in tentatives_terminees:
        par_matiere.setdefault(t.matiere, []).append((t.score / t.nb_questions * 100) if t.nb_questions else 0)
    moyennes_matieres = {m: sum(v) / len(v) for m, v in par_matiere.items()}
    meilleure_matiere = max(moyennes_matieres, key=moyennes_matieres.get) if moyennes_matieres else None

    return {"nb_quiz": nb_quiz, "score_moyen_pourcent": score_moyen, "meilleure_matiere": meilleure_matiere}
