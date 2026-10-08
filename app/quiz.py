"""
Logique metier du Quiz IA par theme (matiere/niveau/difficulte), separee
du router pour la meme raison que subscription.py et dashboard.py :
le router orchestre la requete HTTP, ce module sait generer/corriger un
quiz et calculer les statistiques.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlmodel import Session, select

from .database import engine
from .models import TentativeQuiz, Utilisateur, SignalementQuestionQuiz, ProgressionNotion
from . import ai_quiz
from .quiz_validation import QuizValidationError, valider_questions
from .ia_transport import normaliser_structure_quiz
from .config import parametres

from .referentiel import NIVEAUX  # centralise (voir app/referentiel.py) ; reexporte ici pour ne rien casser dans quiz_router.py qui importe quiz_module.NIVEAUX

logger = logging.getLogger(__name__)

DIFFICULTES = ["Facile", "Moyen", "Difficile"]
NB_QUESTIONS_POSSIBLES = [5, 10, 15, 20]


LONGUEUR_MAX_MATIERE = 120


def valider_parametres(matiere: str, niveau: str, difficulte: str, nb_questions: int) -> str:
    matiere = (matiere or "").strip()
    if not matiere or len(matiere) > LONGUEUR_MAX_MATIERE:
        raise QuizValidationError(f"La matiere doit contenir entre 1 et {LONGUEUR_MAX_MATIERE} caracteres.")
    if niveau not in NIVEAUX:
        raise QuizValidationError("Niveau de quiz invalide.")
    if difficulte not in DIFFICULTES:
        raise QuizValidationError("Difficulte de quiz invalide.")
    if nb_questions not in NB_QUESTIONS_POSSIBLES:
        raise QuizValidationError("Nombre de questions invalide.")
    return matiere


def _generer_quiz_rapide(matiere: str, niveau: str, difficulte: str, nb_questions: int) -> List[Dict]:
    """Genere le quiz et ne fait sur le chemin utilisateur que la validation locale.

    La relecture multi-modeles reste utile pour la qualite et la memoire de
    l'ensemble, mais elle est lancee en arriere-plan apres l'envoi de la
    reponse HTTP. Un etudiant ne doit jamais attendre Qwen + Gemini + arbitre
    pour commencer son quiz."""
    questions_generees = ai_quiz.generer_quiz_par_theme(
        matiere,
        niveau,
        difficulte,
        nb_questions,
    )
    return valider_questions(questions_generees, expected_count=nb_questions)


def _verifier_questions_avant_stockage(
    questions: List[Dict],
    matiere: str,
    niveau: str,
) -> List[Dict]:
    """Applique une relecture multi-modeles avant de livrer le quiz.

    La verification en arriere-plan reste utile pour l'audit et la memoire,
    mais une correction qui change la bonne reponse après que l'etudiant a
    commencé le quiz est interdite. Le contrôle qualité doit donc avoir lieu
    avant le commit de la tentative.
    """
    questions = valider_questions(questions, expected_count=len(questions), strict_coherence=True)
    try:
        questions_finales, confiant = ai_quiz.verifier_et_corriger_questions(
            questions,
            matiere,
            niveau,
            strategie="standard",
        )
        questions_finales = valider_questions(
            questions_finales,
            expected_count=len(questions),
            strict_coherence=True,
        )
        logger.info(
            "Quality gate quiz: matiere=%s niveau=%s questions=%s confiant=%s.",
            matiere,
            niveau,
            len(questions_finales),
            confiant,
        )
        if parametres.ai_ensemble_enabled and not confiant:
            raise QuizValidationError(
                "La vérification multi-modèles n'a pas confirmé le quiz."
            )
        return questions_finales
    except Exception as erreur:
        if parametres.ai_ensemble_enabled:
            logger.warning(
                "Quality gate quiz bloqué: le quiz ne sera pas publié: %s",
                erreur,
            )
            raise QuizValidationError(
                "La vérification qualité du quiz n'a pas pu être confirmée."
            ) from erreur

        logger.warning(
            "Quality gate quiz indisponible en mode sans ensemble; conservation locale: %s",
            erreur,
        )
        return questions


def creer_tentative(
    session: Session,
    utilisateur: Utilisateur,
    matiere: str,
    niveau: str,
    difficulte: str,
    nb_questions: int,
) -> TentativeQuiz:
    """Genere et publie rapidement un quiz après validation locale.

    La vérification multi-modèles est volontairement hors du chemin HTTP :
    la route met ensuite la tentative en file via ai_queue. Cela évite de
    faire attendre l'étudiant pendant les critiques/arbitrages Gemini/Groq.
    """
    matiere = valider_parametres(matiere, niveau, difficulte, nb_questions)
    derniere_erreur = None

    for essai in range(2):
        try:
            questions_generees = _generer_quiz_rapide(
                matiere,
                niveau,
                difficulte,
                nb_questions,
            )
            questions_validees = valider_questions(
                questions_generees,
                expected_count=nb_questions,
                strict_coherence=True,
            )
            if len(questions_validees) != nb_questions:
                raise QuizValidationError(
                    "Le nombre de questions générées est incorrect."
                )

            tentative = TentativeQuiz(
                utilisateur_id=utilisateur.id,
                matiere=matiere,
                niveau=niveau,
                difficulte=difficulte,
                nb_questions=len(questions_validees),
                questions_json=json.dumps(questions_validees, ensure_ascii=False),
            )
            session.add(tentative)
            session.commit()
            session.refresh(tentative)
            return tentative
        except QuizValidationError as erreur:
            derniere_erreur = erreur
            logger.warning(
                "Generation quiz rapide invalide (essai %s/2): %s",
                essai + 1,
                erreur,
            )

    raise QuizValidationError(
        "Impossible de générer un quiz conforme après deux tentatives."
    ) from derniere_erreur

def _questions_brutes(tentative: TentativeQuiz) -> tuple[List[dict], bool]:
    """Lit les deux formats de stockage : liste historique ou paquet adaptatif."""
    donnees = json.loads(tentative.questions_json)
    if isinstance(donnees, dict):
        return list(donnees.get("questions") or []), bool(donnees.get("adaptatif"))
    return list(donnees or []), False


def est_quiz_adaptatif(tentative: TentativeQuiz) -> bool:
    """Indique si une tentative utilise la navigation adaptative question par question."""
    _, adaptatif = _questions_brutes(tentative)
    return adaptatif


def questions(tentative: TentativeQuiz) -> List[dict]:
    # MODIF : compatibilité durable avec les anciennes tentatives et avec toute
    # réponse historique qui aurait conservé les marqueurs de transport math.
    donnees, _ = _questions_brutes(tentative)
    donnees = normaliser_structure_quiz(donnees)
    return valider_questions(donnees, expected_count=tentative.nb_questions)


def _profil_difficultes_adaptatives(nb_questions: int, difficulte_base: str) -> List[str]:
    profils = {
        "Facile": ["Facile", "Facile", "Moyen", "Moyen", "Difficile"],
        "Moyen": ["Facile", "Moyen", "Moyen", "Difficile", "Difficile"],
        "Difficile": ["Moyen", "Moyen", "Difficile", "Difficile", "Difficile"],
    }
    profil = profils.get(difficulte_base, profils["Moyen"])
    return [profil[i % len(profil)] for i in range(max(1, nb_questions))]


def preparer_questions_adaptatives(
    questions_quiz: List[dict],
    difficulte_base: str,
) -> List[dict]:
    """Garantit un niveau individuel par question, sans modifier le contenu pédagogique."""
    niveaux = _profil_difficultes_adaptatives(len(questions_quiz), difficulte_base)
    resultat = []
    for index, question in enumerate(questions_quiz):
        item = dict(question)
        niveau = item.get("difficulte")
        if niveau not in DIFFICULTES:
            niveau = niveaux[index]
        item["difficulte"] = niveau
        resultat.append(item)
    return resultat


def reponses(tentative: TentativeQuiz) -> Optional[List[Optional[int]]]:
    if not tentative.reponses_json:
        return None
    donnees = json.loads(tentative.reponses_json)
    if isinstance(donnees, dict):
        return list(donnees.get("reponses") or [])
    return donnees


def etat_adaptatif(tentative: TentativeQuiz) -> dict:
    """Retourne l'état progressif sans casser les anciennes réponses en liste."""
    nb = tentative.nb_questions
    reponses_existantes = [None] * nb
    ordre: List[int] = []
    serie_reussites = 0
    if tentative.reponses_json:
        donnees = json.loads(tentative.reponses_json)
        if isinstance(donnees, dict):
            reponses_existantes[:nb] = list(donnees.get("reponses") or [])[:nb]
            ordre = [int(i) for i in (donnees.get("ordre") or [])]
            serie_reussites = int(donnees.get("serie_reussites") or 0)
        elif isinstance(donnees, list):
            reponses_existantes[:nb] = donnees[:nb]
    return {
        "reponses": reponses_existantes,
        "ordre": ordre,
        "serie_reussites": max(0, serie_reussites),
    }


