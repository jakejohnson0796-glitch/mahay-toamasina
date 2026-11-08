from app.database import (
    TEMPS_ATTENTE_VERROU_MIGRATION_MS,
    TEMPS_REQUETE_MIGRATION_MS,
    TEMPS_REQUETE_RUNTIME_MS,
    _arguments_connexion,
    _creer_engine,
    _creer_engine_migration,
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


def test_sqlite_en_memoire_partage_la_meme_base_entre_runtime_et_migrations():
    runtime = _creer_engine("sqlite://")
    try:
        migrations = _creer_engine_migration("sqlite://", "sqlite://", runtime)
        assert migrations is runtime
        with runtime.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE partagee (id INTEGER PRIMARY KEY)")
        with migrations.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM partagee"
            ).scalar_one() == 0
    finally:
        runtime.dispose()


def test_postgresql_garde_un_moteur_migration_distinct():
    runtime = object()
    assert (
        _creer_engine_migration(
            "postgresql://runtime@example.test/mahay",
            "postgresql://migration@example.test/mahay",
            runtime,
        )
        is not runtime
    )
