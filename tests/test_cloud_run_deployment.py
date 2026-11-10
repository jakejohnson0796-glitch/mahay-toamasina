from pathlib import Path

from app.config import Parametres


ROOT = Path(__file__).resolve().parents[1]


def test_worker_inline_sql_est_desactive_par_defaut(monkeypatch):
    monkeypatch.delenv("AI_WORKER_INLINE_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert Parametres().ai_worker_inline_enabled is False


def test_worker_inline_sql_accepte_les_valeurs_booleennes(monkeypatch):
    for valeur in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("AI_WORKER_INLINE_ENABLED", valeur)
        assert Parametres().ai_worker_inline_enabled is True


def test_worker_inline_sql_refuse_les_valeurs_non_vraies(monkeypatch):
    for valeur in ("", "false", "0", "no", "off"):
        monkeypatch.setenv("AI_WORKER_INLINE_ENABLED", valeur)
        assert Parametres().ai_worker_inline_enabled is False


def test_cloud_run_peut_demarrer_le_worker_sans_redis():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "if parametres.redis_url or parametres.ai_worker_inline_enabled:" in source
    assert '"ai_queue_backend": "redis" if parametres.redis_url else (' in source
    assert '"postgresql" if parametres.ai_worker_inline_enabled else "disabled"' in source


def test_workflow_cloud_run_est_manuel_et_ne_remplace_pas_render():
    workflow = (ROOT / ".github/workflows/deploy-google-cloud-run.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "if: github.ref == 'refs/heads/main' && inputs.confirm_deploy == 'DEPLOY'" in workflow
    assert "google-github-actions/auth@v2" in workflow
    assert "id-token: write" in workflow
    assert "--no-cpu-throttling" in workflow
    assert "--min 1" in workflow and "--max 1" in workflow
    assert "--timeout 3600s" in workflow
    assert "AI_WORKER_INLINE_ENABLED=true" in workflow
    assert "REDIS_URL" not in workflow
    assert "render" not in workflow.lower()


def test_dockerfile_est_compatible_avec_le_port_cloud_run():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]' in dockerfile


def test_guide_cloud_run_signale_cout_et_isolation_des_donnees():
    guide = (ROOT / "docs/deploiement-google-cloud-run.md").read_text(encoding="utf-8").lower()
    assert "facturation continue" in guide
    assert "supabase de staging" in guide
    assert "render reste la production actuelle" in guide
