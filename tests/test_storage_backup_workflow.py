from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_storage_backup_workflow_uses_dedicated_secrets_and_manual_trigger():
    workflow = (ROOT / ".github" / "workflows" / "storage-backup.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "secrets.BACKUP_SUPABASE_URL" in workflow
    assert "secrets.BACKUP_STORAGE_SERVICE_KEY" in workflow
    assert "secrets.BACKUP_AGE_RECIPIENT" in workflow
    assert "python scripts/backup_supabase_storage.py" in workflow


def test_storage_backup_workflow_encrypts_before_upload_and_limits_secret_scope():
    workflow = (ROOT / ".github" / "workflows" / "storage-backup.yml").read_text(
        encoding="utf-8"
    )
    upload_step = workflow.split("Publier uniquement le fichier chiffré", 1)[1]

    assert "age --encrypt" in workflow
    assert "tar -tzf" in workflow
    assert "rm -rf \"$backup_dir\"" in workflow
    assert "archive: false" in upload_step
    assert "BACKUP_STORAGE_SERVICE_KEY" not in upload_step
    assert "SUPABASE_SERVICE_KEY" not in upload_step
    assert "path: ${{ runner.temp }}/mahay-storage.tar.gz.age" in upload_step
    assert workflow.index("age --encrypt") < workflow.index(
        "Publier uniquement le fichier chiffré"
    )
    assert "retention-days: 30" in upload_step
