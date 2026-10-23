from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app.apprentissage_memoire import (
    interactions_tuteur_recentes,
    formater_memoire_tuteur,
)
from app.models import ProgressionNotion, SessionTuteur, Utilisateur


def _interaction(utilisateur_id, progression_id, question, reponse=""):
    return SessionTuteur(
        utilisateur_id=utilisateur_id,
        progression_id=progression_id,
        notion="Déterminant d'ordre 2",
        question=question,
        explication="Explication initiale.",
        exemple="Exemple initial.",
        exercice="Exercice.",
        correction="Correction.",
        comprehension_reponse=reponse,
        comprehension_feedback="Vérifie le signe du second produit." if reponse else "",
        comprehension_validee=False,
        date_creation=datetime.utcnow() - timedelta(minutes=1),
    )


def test_memoire_tuteur_reste_isolee_par_compte_et_par_notion():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        etudiant = Utilisateur(
            nom="Etudiant A",
            telephone="+261340000101",
            mot_de_passe_hash="hash-a",
        )
        autre = Utilisateur(
            nom="Etudiant B",
            telephone="+261340000102",
            mot_de_passe_hash="hash-b",
        )
        session.add(etudiant)
        session.add(autre)
        session.commit()
        session.refresh(etudiant)
        session.refresh(autre)

        progression_a = ProgressionNotion(
            utilisateur_id=etudiant.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant d'ordre 2",
            nb_questions=3,
            nb_erreurs=2,
        )
        progression_b = ProgressionNotion(
            utilisateur_id=autre.id,
            matiere="Mathématiques",
            niveau="L1",
            notion="Déterminant d'ordre 2",
            nb_questions=3,
            nb_erreurs=2,
        )
        progression_autre = ProgressionNotion(
            utilisateur_id=etudiant.id,
            matiere="Physique",
            niveau="L1",
            notion="Énergie",
            nb_questions=2,
            nb_erreurs=1,
        )
        session.add_all([progression_a, progression_b, progression_autre])
        session.commit()
        session.refresh(progression_a)
        session.refresh(progression_b)
        session.refresh(progression_autre)

        session.add_all([
            _interaction(
                etudiant.id,
                progression_a.id,
                "Je ne comprends pas le signe du déterminant.",
                "J'ai additionné les deux produits.",
            ),
            _interaction(
                autre.id,
                progression_b.id,
                "ÉCHANGE CONFIDENTIEL AUTRE ÉTUDIANT.",
                "DONNÉE À NE PAS DIVULGUER.",
            ),
            _interaction(
                etudiant.id,
                progression_autre.id,
                "Je confonds énergie et puissance.",
                "Réponse liée à la physique.",
            ),
        ])
        session.commit()

        interactions = interactions_tuteur_recentes(
            session,
            etudiant.id,
            progression_id=progression_a.id,
            limite=3,
        )

    assert len(interactions) == 1
    assert interactions[0]["question"] == "Je ne comprends pas le signe du déterminant."
    assert interactions[0]["reponse_etudiant"] == "J'ai additionné les deux produits."
    assert interactions[0]["etat_comprehension"] == "comprehension a retravailler"
    contexte = formater_memoire_tuteur(interactions)
    assert "J'ai additionné les deux produits." in contexte
    assert "non fiables" in contexte
    assert "DONNÉE À NE PAS DIVULGUER" not in contexte
    assert "Je confonds énergie et puissance." not in contexte
