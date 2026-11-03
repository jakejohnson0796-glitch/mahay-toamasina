from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    Cours,
    Devoir,
    EtablissementPartenaire,
    InscriptionCours,
    MembreEtablissement,
    Notification,
    RoleUtilisateur,
    TypeNotification,
    Utilisateur,
)
from app.routers.notifications_router import _notification_autorisee


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _setup_tenants(session):
    institution_a = EtablissementPartenaire(nom="Université A", code="UNIV-A")
    institution_b = EtablissementPartenaire(nom="Université B", code="UNIV-B")
    professeur = Utilisateur(
        nom="Professeur A",
        telephone="0342000001",
        mot_de_passe_hash="hash-prof",
        role=RoleUtilisateur.PROFESSEUR,
    )
    etudiant_a = Utilisateur(
        nom="Étudiant A",
        telephone="0342000002",
        mot_de_passe_hash="hash-a",
        role=RoleUtilisateur.ETUDIANT,
    )
    etudiant_b = Utilisateur(
        nom="Étudiant B",
        telephone="0342000003",
        mot_de_passe_hash="hash-b",
        role=RoleUtilisateur.ETUDIANT,
    )
    session.add_all([institution_a, institution_b, professeur, etudiant_a, etudiant_b])
    session.commit()
    for item in (institution_a, institution_b, professeur, etudiant_a, etudiant_b):
        session.refresh(item)

    session.add_all([
        MembreEtablissement(
            institution_id=institution_a.id,
            utilisateur_id=professeur.id,
            role="professeur",
            est_actif=True,
        ),
        MembreEtablissement(
            institution_id=institution_a.id,
            utilisateur_id=etudiant_a.id,
            role="etudiant",
            est_actif=True,
        ),
        MembreEtablissement(
            institution_id=institution_b.id,
            utilisateur_id=etudiant_b.id,
            role="etudiant",
            est_actif=True,
        ),
    ])
    cours = Cours(
        nom="Algèbre A",
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur.id,
        institution_id=institution_a.id,
    )
    session.add(cours)
    session.commit()
    session.refresh(cours)
    session.add(InscriptionCours(cours_id=cours.id, utilisateur_id=etudiant_a.id))
    session.commit()
    return institution_a, institution_b, cours, etudiant_a, etudiant_b


def test_notification_de_cours_est_visible_uniquement_au_membre_actif():
    engine = _db()
    with Session(engine) as session:
        _, _, cours, etudiant_a, etudiant_b = _setup_tenants(session)
        notification = Notification(
            destinataire_id=etudiant_a.id,
            type_notification=TypeNotification.NOTE_PUBLIEE,
            contenu="Ta note est publiée.",
            cours_id=cours.id,
        )
        session.add(notification)
        session.commit()
        session.refresh(notification)

        assert _notification_autorisee(session, etudiant_a.id, notification)
        assert not _notification_autorisee(session, etudiant_b.id, notification)

        membre = session.exec(
            select(MembreEtablissement).where(
                MembreEtablissement.institution_id == cours.institution_id,
                MembreEtablissement.utilisateur_id == etudiant_a.id,
            )
        ).one()
        membre.est_actif = False
        session.add(membre)
        session.commit()

        assert not _notification_autorisee(session, etudiant_a.id, notification)
    engine.dispose()


def test_ancienne_notification_de_devoir_retrouve_son_cours_depuis_l_url():
    engine = _db()
    with Session(engine) as session:
        _, _, cours, etudiant_a, _ = _setup_tenants(session)
        devoir = Devoir(cours_id=cours.id, titre="Devoir ancien")
        session.add(devoir)
        session.commit()
        session.refresh(devoir)
        notification = Notification(
            destinataire_id=etudiant_a.id,
            type_notification=TypeNotification.NOUVEAU_DEVOIR,
            contenu="Nouveau devoir.",
            url_destination=f"/classe/devoirs/{devoir.id}",
        )
        session.add(notification)
        session.commit()
        session.refresh(notification)

        assert notification.cours_id is None
        assert _notification_autorisee(session, etudiant_a.id, notification)
    engine.dispose()


def test_ancienne_notification_pedagogique_sans_cours_identifiable_est_masquee():
    engine = _db()
    with Session(engine) as session:
        _, _, _, etudiant_a, _ = _setup_tenants(session)
        notification = Notification(
            destinataire_id=etudiant_a.id,
            type_notification=TypeNotification.STATUT_PRESENCE,
            contenu="Ton statut de présence a changé.",
            url_destination="/mes-presences",
        )
        session.add(notification)
        session.commit()
        session.refresh(notification)

        assert not _notification_autorisee(session, etudiant_a.id, notification)
    engine.dispose()


def test_notification_generale_reste_visible_sans_appartenance_a_un_cours():
    engine = _db()
    with Session(engine) as session:
        etudiant = Utilisateur(
            nom="Compte indépendant",
            telephone="0342000004",
            mot_de_passe_hash="hash",
        )
        session.add(etudiant)
        session.commit()
        session.refresh(etudiant)
        notification = Notification(
            destinataire_id=etudiant.id,
            type_notification=TypeNotification.DOCUMENT_APPROUVE,
            contenu="Ton document est approuvé.",
        )
        session.add(notification)
        session.commit()
        session.refresh(notification)

        assert _notification_autorisee(session, etudiant.id, notification)
    engine.dispose()
