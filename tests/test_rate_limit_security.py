from app import rate_limit


def test_rate_limit_store_is_bounded():
    rate_limit._tentatives.clear()
    for i in range(rate_limit.MAX_CLES + 250):
        rate_limit.limite_depassee(f"attaque:{i}", 1, 60)
    assert len(rate_limit._tentatives) <= rate_limit.MAX_CLES
