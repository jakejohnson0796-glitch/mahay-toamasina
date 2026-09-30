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