def enregistrer_reponse_adaptative(
    session: Session,
    tentative: TentativeQuiz,
    index_question: int,
    reponse: Optional[int],
) -> dict:
    """Enregistre une réponse et choisit immédiatement la prochaine difficulté."""
    if not est_quiz_adaptatif(tentative):
        raise QuizValidationError("Cette tentative n'est pas adaptative.")
    if tentative.date_soumission is not None:
        raise QuizValidationError("Le quiz est déjà terminé.")

    questions_quiz = questions(tentative)
    if not 0 <= index_question < len(questions_quiz):
        raise QuizValidationError("Index de question invalide.")
    choix = questions_quiz[index_question].get("choix") or []
    if reponse is None or isinstance(reponse, bool) or not isinstance(reponse, int) or not 0 <= reponse < len(choix):
        raise QuizValidationError("Réponse adaptative invalide.")

    etat = etat_adaptatif(tentative)
    if etat["reponses"][index_question] is not None:
        raise QuizValidationError("Cette question a déjà été répondue.")

    etat["reponses"][index_question] = reponse
    etat["ordre"].append(index_question)

    correcte = reponse == questions_quiz[index_question].get("index_bonne_reponse")
    if correcte:
        etat["serie_reussites"] += 1
    else:
        etat["serie_reussites"] = 0

    niveau_courant = questions_quiz[index_question].get("difficulte", tentative.difficulte)
    niveau_courant = niveau_courant if niveau_courant in DIFFICULTES else "Moyen"
    index_niveau = DIFFICULTES.index(niveau_courant)

    if correcte and etat["serie_reussites"] >= 2:
        niveau_cible = min(len(DIFFICULTES) - 1, index_niveau + 1)
    elif not correcte:
        niveau_cible = max(0, index_niveau - 1)
    else:
        niveau_cible = index_niveau

    candidats = [
        i for i, rep in enumerate(etat["reponses"])
        if rep is None
    ]
    suivante = None
    if candidats:
        def cle(index: int):
            niveau = questions_quiz[index].get("difficulte", "Moyen")
            rang = DIFFICULTES.index(niveau) if niveau in DIFFICULTES else 1
            direction = -rang if niveau_cible > index_niveau else rang
            return (abs(rang - niveau_cible), direction, index)
        suivante = min(candidats, key=cle)

    tentative.reponses_json = json.dumps({
        "reponses": etat["reponses"],
        "ordre": etat["ordre"],
        "serie_reussites": etat["serie_reussites"],
    })
    session.add(tentative)
    session.commit()
    session.refresh(tentative)

    return {
        "correcte": correcte,
        "prochaine_question": suivante,
        "termine": suivante is None,
        "difficulte_suivante": (
            questions_quiz[suivante].get("difficulte", "Moyen")
            if suivante is not None else None
        ),
        "serie_reussites": etat["serie_reussites"],
        "repondues": sum(rep is not None for rep in etat["reponses"]),
        "total": len(questions_quiz),
    }


