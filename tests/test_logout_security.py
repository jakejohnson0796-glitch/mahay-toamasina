from app.routers.auth_router import router


def test_logout_is_post_only():
    routes = [r for r in router.routes if getattr(r, "path", None) == "/deconnexion"]
    assert len(routes) == 1
    assert routes[0].methods == {"POST"}
