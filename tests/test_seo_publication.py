from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from app.config import parametres
from app.templating import _seo_canonical_url, _seo_robots


ROOT = Path(__file__).resolve().parents[1]


def _request(path="/", *, hostname=None, query="", session=None):
    canonical_host = urlsplit(parametres.seo_canonical_base_url).hostname
    return SimpleNamespace(
        url=SimpleNamespace(
            path=path,
            hostname=hostname or canonical_host,
            query=query,
        ),
        session=session or {},
    )


def test_seo_canonical_uses_the_primary_host_and_ignores_query_parameters():
    request = _request("/a-propos", query="utm_source=test")
    assert _seo_canonical_url(request) == (
        f"{parametres.seo_canonical_base_url.rstrip('/')}/a-propos"
    )


def test_only_public_pages_on_the_primary_host_are_indexable():
    assert _seo_robots(_request("/")) == "index, follow"
    assert _seo_robots(_request("/a-propos")) == "index, follow"
    assert _seo_robots(_request("/connexion")) == "noindex, follow"
    assert _seo_robots(_request("/inscription")) == "noindex, follow"
    assert _seo_robots(_request("/dashboard")) == "noindex, follow"
    assert _seo_robots(_request("/faq", query="q=compte")) == "noindex, follow"


def test_other_render_subdomains_are_not_indexable():
    request = _request("/", hostname="mahay-toamasina.onrender.com")
    assert _seo_robots(request) == "noindex, follow"
    assert _seo_canonical_url(request) == (
        f"{parametres.seo_canonical_base_url.rstrip('/')}/"
    )


def test_authenticated_pages_are_not_indexable():
    request = _request("/", session={"user_id": 123})
    assert _seo_robots(request) == "noindex, nofollow"


def test_base_template_exposes_canonical_google_verification_and_site_schema():
    template = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    assert 'name="robots"' in template
    assert 'rel="canonical"' in template
    assert 'name="google-site-verification"' in template
    assert 'type="application/ld+json"' in template
    assert '"@type": "WebSite"' in template
    assert '"name": "MITARIDALA"' in template


def test_sitemap_contains_only_stable_public_pages():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    start = source.index('@app.get("/sitemap.xml"')
    end = source.index('@app.get("/")', start)
    sitemap_source = source[start:end]

    for path in ("/", "/a-propos", "/universites", "/documents", "/cercles",
                 "/faq", "/mode-emploi", "/contact", "/cadre-legal"):
        assert f'"{path}"' in sitemap_source

    assert '"/inscription"' not in sitemap_source
    assert '"/connexion"' not in sitemap_source
    assert "parametres.seo_canonical_base_url" in sitemap_source


def test_search_console_token_is_configured_through_environment_only():
    config = (ROOT / "app/config.py").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'os.getenv("GOOGLE_SITE_VERIFICATION", "")' in config
    assert "GOOGLE_SITE_VERIFICATION=" in env_example


def test_google_search_console_html_file_is_preserved_at_site_root():
    verification_file = ROOT / "google8d625d7edf0d28f9.html"
    assert verification_file.is_file()
    assert verification_file.read_text(encoding="utf-8").strip() == (
        "google-site-verification: google8d625d7edf0d28f9.html"
    )

    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert '@app.get("/google8d625d7edf0d28f9.html", include_in_schema=False)' in source
    assert 'FileResponse(fichier_verification, media_type="text/html")' in source
