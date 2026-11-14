from app import rate_limit


class FauxRedis:
    def __init__(self):
        self.compteurs = {}
        self.index = {}

    def eval(self, _script, nombre_cles, *args):
        assert nombre_cles == 2
        rate_key, index_key, now_ms, window_ms, maximum, member, maximum_keys = args
        now_ms = int(now_ms)
        window_ms = int(window_ms)
        maximum = int(maximum)
        maximum_keys = int(maximum_keys)

        compteur = self.compteurs.setdefault(rate_key, {})
        self.compteurs[rate_key] = {
            identifiant: score
            for identifiant, score in compteur.items()
            if score > now_ms - window_ms
        }
        index = self.index.setdefault(index_key, {})
        self.index[index_key] = {
            cle: expiration for cle, expiration in index.items()
            if expiration > now_ms
        }

        compteur = self.compteurs[rate_key]
        if len(compteur) >= maximum:
            self.index[index_key][rate_key] = now_ms + window_ms
            return 1

        compteur[member] = now_ms
        self.index[index_key][rate_key] = now_ms + window_ms
        if len(self.index[index_key]) > maximum_keys:
            plus_ancienne = min(self.index[index_key], key=self.index[index_key].get)
            self.compteurs.pop(plus_ancienne, None)
            self.index[index_key].pop(plus_ancienne, None)
        return 0


def _preparer_redis(monkeypatch, redis_client):
    monkeypatch.setattr(rate_limit.parametres, "redis_url", "redis://redis-test")
    monkeypatch.setattr(rate_limit, "_client_redis", redis_client)
    monkeypatch.setattr(rate_limit, "_url_client_redis", "redis://redis-test")
    rate_limit._tentatives.clear()


def test_rate_limit_store_is_bounded():
    rate_limit._tentatives.clear()
    for i in range(rate_limit.MAX_CLES + 250):
        rate_limit._limite_depassee_memoire(f"attaque:{i}", 1, 60)
    assert len(rate_limit._tentatives) <= rate_limit.MAX_CLES


def test_redis_rate_limit_is_shared_after_local_state_reset(monkeypatch):
    client = FauxRedis()
    _preparer_redis(monkeypatch, client)

    assert rate_limit.limite_depassee("connexion:telephone:123", 2, 60) is False
    assert rate_limit.limite_depassee("connexion:telephone:123", 2, 60) is False

    # Simule un redémarrage : l'état mémoire disparaît, Redis reste la source commune.
    rate_limit._tentatives.clear()
    assert rate_limit.limite_depassee("connexion:telephone:123", 2, 60) is True


def test_redis_rate_limit_hashes_keys_and_bounds_global_index(monkeypatch):
    client = FauxRedis()
    _preparer_redis(monkeypatch, client)

    for i in range(rate_limit.MAX_CLES + 20):
        rate_limit.limite_depassee(f"client:{i}", 1, 60)

    assert len(client.index["mahay:security:rate:v1:index"]) <= rate_limit.MAX_CLES
    assert all(key.startswith("mahay:security:rate:v1:") for key in client.compteurs)


def test_redis_failure_uses_bounded_memory_fallback(monkeypatch):
    class RedisIndisponible:
        def eval(self, *_args):
            raise ConnectionError("redis unavailable")

    _preparer_redis(monkeypatch, RedisIndisponible())
    assert rate_limit.limite_depassee("fallback:test", 1, 60) is False
    assert rate_limit.limite_depassee("fallback:test", 1, 60) is True
    assert len(rate_limit._tentatives) == 1
