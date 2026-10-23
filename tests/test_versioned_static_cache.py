from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.static_cache import VersionedStaticAssetCacheMiddleware


def _client() -> TestClient:
    app = Starlette()

    @app.route("/static/{asset_path:path}", methods=["GET", "HEAD"])
    def servir_asset(request):
        if request.path_params["asset_path"] == "absent.css":
            return PlainTextResponse("not found", status_code=404)
        return PlainTextResponse("body {}", media_type="text/css")

    @app.route("/page", methods=["GET", "HEAD"])
    def page(request):
        return PlainTextResponse("page")

    app.add_middleware(VersionedStaticAssetCacheMiddleware)
    return TestClient(app)


def test_cache_immuable_pour_asset_versionne_par_contenu():
    response = _client().get("/static/style.css?v=0123abcd-0123456789ab")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_cache_immuable_pour_dependance_vendor_epinglee():
    response = _client().get("/static/vendor/katex/katex.min.js?v=0.19.0")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_asset_non_versionne_reste_sans_cache_force():
    response = _client().get("/static/style.css")
    assert response.status_code == 200
    assert "cache-control" not in response.headers


def test_page_dynamique_ne_devient_pas_cacheable_avec_parametre_v():
    response = _client().get("/page?v=0123abcd-0123456789ab")
    assert response.status_code == 200
    assert "cache-control" not in response.headers


def test_version_invalide_et_asset_absent_ne_sont_pas_caches():
    client = _client()
    invalide = client.get("/static/style.css?v=0")
    absent = client.get("/static/absent.css?v=0123abcd-0123456789ab")
    assert "cache-control" not in invalide.headers
    assert absent.status_code == 404
    assert "cache-control" not in absent.headers
