import io
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from scripts.backup_supabase_storage import (
    StorageBackupError,
    SupabaseStorageBackup,
    _CredentialSafeRedirectHandler,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self._stream = io.BytesIO(body)

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self._stream.close()


class FakeStorageAPI:
    def __init__(self):
        self.calls = []
        self.file_bytes = b"pdf-bytes"

    def __call__(self, request, timeout=0):
        self.calls.append(request)
        parsed = urlsplit(request.full_url)
        path = parsed.path
        method = request.get_method()

        if method == "GET" and path == "/storage/v1/bucket/":
            body = [{"id": "documents", "name": "documents", "public": False}]
            return FakeResponse(json.dumps(body).encode())

        if method == "POST" and path == "/storage/v1/object/list/documents":
            payload = json.loads(request.data.decode())
            if payload["prefix"] == "":
                body = [{"name": "cours", "id": None, "metadata": None}]
            elif payload["prefix"] == "cours/":
                body = [{
                    "name": "support de cours.pdf",
                    "id": "object-id",
                    "metadata": {
                        "size": len(self.file_bytes),
                        "mimetype": "application/pdf",
                        "cacheControl": "3600",
                    },
                    "updated_at": "2026-11-01T10:00:00Z",
                    "created_at": "2026-10-01T10:00:00Z",
                }]
            else:
                body = []
            return FakeResponse(json.dumps(body).encode())

        if method == "GET" and path == (
            "/storage/v1/object/documents/cours/support%20de%20cours.pdf"
        ):
            return FakeResponse(self.file_bytes)

        raise AssertionError(f"Unexpected request: {method} {path}")


def test_downloads_nested_objects_and_writes_a_hash_manifest(tmp_path):
    api = FakeStorageAPI()
    backup = SupabaseStorageBackup(
        "https://example.supabase.co",
        "service-role-secret-for-tests",
        opener=api,
    )

    result = backup.backup(tmp_path / "storage")

    target = tmp_path / "storage" / "documents" / "cours" / "support de cours.pdf"
    assert target.read_bytes() == b"pdf-bytes"
    assert result == {"bucket_count": 1, "object_count": 1, "total_bytes": 9}

    manifest = json.loads(
        (tmp_path / "storage" / "storage-manifest.json").read_text(encoding="utf-8")
    )
    record = manifest["buckets"][0]["objects"][0]
    assert record["path"] == "cours/support de cours.pdf"
    assert record["size"] == 9
    assert record["content_type"] == "application/pdf"
    assert len(record["sha256"]) == 64

    for request in api.calls:
        headers = {key.lower(): value for key, value in request.header_items()}
        assert headers["apikey"] == "service-role-secret-for-tests"
        assert headers["authorization"] == "Bearer service-role-secret-for-tests"


def test_rejects_path_traversal_from_storage_listing(tmp_path):
    class MaliciousAPI:
        def __call__(self, request, timeout=0):
            path = urlsplit(request.full_url).path
            if path == "/storage/v1/bucket/":
                return FakeResponse(b'[{"id":"documents","public":false}]')
            if path == "/storage/v1/object/list/documents":
                return FakeResponse(b'[{"name":"..","id":null,"metadata":null}]')
            raise AssertionError(path)

    backup = SupabaseStorageBackup(
        "https://example.supabase.co",
        "service-role-secret-for-tests",
        opener=MaliciousAPI(),
    )
    output = tmp_path / "storage"

    with pytest.raises(StorageBackupError, match="Unsafe"):
        backup.backup(output)

    assert not (tmp_path / "outside").exists()


def test_refuses_to_overwrite_a_non_empty_output_directory(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    backup = SupabaseStorageBackup(
        "https://example.supabase.co",
        "service-role-secret-for-tests",
        opener=FakeStorageAPI(),
    )

    with pytest.raises(StorageBackupError, match="must be empty"):
        backup.backup(output)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_detects_download_size_mismatch(tmp_path):
    api = FakeStorageAPI()
    api.file_bytes = b"short"
    backup = SupabaseStorageBackup(
        "https://example.supabase.co",
        "service-role-secret-for-tests",
        opener=api,
    )
    # The fixture reports the size of the modified payload, then force a
    # mismatch from the API metadata without changing the downloaded object.
    original_call = api.__call__

    def mismatching_api(request, timeout=0):
        response = original_call(request, timeout)
        if request.get_method() == "POST":
            parsed = urlsplit(request.full_url)
            if parsed.path.endswith("/object/list/documents"):
                payload = json.loads(request.data.decode())
                if payload["prefix"] == "cours/":
                    return FakeResponse(json.dumps([{
                        "name": "support de cours.pdf",
                        "id": "object-id",
                        "metadata": {"size": 100, "mimetype": "application/pdf"},
                    }]).encode())
        return response

    backup.opener = mismatching_api
    with pytest.raises(StorageBackupError, match="did not match"):
        backup.backup(tmp_path / "storage")



def test_requires_https_for_storage_credentials():
    with pytest.raises(StorageBackupError, match="HTTPS"):
        SupabaseStorageBackup(
            "http://example.supabase.co",
            "service-role-secret-for-tests",
            opener=FakeStorageAPI(),
        )


def test_empty_bucket_inventory_fails_closed(tmp_path):
    class EmptyBucketsAPI:
        def __call__(self, request, timeout=0):
            assert request.get_method() == "GET"
            return FakeResponse(b"[]")

    backup = SupabaseStorageBackup(
        "https://example.supabase.co",
        "service-role-secret-for-tests",
        opener=EmptyBucketsAPI(),
    )

    with pytest.raises(StorageBackupError, match="No Storage buckets"):
        backup.backup(tmp_path / "empty-storage")



def test_cross_origin_redirect_does_not_forward_storage_credentials():
    from urllib.request import Request

    request = Request(
        "https://project.supabase.co/storage/v1/object/private/file.pdf",
        headers={
            "apikey": "never-forward-this-key",
            "Authorization": "Bearer never-forward-this-key",
        },
    )
    redirected = _CredentialSafeRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://signed-download.example/file.pdf?token=signed",
    )

    headers = {key.lower(): value for key, value in redirected.header_items()}
    assert "authorization" not in headers
    assert "apikey" not in headers


def test_same_origin_redirect_keeps_storage_credentials():
    from urllib.request import Request

    request = Request(
        "https://project.supabase.co/storage/v1/object/private/file.pdf",
        headers={
            "apikey": "test-key",
            "Authorization": "Bearer test-key",
        },
    )
    redirected = _CredentialSafeRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://project.supabase.co/storage/v1/object/private/file.pdf?download=1",
    )

    headers = {key.lower(): value for key, value in redirected.header_items()}
    assert headers["authorization"] == "Bearer test-key"
    assert headers["apikey"] == "test-key"
