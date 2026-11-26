from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workflow_requires_database_url_and_age_public_recipient():
    workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "secrets.BACKUP_DATABASE_URL" in workflow
    assert "secrets.BACKUP_AGE_RECIPIENT" in workflow
    assert "age1[0-9a-z]+" in workflow
    assert "postgres:17-alpine" in workflow
    assert "jobs:\\n  backup:\\n    name: Exporter et chiffrer les tables public\\n    runs-on: ubuntu-24.04\\n    timeout-minutes: 25\\n    env:" not in workflow
    upload_step = workflow.split("Publier uniquement le fichier chiffré", 1)[1]
    assert "DATABASE_URL" not in upload_step
    assert "AGE_RECIPIENT" not in upload_step


def test_workflow_exports_public_schema_and_uploads_only_ciphertext():
    workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(
        encoding="utf-8"
    )

    assert "--schema=public" in workflow
    assert "pg_restore --list" in workflow
    assert "age --encrypt" in workflow
    assert "trap 'rm -f" in workflow
    assert "trap 'rm -rf" not in workflow
    assert workflow.index("Publier uniquement le fichier chiffré") < workflow.index(
        "Nettoyer les fichiers temporaires du runner"
    )
    assert "path: ${{ runner.temp }}/mahay-backup/mahay-public.dump.age" in workflow
    assert "retention-days: 30" in workflow


def test_backup_document_states_storage_and_automation_limits():
    guide = (ROOT / "docs" / "sauvegarde-et-restauration.md").read_text(
        encoding="utf-8"
    )

    assert "volumes de lignes" in guide
    assert "ne couvre pas" in guide
    assert "fichiers binaires" in guide
    assert "volontairement manuel" in guide
    assert "clé privée" in guide
