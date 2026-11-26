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
    assert "uses: actions/checkout@v7" in workflow
    assert "python scripts/backup_supabase_storage.py" in workflow


def test_storage_backup_workflow_scopes_credentials_and_encrypts_before_upload():
    workflow = (ROOT / ".github" / "workflows" / "storage-backup.yml").read_text(
        encoding="utf-8"
    )
    download_step = workflow.split("Exporter tous les buckets Supabase", 1)[1].split(
        "Créer et chiffrer l'archive", 1
    )[0]
    encryption_step = workflow.split("Créer et chiffrer l'archive", 1)[1].split(
        "Publier uniquement le fichier chiffré", 1
    )[0]
    upload_step = workflow.split("Publier uniquement le fichier chiffré", 1)[1]

    assert "SUPABASE_SERVICE_KEY:" in download_step
    assert "AGE_RECIPIENT:" not in download_step
    assert "AGE_RECIPIENT:" in encryption_step
    assert "SUPABASE_SERVICE_KEY" not in encryption_step
    assert "age --encrypt" in encryption_step
    assert "tar -tzf" in encryption_step
    assert "rm -rf \"$backup_dir\"" in encryption_step
    assert "archive: false" in upload_step
    assert "BACKUP_STORAGE_SERVICE_KEY" not in upload_step
    assert "SUPABASE_SERVICE_KEY" not in upload_step
    assert "AGE_RECIPIENT" not in upload_step
    assert "path: ${{ runner.temp }}/mahay-storage.tar.gz.age" in upload_step
    assert "retention-days: 30" in upload_step
