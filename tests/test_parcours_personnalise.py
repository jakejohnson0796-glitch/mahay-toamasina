from datetime import datetime

from app.models import ProgressionNotion, TentativeQuiz
from app.quiz import (
    mettre_a_jour_progression_notion,
    notions_a_revoir,
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
