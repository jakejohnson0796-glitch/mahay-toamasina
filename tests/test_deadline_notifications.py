from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app.dashboard import notifier_echeances_proches
from app.models import (
    Cours, Devoir, InscriptionCours, Notification, RenduDevoir,
    TypeNotification, Utilisateur,
)


def _database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_rappel_echeance_est_unique_et_exclut_les_devoirs_rendus_ou_fermes():
    engine = _database()
    maintenant = datetime(2026, 11, 2, 9, 0)
    with Session(engine) as session:
        professeur = Utilisateur(nom="Professeur", telephone="0341000001", mot_de_passe_hash="hash")
        etudiant = Utilisateur(nom="Étudiant", telephone="0341000002", mot_de_passe_hash="hash")
        session.add_all([professeur, etudiant])
        session.commit()
        session.refresh(professeur)
        session.refresh(etudiant)

        cours = Cours(
            nom="Algèbre", matiere="Mathématiques", niveau="L1",
            professeur_id=professeur.id, code_invitation="ABCD2345",
        )
        session.add(cours)
        session.commit()
        session.refresh(cours)
        session.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant.id))

        proche = Devoir(
            cours_id=cours.id, titre="Devoir proche",
            date_limite=maintenant + timedelta(hours=6),
        )
        lointain = Devoir(
            cours_id=cours.id, titre="Devoir lointain",
            date_limite=maintenant + timedelta(hours=48),
        )
        ferme = Devoir(
            cours_id=cours.id, titre="Devoir fermé",
            date_limite=maintenant + timedelta(hours=3), est_clos=True,
        )
        archive = Devoir(
            cours_id=cours.id, titre="Devoir archivé",
            date_limite=maintenant + timedelta(hours=3), archive=True,
        )
        deja_rendu = Devoir(
            cours_id=cours.id, titre="Déjà rendu",
            date_limite=maintenant + timedelta(hours=3),
        )
        session.add_all([proche, lointain, ferme, archive, deja_rendu])
        session.commit()
        session.refresh(deja_rendu)
        session.add(RenduDevoir(
            devoir_id=deja_rendu.id, utilisateur_id=etudiant.id,
            chemin_fichier="uploads/rendu-test.pdf", nom_fichier_original="rendu-test.pdf",
        ))
        session.commit()

        assert notifier_echeances_proches(session, etudiant.id, maintenant) == 1
        assert notifier_echeances_proches(session, etudiant.id, maintenant) == 0
        rappels = session.exec(
            select(Notification).where(
                Notification.destinataire_id == etudiant.id,
                Notification.type_notification == TypeNotification.RAPPEL_ECHEANCE,
            )
        ).all()
        assert len(rappels) == 1
        assert "Devoir proche" in rappels[0].contenu
        assert rappels[0].url_destination.startswith(f"/classe/devoirs/{proche.id}?rappel=")