def _score_maitrise_effectif(progression: ProgressionNotion) -> int:
    """Retourne le score de maitrise, avec un repli compatible avec les
    anciennes lignes creees avant l'introduction du score persistant."""
    if progression.score_maitrise:
        return max(0, min(100, progression.score_maitrise))
    if progression.nb_questions:
        return max(
            0,
            min(100, round(progression.nb_reussites * 100 / progression.nb_questions)),
        )
    return 0


def revision_due(progression: ProgressionNotion, maintenant: Optional[datetime] = None) -> bool:
    """Indique si une notion doit etre revisee maintenant."""
    maintenant = maintenant or datetime.utcnow()
    return progression.prochaine_revision_le is None or progression.prochaine_revision_le <= maintenant


def _intervalle_revision_jours(
    score_maitrise: int,
    serie_reussites: int,
    echec_pendant_revision: bool,
) -> int:
    """Calcule le prochain intervalle de revision selon la maitrise observee."""
    if echec_pendant_revision or score_maitrise < 50:
        return 1
    if score_maitrise < 65:
        return 2
    if score_maitrise < 80:
        return 4
    if score_maitrise < 90:
        return 7
    if score_maitrise < 97:
        return 14
    # Une longue serie de reussites permet d'espacer jusqu'a 30 jours.
    return 30 if serie_reussites >= 3 else 14


