from datetime import datetime, timedelta

from app.models import ProgressionNotion, TentativeQuiz
from app.quiz import (
    mettre_a_jour_progression_notion,
    notions_a_revoir,
    plan_revision_du_jour,
    difficulte_revision_adaptative,
)
from app.quiz_validation import valider_questions


class FakeResult:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values[0] if self.values else None

    def all(self):
        return list(self.values)


class FakeSession:
    def __init__(self):
        self.objects = []

    def exec(self, _query):
        progressions = [obj for obj in self.objects if isinstance(obj, ProgressionNotion)]
        return FakeResult(progressions)

    def add(self, obj):
        if obj not in self.objects:
            self.objects.append(obj)

    def commit(self):
        return None


def _tentative():
    return TentativeQuiz(
        id=10,
        utilisateur_id=7,
        matiere="Français",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=2,
        questions_json="[]",
    )


def _questions():
    return valider_questions(
        [
            {
                "question": "Quelle forme est correcte ?",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 0,
                "explication": "La forme A est correcte.",
                "notion": "Concordance des temps",
            },
            {
                "question": "Quelle règle applique-t-on ?",
                "choix": ["A", "B", "C"],
                "index_bonne_reponse": 1,
                "explication": "La règle B s'applique ici.",
                "notion": "Concordance des temps",
            },
        ],
        expected_count=2,
    )


def test_une_erreur_cree_une_progression_par_notion():
    session = FakeSession()

    mettre_a_jour_progression_notion(
        session,
        _tentative(),
        _questions(),
        [0, 0],
    )

    progression = session.objects[0]
    assert progression.matiere == "Français"
    assert progression.notion == "Concordance des temps"
    assert progression.nb_questions == 2
    assert progression.nb_reussites == 1
    assert progression.nb_erreurs == 1
    assert progression.derniere_erreur_le is not None
    assert progression.score_maitrise == 46
    assert progression.nb_revisions == 1
    assert progression.prochaine_revision_le is not None
    assert progression.prochaine_revision_le > datetime.utcnow() + timedelta(hours=23)


def test_une_notion_fragile_est_priorisee():
    session = FakeSession()
    maintenant = datetime.utcnow()
    faible = ProgressionNotion(
        id=1,
        utilisateur_id=7,
        matiere="Mathématiques",
        notion="Dérivées",
        niveau="L1",
        nb_questions=5,
        nb_reussites=1,
        nb_erreurs=4,
        date_maj=maintenant,
    )
    solide = ProgressionNotion(
        id=2,
        utilisateur_id=7,
        matiere="Français",
        notion="Concordance des temps",
        niveau="L1",
        nb_questions=5,
        nb_reussites=4,
        nb_erreurs=1,
        date_maj=maintenant,
    )
    session.objects.extend([solide, faible])

    resultats = notions_a_revoir(session, 7, limit=2)

    assert [p.id for p in resultats] == [1, 2]


def test_plan_du_jour_priorise_une_revision_arrivee_a_echeance():
    session = FakeSession()
    maintenant = datetime.utcnow()
    due = ProgressionNotion(
        id=1,
        utilisateur_id=7,
        matiere="Mathématiques",
        notion="Dérivées",
        niveau="L1",
        nb_questions=10,
        nb_reussites=9,
        nb_erreurs=1,
        score_maitrise=88,
        serie_reussites=3,
        prochaine_revision_le=maintenant - timedelta(hours=1),
        date_maj=maintenant - timedelta(days=10),
    )
    faible_mais_pas_due = ProgressionNotion(
        id=2,
        utilisateur_id=7,
        matiere="Français",
        notion="Concordance des temps",
        niveau="L1",
        nb_questions=10,
        nb_reussites=4,
        nb_erreurs=6,
        score_maitrise=40,
        prochaine_revision_le=maintenant + timedelta(days=2),
        date_maj=maintenant,
    )
    session.objects.extend([faible_mais_pas_due, due])

    resultats = plan_revision_du_jour(session, 7, limit=2)

    assert [p.id for p in resultats] == [1, 2]


def test_difficulte_de_revision_s_adapte_a_la_maitrise():
    fragile = ProgressionNotion(score_maitrise=35)
    moyenne = ProgressionNotion(score_maitrise=62)
    solide = ProgressionNotion(score_maitrise=86)

    assert difficulte_revision_adaptative(fragile) == "Facile"
    assert difficulte_revision_adaptative(moyenne) == "Moyen"
    assert difficulte_revision_adaptative(solide) == "Difficile"
    assert difficulte_revision_adaptative(None) == "Moyen"


def test_diagnostic_examen_donne_un_bilan_actionnable():
    from app.quiz import diagnostic_examen

    maintenant = datetime.utcnow()
    tentative = TentativeQuiz(
        utilisateur_id=7,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=10,
        questions_json="[]",
        score=6,
        mode_examen=True,
        duree_secondes=900,
        date_creation=maintenant - timedelta(minutes=8, seconds=20),
        date_soumission=maintenant,
    )

    diagnostic = diagnostic_examen(tentative, nb_erreurs=4, nb_notions_faibles=2)

    assert diagnostic["pourcentage"] == 60
    assert diagnostic["niveau"] == "en_consolidation"
    assert diagnostic["nb_erreurs"] == 4
    assert diagnostic["nb_notions_faibles"] == 2
    assert diagnostic["temps_utilise_secondes"] == 500
    assert diagnostic["temps_affiche"] == "8 min 20 s"
    assert diagnostic["temps_moyen_question_secondes"] == 50


def test_diagnostic_examen_borne_le_temps_a_la_duree():
    from app.quiz import diagnostic_examen

    maintenant = datetime.utcnow()
    tentative = TentativeQuiz(
        utilisateur_id=7,
        matiere="Droit",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=10,
        questions_json="[]",
        score=9,
        mode_examen=True,
        duree_secondes=900,
        date_creation=maintenant - timedelta(minutes=30),
        date_soumission=maintenant,
    )

    diagnostic = diagnostic_examen(tentative, nb_erreurs=1, nb_notions_faibles=1)

    assert diagnostic["temps_utilise_secondes"] == 900
