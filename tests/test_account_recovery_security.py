import sqlalchemy as sa
from sqlmodel import Session

from app.models import CodeReinitialisationMotDePasse
from app.routers.auth_router import (
    _consommer_code_reinitialisation,
    _invalider_codes_reinitialisation,
)


def _database_reset_codes():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("utilisateur", metadata, sa.Column("id", sa.Integer, primary_key=True))
    CodeReinitialisationMotDePasse.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    return engine


def test_password_reset_code_can_only_be_consumed_once():
    from datetime import datetime, timedelta

    engine = _database_reset_codes()
    with Session(engine) as session:
        entree = CodeReinitialisationMotDePasse(
            utilisateur_id=77,
            code_hash="hash-test",
            expire_le=datetime.utcnow() + timedelta(minutes=10),
        )
        session.add(entree)
        session.commit()
        code_id = entree.id

        assert _consommer_code_reinitialisation(session, code_id, 77) is True
        session.commit()
        assert _consommer_code_reinitialisation(session, code_id, 77) is False


def test_new_password_reset_request_invalidates_all_previous_codes():
    from datetime import datetime, timedelta

    engine = _database_reset_codes()
    with Session(engine) as session:
        session.add_all([
            CodeReinitialisationMotDePasse(
                utilisateur_id=78,
                code_hash="ancien-1",
                expire_le=datetime.utcnow() + timedelta(minutes=10),
            ),
            CodeReinitialisationMotDePasse(
                utilisateur_id=78,
                code_hash="ancien-2",
                expire_le=datetime.utcnow() + timedelta(minutes=10),
            ),
        ])
        session.commit()

        _invalider_codes_reinitialisation(session, 78)
        session.commit()
        actifs = session.exec(
            sa.select(CodeReinitialisationMotDePasse).where(
                CodeReinitialisationMotDePasse.utilisateur_id == 78,
                CodeReinitialisationMotDePasse.utilise == False,  # noqa: E712
            )
        ).all()
        assert actifs == []


def test_admin_confirmation_rate_limit_survives_session_rotation(monkeypatch):
    from types import SimpleNamespace
    from app import admin_security

    compteurs = {}

    def fake_limit(key, maximum, _window):
        deja = compteurs.get(key, 0)
        compteurs[key] = deja + 1
        return deja >= maximum

    monkeypatch.setattr(admin_security, "limite_depassee", fake_limit)
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.10"),
        headers={},
    )

    # Chaque appel représente un navigateur/cookie différent, mais le même admin.
    for _ in range(admin_security.MAX_ECHECS_CONFIRMATION_ADMIN):
        assert admin_security.limite_confirmation_admin_depassee(request, 456) is False
    assert admin_security.limite_confirmation_admin_depassee(request, 456) is True


def test_supervised_account_remains_valid_after_write_only_while_profile_is_approved():
    from app.admin_security import compte_cible_supervise_valide
    from app.models import RoleUtilisateur, Utilisateur

    for role, profil, statut in [
        (RoleUtilisateur.SPONSOR, "sponsor", "approuve"),
        (RoleUtilisateur.RESPONSABLE, "responsable", "approuve"),
    ]:
        cible = Utilisateur(
            id=501,
            nom="Profil approuvé",
            telephone="0340000501",
            mot_de_passe_hash="hash-test",
            role=role,
            profil_souhaite=profil,
        )
        setattr(cible, "statut_verification_" + profil, statut)
        assert compte_cible_supervise_valide(cible) is True

        setattr(cible, "statut_verification_" + profil, "en_attente")
        assert compte_cible_supervise_valide(cible) is False