NIVEAU_DIFFICULTE_RANG = {"Facile": 1, "Moyen": 2, "Difficile": 3}


def _rang_difficulte(niveau: Optional[str]) -> int:
    return NIVEAU_DIFFICULTE_RANG.get((niveau or "").strip(), 0)


def diagnostiquer_maitrise(progression: ProgressionNotion) -> dict:
    """Transforme les statistiques d'une notion en preuve lisible et actionnable.

    Une notion n'est pas dite « maîtrisée » sur un seul bon score : il faut
    une répétition sur plusieurs séances, une série de réussites et au moins
    une réussite à difficulté intermédiaire. Cette règle crée une preuve
    pédagogique explicable, plutôt qu'un simple pourcentage.
    """
    score = _score_maitrise_effectif(progression)
    questions = int(progression.nb_questions or 0)
    revisions = int(progression.nb_revisions or 0)
    serie = int(progression.serie_reussites or 0)
    rang_max = _rang_difficulte(progression.niveau_max_reussi)

    conditions = {
        "score": score >= 85,
        "questions": questions >= 8,
        "seances": revisions >= 3,
        "serie": serie >= 3,
        "difficulte": rang_max >= 2,
    }
    confirme = bool(progression.maitrise_confirmee or all(conditions.values()))

    if confirme:
        statut = "prouvee"
        libelle = "Maîtrise prouvée"
        action = "Révision espacée"
    elif score >= 75 and revisions >= 2:
        statut = "a_confirmer"
        libelle = "Prête pour une épreuve de maîtrise"
        action = "Épreuve de confirmation"
    elif score >= 50:
        statut = "construction"
        libelle = "En construction"
        action = "Quiz ciblé"
    else:
        statut = "fragile"
        libelle = "Notion fragile"
        action = "Tuteur IA"

    confiance = int(progression.confiance_maitrise or 0)
    if not confiance:
        confiance = min(
            100,
            max(
                score,
                score
                + min(revisions * 3, 9)
                + (10 if serie >= 3 else 0)
                + (8 if rang_max >= 2 else 0),
            ),
        )

    conditions_manquantes = []
    labels = {
        "score": f"atteindre 85 % de maîtrise ({score} %)",
        "questions": f"avoir 8 questions évaluées ({questions})",
        "seances": f"avoir 3 séances différentes ({revisions})",
        "serie": f"obtenir 3 réussites consécutives ({serie})",
        "difficulte": (
            f"réussir au moins Moyen (meilleur niveau : {progression.niveau_max_reussi or 'aucun'})"
        ),
    }
    for cle, ok in conditions.items():
        if not ok:
            conditions_manquantes.append(labels[cle])

    return {
        "statut": statut,
        "libelle": libelle,
        "action": action,
        "score": score,
        "confiance": confiance,
        "conditions": conditions,
        "conditions_manquantes": conditions_manquantes,
        "niveau_max_reussi": progression.niveau_max_reussi or "Aucun",
        "maitrise_confirmee": confirme,
        "prochaine_preuve_le": progression.prochaine_preuve_le,
    }


