from app.database import (
    TEMPS_ATTENTE_VERROU_MIGRATION_MS,
    TEMPS_REQUETE_MIGRATION_MS,
    TEMPS_REQUETE_RUNTIME_MS,
    _arguments_connexion,
)


def test_runtime_conserve_un_timeout_court_pour_les_requetes_http():
    args = _arguments_connexion(
        "postgresql://mahay_runtime:secret@example.test:5432/mahay"
    )
    assert args["connect_timeout"] == 10
    assert args["options"] == f"-c statement_timeout={TEMPS_REQUETE_RUNTIME_MS}"
    assert TEMPS_REQUETE_RUNTIME_MS == 10_000


def test_migrations_disposent_d_un_delai_plus_long_et_d_un_lock_timeout():
    args = _arguments_connexion(
        "postgresql://postgres:secret@example.test:5432/mahay",
        pour_migrations=True,
    )
    assert args["connect_timeout"] == 10
    assert f"statement_timeout={TEMPS_REQUETE_MIGRATION_MS}" in args["options"]
    assert f"lock_timeout={TEMPS_ATTENTE_VERROU_MIGRATION_MS}" in args["options"]
    assert TEMPS_REQUETE_MIGRATION_MS > TEMPS_REQUETE_RUNTIME_MS


def test_sqlite_garde_son_option_de_connexion_compatible():
    args = _arguments_connexion("sqlite:///./mahay-test.db", pour_migrations=True)
    assert args == {"check_same_thread": False}
