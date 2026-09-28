from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_base_n_appelle_plus_un_entier_comme_une_fonction():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "calculer_jours_inactivite(utilisateur)" in base
    assert "jours_inactivite(utilisateur)" not in base


def test_global_jinja_d_inactivite_est_distinct_du_contexte_securite():
    templating = (ROOT / "app" / "templating.py").read_text(encoding="utf-8")
    assert 'templates.env.globals["calculer_jours_inactivite"]' in templating