def besoin_preuve_maitrise(progression: ProgressionNotion) -> bool:
    """Autorise une épreuve ciblée même lorsque la révision n'est pas échue."""
    diagnostic = diagnostiquer_maitrise(progression)
    return diagnostic["statut"] == "a_confirmer" and not progression.maitrise_confirmee


def mettre_a_jour_progression_notion(
    session: Session,
    tentative: TentativeQuiz,
    questions_quiz: List[dict],
    reponses_soumises: List[Optional[int]],
) -> None:
    """Met a jour la memoire d'apprentissage apres un quiz termine et
    recalcule la prochaine revision de chaque notion rencontree."""
    maintenant = datetime.utcnow()
    progressions_touchees: Dict[int, ProgressionNotion] = {}
    echecs_pendant_revision = set()

    for index, question in enumerate(questions_quiz):
        notion = (question.get("notion") or "").strip()
        if not notion:
            notion = f"Notions générales — {tentative.matiere}"
        progression = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id == tentative.utilisateur_id,
                ProgressionNotion.matiere == tentative.matiere,
                ProgressionNotion.notion == notion,
            )
        ).first()
        if progression is None:
            progression = ProgressionNotion(
                utilisateur_id=tentative.utilisateur_id,
                matiere=tentative.matiere,
                notion=notion,
                niveau=tentative.niveau,
                score_maitrise=50,
            )
        elif not progression.score_maitrise and progression.nb_questions:
            progression.score_maitrise = _score_maitrise_effectif(progression)

        progression.niveau = tentative.niveau
        progression.nb_questions += 1
        correcte = (
            index < len(reponses_soumises)
            and reponses_soumises[index] is not None
            and reponses_soumises[index] == question.get("index_bonne_reponse")
        )
        if correcte:
            progression.nb_reussites += 1
            progression.serie_reussites += 1
            progression.score_maitrise = min(
                100,
                progression.score_maitrise
                + max(4, round((100 - progression.score_maitrise) * 0.18)),
            )
            niveau_question = question.get("difficulte") or tentative.difficulte
            if _rang_difficulte(niveau_question) > _rang_difficulte(progression.niveau_max_reussi):
                progression.niveau_max_reussi = niveau_question
            progression.derniere_reussite_le = maintenant
        else:
            progression.nb_erreurs += 1
            progression.serie_reussites = 0
            progression.score_maitrise = max(
                0,
                progression.score_maitrise
                - max(8, round(max(1, progression.score_maitrise) * 0.22)),
            )
            progression.derniere_erreur_le = maintenant
            echecs_pendant_revision.add(notion)
            # Une nouvelle erreur invalide la preuve précédente : la preuve
            # doit rester actuelle, pas seulement historique.
            progression.maitrise_confirmee = False
            progression.prochaine_preuve_le = maintenant + timedelta(days=1)

        progression.date_maj = maintenant
        progressions_touchees[id(progression)] = progression
        session.add(progression)

    for progression in progressions_touchees.values():
        progression.nb_revisions += 1
        progression.prochaine_revision_le = maintenant + timedelta(
            days=_intervalle_revision_jours(
                progression.score_maitrise,
                progression.serie_reussites,
                progression.notion in echecs_pendant_revision,
            )
        )

        diagnostic_avant_preuve = diagnostiquer_maitrise(progression)
        if diagnostic_avant_preuve["statut"] == "prouvee" and not progression.maitrise_confirmee:
            progression.maitrise_confirmee = True
            progression.derniere_preuve_le = maintenant
            progression.prochaine_preuve_le = maintenant + timedelta(
                days=30 if progression.score_maitrise >= 95 and progression.serie_reussites >= 5 else 14
            )

        progression.confiance_maitrise = diagnostic_avant_preuve["confiance"]
        if progression.maitrise_confirmee:
            progression.confiance_maitrise = max(
                progression.confiance_maitrise,
                min(100, progression.score_maitrise + 10),
            )

        session.add(progression)

    session.commit()


