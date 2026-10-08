from types import SimpleNamespace

from app import ai_worker


def test_worker_priorise_l_id_redis(monkeypatch):
    tache = SimpleNamespace(id=12)

    monkeypatch.setattr(ai_worker.ai_queue, "redis_configure", lambda: True)
    monkeypatch.setattr(
        ai_worker.ai_queue,
        "attendre_tache",
        lambda timeout=15: 12,
    )
    monkeypatch.setattr(
        ai_worker.ai_queue,
        "prendre_tache",
        lambda tache_id=None: tache if tache_id == 12 else None,
    )

    resultat, dernier_controle = ai_worker._obtenir_prochaine_tache(0.0)

    assert resultat is tache
    assert dernier_controle > 0


def test_worker_utilise_le_fallback_postgres_periodique(monkeypatch):
    tache = SimpleNamespace(id=15)

    monkeypatch.setattr(ai_worker.ai_queue, "redis_configure", lambda: True)
    monkeypatch.setattr(
        ai_worker.ai_queue,
        "attendre_tache",
        lambda timeout=15: None,
    )

    appels = []

    def prendre_tache(tache_id=None):
        appels.append(tache_id)
        return tache if tache_id is None else None

    monkeypatch.setattr(ai_worker.ai_queue, "prendre_tache", prendre_tache)
    monkeypatch.setattr(ai_worker.time, "monotonic", lambda: 100.0)

    resultat, dernier_controle = ai_worker._obtenir_prochaine_tache(0.0)

    assert resultat is tache
    assert appels == [None]
    assert dernier_controle == 100.0



def test_worker_dispatche_une_verification_tuteur(monkeypatch):
    tache = SimpleNamespace(
        type_tache=ai_worker.ai_queue.TYPE_VERIFICATION_TUTEUR,
        session_tuteur_id=27,
    )
    appelees = []

    monkeypatch.setattr(
        ai_worker.ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: appelees.append(session_id),
    )

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, _session_id):
            self.calls += 1
            return SimpleNamespace(
                statut_verification_ia="en_cours" if self.calls == 1 else "terminee",
                erreur_verification_ia=None,
            )

    monkeypatch.setattr(ai_worker, "Session", lambda _engine: FakeSession())

    ai_worker.traiter_tache(tache)

    assert appelees == [27]


def test_worker_rejete_une_verification_tuteur_en_echec(monkeypatch):
    tache = SimpleNamespace(
        type_tache=ai_worker.ai_queue.TYPE_VERIFICATION_TUTEUR,
        session_tuteur_id=28,
    )

    monkeypatch.setattr(
        ai_worker.ai_quiz,
        "verifier_session_tuteur_en_arriere_plan",
        lambda session_id: None,
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, _session_id):
            return SimpleNamespace(
                statut_verification_ia="echouee",
                erreur_verification_ia="Provider indisponible.",
            )

    monkeypatch.setattr(ai_worker, "Session", lambda _engine: FakeSession())

    try:
        ai_worker.traiter_tache(tache)
    except RuntimeError as erreur:
        assert "Provider indisponible." in str(erreur)
    else:
        raise AssertionError("Une vérification Tuteur échouée doit déclencher un retry de la file.")
