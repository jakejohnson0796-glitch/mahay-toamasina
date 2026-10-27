"""Tests de non-régression pour la diversité historique des quiz générés."""
import json

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import RoleUtilisateur, TentativeQuiz, Utilisateur
from app.quiz import _questions_vues_recemment


def _creer_utilisateur(session: Session, numero: int) -> Utilisateur:
    utilisateur = Utilisateur(
        nom=f"Étudiant test {numero}",
        telephone=f"+261340001{numero:03d}",
        mot_de_passe_hash=f"hash-{numero}",
        role=RoleUtilisateur.ETUDIANT,
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    return utilisateur


def _creer_tentative(
    session: Session,
    utilisateur_id: int,
    matiere: str,
    questions: list[dict],
    *,
    enveloppe: bool = False,
) -> TentativeQuiz:
    contenu = {"questions": questions} if enveloppe else questions
    tentative = TentativeQuiz(
        utilisateur_id=utilisateur_id,
        matiere=matiere,
        niveau="L1",
        difficulte="Moyen",
        nb_questions=len(questions),
        questions_json=json.dumps(contenu, ensure_ascii=False),
    )
    session.add(tentative)
    session.commit()
    session.refresh(tentative)
    return tentative


def test_historique_anti_repetition_echantillonne_huit_tentatives():
    moteur = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(moteur)

    with Session(moteur) as session:
        utilisateur = _creer_utilisateur(session, 1)
        for numero_tentative in range(1, 10):
            questions = [
                {
                    "question": (
                        f"Dans l'essai {numero_tentative}, quelle méthode permet "
                        f"de résoudre le problème numéro {numero_question} ?"
                    )
                }
                for numero_question in range(1, 6)
            ]
            _creer_tentative(
                session,
                utilisateur.id,
                "Mathématiques",
                questions,
                enveloppe=numero_tentative % 2 == 0,
            )

        # Les dernières activités d'autres personnes/matières ne doivent pas
        # déplacer ni contaminer l'historique propre à cet étudiant.
        _creer_tentative(
            session,
            utilisateur.id,
            "Physique",
            [{"question": "Question réservée à la physique ?"}],
        )
        autre = _creer_utilisateur(session, 2)
        _creer_tentative(
            session,
            autre.id,
            "Mathématiques",
            [{"question": "Question privée d'un autre étudiant ?"}],
        )

        historique = _questions_vues_recemment(
            session, utilisateur.id, "Mathématiques"
        )

    assert len(historique) == 24
    # L'échantillon prend la première question de chacune des huit tentatives
    # les plus récentes, puis leur deuxième question, etc.
    assert historique[:8] == [
        (
            f"Dans l'essai {numero_tentative}, quelle méthode permet "
            "de résoudre le problème numéro 1 ?"
        )
        for numero_tentative in range(9, 1, -1)
    ]
    assert historique[8:16] == [
        (
            f"Dans l'essai {numero_tentative}, quelle méthode permet "
            "de résoudre le problème numéro 2 ?"
        )
        for numero_tentative in range(9, 1, -1)
    ]
    assert not any("essai 1," in question for question in historique)
    assert not any("Physique" in question for question in historique)
    assert not any("autre étudiant" in question for question in historique)


def test_historique_anti_repetition_ignore_les_questions_exactement_dupliquees():
    moteur = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(moteur)

    with Session(moteur) as session:
        utilisateur = _creer_utilisateur(session, 3)
        _creer_tentative(
            session,
            utilisateur.id,
            "Mathématiques",
            [
                {"question": "Comment calculer le déterminant d'une matrice ?"},
                {"question": "Quelle est la méthode pour calculer un déterminant ?"},
            ],
        )
        _creer_tentative(
            session,
            utilisateur.id,
            "Mathématiques",
            [
                {"question": "Comment calculer le déterminant d'une matrice ?"},
                {"question": "Comment résoudre un système linéaire ?"},
            ],
            enveloppe=True,
        )

        historique = _questions_vues_recemment(
            session, utilisateur.id, "Mathématiques"
        )

    assert historique == [
        "Comment calculer le déterminant d'une matrice ?",
        "Comment résoudre un système linéaire ?",
        "Quelle est la méthode pour calculer un déterminant ?",
    ]