def plan_revision_du_jour(
    session: Session,
    utilisateur_id: int,
    limit: int = 8,
) -> List[ProgressionNotion]:
    """Construit automatiquement le plan du jour.

    Une notion est proposee si sa date de revision est echue ou si sa
    maitrise reste sous 75 %. Les revisions echues passent avant les
    notions faibles non echues, puis on priorise les scores les plus bas.
    """
    maintenant = datetime.utcnow()
    elements = session.exec(
        select(ProgressionNotion)
        .where(ProgressionNotion.utilisateur_id == utilisateur_id)
    ).all()

    elements = [
        p for p in elements
        if p.nb_questions > 0
        and (revision_due(p, maintenant) or _score_maitrise_effectif(p) < 75)
    ]
    elements.sort(
        key=lambda p: (
            0 if revision_due(p, maintenant) else 1,
            _score_maitrise_effectif(p),
            -(p.nb_erreurs),
            p.date_maj,
        )
    )
    return elements[:limit]


def notions_a_revoir(
    session: Session,
    utilisateur_id: int,
    limit: int = 8,
) -> List[ProgressionNotion]:
    """Compatibilite historique : les anciennes vues utilisent ce nom pour
    afficher le plan de revision personnalise du jour."""
    return plan_revision_du_jour(session, utilisateur_id, limit=limit)


def corriger(session: Session, tentative: TentativeQuiz, reponses_soumises: List[Optional[int]]) -> TentativeQuiz:
    """Calcule le score en comparant les reponses soumises aux bonnes
    reponses, et fige la tentative (elle devient un resultat d'historique
    consultable, plus modifiable)."""
    qs = questions(tentative)
    if len(reponses_soumises) != len(qs):
        raise QuizValidationError("Le nombre de reponses ne correspond pas au quiz.")
    for index, reponse in enumerate(reponses_soumises):
        if reponse is not None and (isinstance(reponse, bool) or not isinstance(reponse, int) or reponse < 0 or reponse >= len(qs[index]["choix"])):
            raise QuizValidationError("Une reponse de quiz est invalide.")
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
    mettre_a_jour_progression_notion(session, tentative, qs, reponses_soumises)
    return tentative


def difficulte_revision_adaptative(progression: Optional[ProgressionNotion]) -> str:
    """Choisit une difficulté de révision selon la maîtrise actuelle.

    Fragile -> facile pour reconstruire les bases, intermédiaire -> moyen,
    solide -> difficile pour éviter de plafonner à une suite d'exercices trop
    simples.
    """
    if progression is None:
        return "Moyen"
    score = _score_maitrise_effectif(progression)
    if score < 50:
        return "Facile"
    if score < 75:
        return "Moyen"
    return "Difficile"


