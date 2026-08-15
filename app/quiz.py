"""
Logique metier du Quiz IA par theme (matiere/niveau/difficulte), separee
du router pour la meme raison que subscription.py et dashboard.py :
le router orchestre la requete HTTP, ce module sait generer/corriger un
quiz et calculer les statistiques.
"""
import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlmodel import Session, select

from .models import TentativeQuiz, Utilisateur, SignalementQuestionQuiz
from . import ai_quiz

from .referentiel import NIVEAUX  # centralise (voir app/referentiel.py) ; reexporte ici pour ne rien casser dans quiz_router.py qui importe quiz_module.NIVEAUX
DIFFICULTES = ["Facile", "Moyen", "Difficile"]
NB_QUESTIONS_POSSIBLES = [5, 10, 15, 20]


ESSAIS_MAX_GENERATION = 2


def _generer_quiz_confiant(matiere: str, niveau: str, difficulte: str, nb_questions: int) -> List[Dict]:
    """Genere un quiz et le fait verifier par l'IA (voir
    ai_quiz.verifier_et_corriger_questions). Si Groq n'est pas confiant
    sur la totalite des questions, on retente une generation COMPLETE
    depuis zero plutot que de livrer un quiz sur lequel l'IA elle-meme a
    des doutes — jusqu'a ESSAIS_MAX_GENERATION tentatives, pour ne
    jamais bloquer indefiniment l'etudiant. Si aucun essai n'aboutit a
    une confiance totale, on livre quand meme le dernier resultat verifie
    (un quiz relu vaut mieux qu'un quiz jamais livre)."""
    questions_verifiees: List[Dict] = []
    for _ in range(ESSAIS_MAX_GENERATION):
        questions_generees = ai_quiz.generer_quiz_par_theme(matiere, niveau, difficulte, nb_questions)
        questions_verifiees, confiant = ai_quiz.verifier_et_corriger_questions(questions_generees, matiere, niveau)
        if confiant:
            break
    return questions_verifiees


def creer_tentative(
    session: Session,
    utilisateur: Utilisateur,
    matiere: str,
    niveau: str,
    difficulte: str,
    nb_questions: int,
) -> TentativeQuiz:
    """Genere les questions via l'IA, les fait relire et auto-evaluer par
    un second appel IA (voir _generer_quiz_confiant), puis cree la
    tentative (pas encore repondue). Meme en cas d'echec de generation,
    on cree quand meme la tentative avec le message d'erreur comme
    unique 'question' — ca reste coherent avec le comportement existant,
    et evite un ecran d'erreur brut."""
    questions_verifiees = _generer_quiz_confiant(matiere, niveau, difficulte, nb_questions)

    tentative = TentativeQuiz(
        utilisateur_id=utilisateur.id,
        matiere=matiere,
        niveau=niveau,
        difficulte=difficulte,
        nb_questions=len(questions_verifiees),
        questions_json=json.dumps(questions_verifiees, ensure_ascii=False),
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


def signaler_question(
    session: Session, tentative_id: int, index_question: int, signale_par_id: int, motif: Optional[str] = None
) -> None:
    """Enregistre le signalement d'une question par un etudiant. Evite
    les doublons : un signalement non-traite deja existant de ce meme
    etudiant sur cette meme question n'est pas duplique."""
    deja_signale = session.exec(
        select(SignalementQuestionQuiz).where(
            SignalementQuestionQuiz.tentative_id == tentative_id,
            SignalementQuestionQuiz.index_question == index_question,
            SignalementQuestionQuiz.signale_par_id == signale_par_id,
            SignalementQuestionQuiz.traite == False,  # noqa: E712
        )
    ).first()
    if deja_signale:
        return

    session.add(SignalementQuestionQuiz(
        tentative_id=tentative_id,
        index_question=index_question,
        signale_par_id=signale_par_id,
        motif=motif,
    ))
    session.commit()


SECONDES_PAR_QUESTION_EXAMEN = 90
NB_QUESTIONS_EXAMEN = 10


def creer_tentative_examen(session: Session, utilisateur: Utilisateur, matiere: str, niveau: str, difficulte: str) -> TentativeQuiz:
    """Cree une tentative en 'mode examen' : memes garanties de qualite
    que creer_tentative() (verification IA, regeneration si pas confiant),
    mais marquee avec un chronometre. La matiere/niveau/difficulte sont
    deja tires au sort par l'appelant (voir quiz_router.py) — cette
    fonction se contente de creer le quiz et d'activer le mode examen."""
    tentative = creer_tentative(session, utilisateur, matiere, niveau, difficulte, NB_QUESTIONS_EXAMEN)
    tentative.mode_examen = True
    tentative.duree_secondes = NB_QUESTIONS_EXAMEN * SECONDES_PAR_QUESTION_EXAMEN
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def secondes_restantes_examen(tentative: TentativeQuiz) -> int:
    """Temps restant (en secondes, jamais negatif) avant la fin du
    chronometre d'un quiz en mode examen. Calcule cote serveur (pas
    seulement cote client) pour eviter qu'un etudiant ne triche en
    modifiant l'horloge de son navigateur — le compte a rebours affiche
    est indicatif, mais rien n'empeche de soumettre apres l'expiration
    cote serveur si on voulait un jour l'imposer strictement."""
    if not tentative.mode_examen or not tentative.duree_secondes:
        return 0
    ecoule = (datetime.utcnow() - tentative.date_creation).total_seconds()
    return max(0, int(tentative.duree_secondes - ecoule))
