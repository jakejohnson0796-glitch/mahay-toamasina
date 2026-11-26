#!/usr/bin/env python3
"""Export all Supabase Storage buckets to a local directory for encryption.

Only object bytes and a minimal manifest are written. Never print object names,
signed URLs, API keys, or response bodies to the workflow log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


PAGE_SIZE = 100
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 90


class StorageBackupError(RuntimeError):
    """A safe-to-display backup error without secrets or response bodies."""


def _safe_segment(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StorageBackupError(f"Invalid empty {label} returned by Storage.")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise StorageBackupError(f"Unsafe {label} returned by Storage.")
    return value


class SupabaseStorageBackup:
    def __init__(
        self,
        supabase_url: str,
        service_key: str,
        *,
        opener=urlopen,
        page_size: int = PAGE_SIZE,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlsplit((supabase_url or "").strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise StorageBackupError("SUPABASE_URL must be a valid HTTPS project URL.")
        if not service_key or "\r" in service_key or "\n" in service_key:
            raise StorageBackupError("SUPABASE_SERVICE_KEY is missing or invalid.")
        if not 1 <= page_size <= 1000:
            raise StorageBackupError("The Storage page size is outside the supported range.")

        self.base_url = supabase_url.strip().rstrip("/")
        self.service_key = service_key
        self.opener = opener
        self.page_size = page_size
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            return self.opener(request, timeout=self.timeout)
        except HTTPError as error:
            raise StorageBackupError(
                f"Supabase Storage request failed (HTTP {error.code})."
            ) from None
        except (URLError, TimeoutError, OSError):
            raise StorageBackupError(
                "Could not connect to Supabase Storage. Check the URL and network access."
            ) from None

    def _request_json(self, method: str, path: str, payload: dict | None = None):
        try:
            with self._request(method, path, payload) as response:
                raw = response.read()
        except StorageBackupError:
            raise
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise StorageBackupError("Supabase Storage returned an invalid JSON response.") from None

    def list_buckets(self) -> list[dict]:
        buckets = self._request_json("GET", "/storage/v1/bucket/")
        if not isinstance(buckets, list):
            raise StorageBackupError("Supabase Storage returned an invalid bucket list.")

        normalized = []
        seen = set()
        for bucket in buckets:
            if not isinstance(bucket, dict):
                raise StorageBackupError("Supabase Storage returned an invalid bucket entry.")
            bucket_id = _safe_segment(bucket.get("id") or bucket.get("name"), label="bucket id")
            if bucket_id in seen:
                raise StorageBackupError("Supabase Storage returned a duplicate bucket id.")
            seen.add(bucket_id)
            normalized.append({
                "id": bucket_id,
                "public": bool(bucket.get("public", False)),
                "created_at": bucket.get("created_at"),
                "updated_at": bucket.get("updated_at"),
                "file_size_limit": bucket.get("file_size_limit"),
                "allowed_mime_types": bucket.get("allowed_mime_types"),
            })

        return sorted(normalized, key=lambda item: item["id"])

    def _list_page(self, bucket_id: str, prefix: str, offset: int) -> list[dict]:
        endpoint = f"/storage/v1/object/list/{quote(bucket_id, safe='')}"
        result = self._request_json(
            "POST",
            endpoint,
            {
                "prefix": prefix,
                "limit": self.page_size,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if not isinstance(result, list):
            raise StorageBackupError("Supabase Storage returned an invalid object listing.")
        return result

    def iter_objects(self, bucket_id: str):
        """Walk folder entries recursively and yield each actual object once."""
        pending = [""]
        visited_folders = set()
        visited_objects = set()

        while pending:
            prefix = pending.pop()
            offset = 0
            while True:
                entries = self._list_page(bucket_id, prefix, offset)
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise StorageBackupError("Supabase Storage returned an invalid object entry.")
                    name = _safe_segment(entry.get("name"), label="object name")
                    object_path = f"{prefix}{name}" if prefix else name
                    metadata = entry.get("metadata")

                    # Legacy Storage listing represents folders with id=null
                    # and metadata=null; actual files carry an object id.
                    is_folder = entry.get("id") is None and metadata is None
                    if is_folder:
                        child_prefix = f"{object_path}/"
                        if child_prefix not in visited_folders:
                            visited_folders.add(child_prefix)
                            pending.append(child_prefix)
                        continue

                    if object_path in visited_objects:
                        raise StorageBackupError("Supabase Storage returned a duplicate object path.")
                    visited_objects.add(object_path)
                    yield object_path, entry

                if len(entries) < self.page_size:
                    break
                offset += len(entries)

    def _download_object(
        self,
        bucket_id: str,
        object_path: str,
        destination: Path,
        metadata: dict,
    ) -> dict:
        encoded_bucket = quote(bucket_id, safe="")
        encoded_path = quote(object_path, safe="/")
        endpoint = f"/storage/v1/object/{encoded_bucket}/{encoded_path}"
        temporary = destination.with_name(destination.name + ".partial")
        digest = hashlib.sha256()
        byte_count = 0

        try:
            with self._request("GET", endpoint) as response:
                with temporary.open("xb") as output:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        byte_count += len(chunk)
        except FileExistsError:
            raise StorageBackupError("A duplicate destination path was detected.") from None
        except StorageBackupError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError:
            temporary.unlink(missing_ok=True)
            raise StorageBackupError("A Storage object could not be written to the backup directory.") from None

        expected_size = metadata.get("size") if isinstance(metadata, dict) else None
        if expected_size is not None:
            try:
                expected_size = int(expected_size)
            except (TypeError, ValueError):
                temporary.unlink(missing_ok=True)
                raise StorageBackupError("Storage returned invalid file-size metadata.") from None
            if expected_size != byte_count:
                temporary.unlink(missing_ok=True)
                raise StorageBackupError("A downloaded object did not match its reported size.")

        temporary.replace(destination)
        return {
            "path": object_path,
            "size": byte_count,
            "sha256": digest.hexdigest(),
            "content_type": (
                metadata.get("mimetype") or metadata.get("contentType")
                if isinstance(metadata, dict)
                else None
            ),
            "cache_control": metadata.get("cacheControl") if isinstance(metadata, dict) else None,
            "updated_at": None,
        }

    def backup(self, output_dir: Path) -> dict:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        if any(output_dir.iterdir()):
            raise StorageBackupError("The output directory must be empty.")

        buckets = self.list_buckets()
        if not buckets:
            raise StorageBackupError("No Storage buckets were found; refusing to create an empty backup.")

        manifest_buckets = []
        total_objects = 0
        total_bytes = 0

        for bucket in buckets:
            bucket_id = bucket["id"]
            bucket_dir = output_dir / bucket_id
            bucket_dir.mkdir(parents=True, exist_ok=True)
            file_records = []
            bucket_bytes = 0

            for object_path, entry in self.iter_objects(bucket_id):
                parts = PurePosixPath(object_path).parts
                if not parts or any(part in {"", ".", ".."} for part in parts):
                    raise StorageBackupError("An unsafe Storage object path was detected.")
                destination = bucket_dir.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise StorageBackupError("Two Storage objects map to the same local path.")

                record = self._download_object(
                    bucket_id,
                    object_path,
                    destination,
                    entry.get("metadata") or {},
                )
                record["updated_at"] = entry.get("updated_at")
                record["created_at"] = entry.get("created_at")
                file_records.append(record)
                bucket_bytes += record["size"]

            manifest_buckets.append({
                **bucket,
                "object_count": len(file_records),
                "total_bytes": bucket_bytes,
                "objects": file_records,
            })
            total_objects += len(file_records)
            total_bytes += bucket_bytes

        manifest = {
            "format_version": 1,
            "source_host": urlsplit(self.base_url).hostname,
            "bucket_count": len(manifest_buckets),
            "object_count": total_objects,
            "total_bytes": total_bytes,
            "buckets": manifest_buckets,
        }
        manifest_path = output_dir / "storage-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "bucket_count": len(manifest_buckets),
            "object_count": total_objects,
            "total_bytes": total_bytes,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a local export of every Supabase Storage bucket.")
    parser.add_argument("--output", required=True, type=Path, help="Empty output directory for the export.")
    arguments = parser.parse_args(argv)

    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not service_key:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY are required.", file=sys.stderr)
        return 2

    try:
        backup = SupabaseStorageBackup(supabase_url, service_key)
        summary = backup.backup(arguments.output)
    except StorageBackupError as error:
        print(f"Storage backup failed: {error}", file=sys.stderr)
        return 1

    print(
        "Storage export complete: "
        f"{summary['bucket_count']} buckets, "
        f"{summary['object_count']} objects, "
        f"{summary['total_bytes']} bytes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