def creer_tentative_ciblee(
    session: Session,
    utilisateur: Utilisateur,
    matiere: str,
    niveau: str,
    notion: str,
    nb_questions: int = 5,
    progression: Optional[ProgressionNotion] = None,
) -> TentativeQuiz:
    """Construit un quiz court centre sur une faiblesse avec difficulté adaptative."""
    if progression is not None and progression.utilisateur_id != utilisateur.id:
        progression = None

    difficulte_ciblee = difficulte_revision_adaptative(progression)

    matiere = valider_parametres(matiere, niveau, difficulte_ciblee, nb_questions)
    notion = (notion or "").strip()[:100]
    if not notion:
        raise QuizValidationError("La notion ciblee est obligatoire.")
    questions_ciblees = ai_quiz.generer_quiz_cible(
        matiere,
        niveau,
        notion,
        nb_questions,
        difficulte=difficulte_ciblee,
    )
    questions_ciblees = valider_questions(
        questions_ciblees,
        expected_count=nb_questions,
        strict_coherence=True,
    )
    questions_ciblees = preparer_questions_adaptatives(
        questions_ciblees,
        difficulte_ciblee,
    )
    tentative = TentativeQuiz(
        utilisateur_id=utilisateur.id,
        matiere=matiere,
        niveau=niveau,
        difficulte=difficulte_ciblee,
        nb_questions=len(questions_ciblees),
        questions_json=json.dumps(
            {"questions": questions_ciblees, "adaptatif": True},
            ensure_ascii=False,
        ),
    )
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def verifier_tentative_en_arriere_plan(tentative_id: int, strategie: Optional[str] = None) -> None:
    """Relit un quiz apres sa livraison, sans modifier le quiz affiche.

    Cette tache conserve la securite du pipeline multi-modeles (critiques,
    arbitrage si necessaire, memoire des erreurs) mais ne bloque plus la
    requete HTTP qui doit seulement permettre a l'etudiant de commencer.
    """
    try:
        from .models import TentativeQuiz as _TentativeQuiz

        with Session(engine) as session:
            tentative = session.get(_TentativeQuiz, tentative_id)
            if not tentative:
                return
            try:
                questions_tentative = questions(tentative)
            except (ValueError, QuizValidationError):
                logger.warning(
                    "Verification arriere-plan ignoree pour le quiz #%s: questions invalides.",
                    tentative_id,
                )
                return

            questions_finales, confiant = ai_quiz.verifier_et_corriger_questions(
                questions_tentative,
                tentative.matiere,
                tentative.niveau,
                strategie=strategie or "standard",
            )
            try:
                valider_questions(
                    questions_finales,
                    expected_count=len(questions_tentative),
                )
            except QuizValidationError:
                logger.warning(
                    "Verification arriere-plan invalide pour le quiz #%s; quiz utilisateur conserve.",
                    tentative_id,
                )
                return

            logger.info(
                "Verification arriere-plan quiz #%s terminee: strategie=%s confiant=%s.",
                tentative_id,
                strategie or "standard",
                confiant,
            )
    except Exception:
        logger.exception(
            "Erreur pendant la verification arriere-plan du quiz #%s.",
            tentative_id,
        )


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
    """Cree une tentative en 'mode examen' : meme generation rapide et
    validation locale que creer_tentative(), mais marquee avec un
    chronometre. La relecture multi-modeles est placee ensuite dans la file
    IA dediee par le router. La matiere/niveau/difficulte sont deja tires au
    sort par l'appelant (voir quiz_router.py)."""
    tentative = creer_tentative(session, utilisateur, matiere, niveau, difficulte, NB_QUESTIONS_EXAMEN)
    tentative.mode_examen = True
    tentative.duree_secondes = NB_QUESTIONS_EXAMEN * SECONDES_PAR_QUESTION_EXAMEN
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def temps_utilise_examen(tentative: TentativeQuiz) -> int:
    """Retourne le temps écoulé entre le début et la soumission d'un examen."""
    if not tentative.mode_examen:
        return 0
    fin = tentative.date_soumission or datetime.utcnow()
    debut = tentative.date_creation
    duree = max(0, int((fin - debut).total_seconds()))
    if tentative.duree_secondes:
        return min(duree, tentative.duree_secondes)
    return duree


def diagnostic_examen(
    tentative: TentativeQuiz,
    nb_erreurs: int,
    nb_notions_faibles: int,
) -> dict:
    """Produit un diagnostic simple et actionnable après un examen blanc."""
    pourcentage = round(
        tentative.score * 100 / tentative.nb_questions
    ) if tentative.nb_questions else 0
    if pourcentage >= 80:
        niveau = "solide"
        message = "Très bon niveau. Utilise maintenant les notions faibles pour gagner encore en précision."
    elif pourcentage >= 60:
        niveau = "en_consolidation"
        message = "Les bases sont là, mais certaines notions doivent encore être consolidées avant un examen réel."
    else:
        niveau = "priorite"
        message = "Le plus rentable est de travailler d'abord tes notions les plus faibles avant de refaire un examen complet."

    temps = temps_utilise_examen(tentative)
    minutes, secondes = divmod(temps, 60)
    temps_affiche = f"{minutes} min" if secondes == 0 else f"{minutes} min {secondes:02d} s"
    moyenne = round(temps / tentative.nb_questions) if tentative.nb_questions else 0

    return {
        "pourcentage": pourcentage,
        "niveau": niveau,
        "message": message,
        "nb_erreurs": nb_erreurs,
        "nb_notions_faibles": nb_notions_faibles,
        "temps_utilise_secondes": temps,
        "temps_affiche": temps_affiche,
        "temps_moyen_question_secondes": moyenne,
    }


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
