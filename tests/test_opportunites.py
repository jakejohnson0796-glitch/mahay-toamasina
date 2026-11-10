from pathlib import Path

from app.routers.opportunites_router import CATEGORIES, _source_http_valide


ROOT = Path(__file__).resolve().parents[1]


def test_seules_les_categories_prevues_sont_proposees():
    assert CATEGORIES == ("bourse", "concours", "admission", "stage", "formation", "evenement")


def test_source_accepte_http_et_https():
    assert _source_http_valide("https://www.exemple.org/appel")
    assert _source_http_valide("http://exemple.org")


def test_source_refuse_les_schemas_non_web_et_les_urls_mal_formees():
    assert not _source_http_valide("javascript:alert(1)")
    assert not _source_http_valide("data:text/html,test")
    assert not _source_http_valide("//exemple.org")
    assert not _source_http_valide("pas-une-url")
    assert not _source_http_valide("")


def test_migration_opportunites_est_reversible_et_suit_la_tete_actuelle():
    migration = (ROOT / "alembic/versions/b7e2c9a4d1f6_opportunites_academiques.py").read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "m1e7b3c5d9a2"' in migration
    assert "op.create_table(" in migration
    assert '"opportuniteacademique"' in migration
    assert "def downgrade()" in migration
