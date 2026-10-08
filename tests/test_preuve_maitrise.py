from sqlmodel import Session, SQLModel, create_engine, select

from app.models import ProgressionNotion, TentativeQuiz, Utilisateur
from app.quiz import (
    besoin_preuve_maitrise,
    diagnostiquer_maitrise,
    mettre_a_jour_progression_notion,
)


def _question():
    return {
        "question": "Calcule.",
        "choix": ["4", "5", "6"],
        "index_bonne_reponse": 0,
        "explication": "Le résultat est 4.",
        "notion": "Déterminant d'ordre 2",
        "difficulte": "Moyen",
    }


def _tentative(utilisateur_id: int, numero: int) -> TentativeQuiz:
    return TentativeQuiz(
        id=numero,
        utilisateur_id=utilisateur_id,
        matiere="Mathématiques",
        niveau="L1",
        difficulte="Moyen",
        nb_questions=3,
        questions_json="[]",
    )


def test_diagnostic_maitrise_explique_les_preuves_manquantes():
    progression = ProgressionNotion(
        utilisateur_id=1,
        matiere="Mathématiques",
        notion="Matrices",
        score_maitrise=76,
        nb_questions=5,
        nb_revisions=1,
        serie_reussites=2,
        niveau_max_reussi="Facile",
    )

    diagnostic = diagnostiquer_maitrise(progression)

    assert diagnostic["statut"] == "construction"
    assert diagnostic["maitrise_confirmee"] is False
    assert diagnostic["action"] == "Quiz ciblé"
    assert diagnostic["conditions"]["questions"] is False
    assert "avoir 3 séances différentes (1)" in diagnostic["conditions_manquantes"]


def test_trois_seances_et_neuf_reussites_produisent_une_maitrise_prouvee():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Preuve Master",
            telephone="690000200",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        questions = [_question(), _question(), _question()]
        for numero in range(1, 4):
            tentative = _tentative(utilisateur.id, numero)
            mettre_a_jour_progression_notion(
                session,
                tentative,
                questions,
                [0, 0, 0],
            )

        progression = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id == utilisateur.id
            )
        ).one()

        assert progression.nb_questions == 9
        assert progression.nb_revisions == 3
        assert progression.niveau_max_reussi == "Moyen"
        assert progression.maitrise_confirmee is True
        assert progression.derniere_preuve_le is not None
        assert progression.prochaine_preuve_le is not None
        assert progression.confiance_maitrise >= 95

        diagnostic = diagnostiquer_maitrise(progression)
        assert diagnostic["statut"] == "prouvee"
        assert diagnostic["conditions_manquantes"] == []


def test_une_nouvelle_erreur_invalide_une_preuve_precedente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        utilisateur = Utilisateur(
            nom="Preuve Revalidation",
            telephone="690000201",
            mot_de_passe_hash="hash",
        )
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)

        questions = [_question(), _question(), _question()]
        for numero in range(1, 4):
            mettre_a_jour_progression_notion(
                session,
                _tentative(utilisateur.id, numero),
                questions,
                [0, 0, 0],
            )

        progression = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id == utilisateur.id
            )
        ).one()
        assert progression.maitrise_confirmee is True

        mettre_a_jour_progression_notion(
            session,
            _tentative(utilisateur.id, 4),
            [questions[0]],
            [1],
        )

        session.refresh(progression)
        assert progression.maitrise_confirmee is False
        assert progression.prochaine_preuve_le is not None
        diagnostic = diagnostiquer_maitrise(progression)
        assert diagnostic["statut"] == "a_confirmer"
        assert besoin_preuve_maitrise(progression) is True
