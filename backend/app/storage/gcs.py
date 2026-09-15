from __future__ import annotations

import mimetypes
from typing import Protocol
from uuid import UUID

from app.config import Settings, get_settings


class ObjectStorage(Protocol):
    def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Upload and return a storage URI (gs:// or mem://)."""

    def download_bytes(self, uri: str) -> bytes:
        ...

    def delete_uri(self, uri: str) -> None:
        ...

    def delete_prefix(self, prefix: str) -> None:
        ...


def asset_object_key(
    clerk_user_id: str,
    session_id: UUID,
    asset_id: UUID,
    filename: str,
) -> str:
    safe_name = filename.replace("\\", "/").split("/")[-1] or "file.bin"
    return f"users/{clerk_user_id}/sessions/{session_id}/{asset_id}/{safe_name}"


def preview_object_key(
    clerk_user_id: str,
    session_id: UUID,
    asset_id: UUID,
) -> str:
    return f"users/{clerk_user_id}/sessions/{session_id}/{asset_id}/preview.png"


def analysis_overlay_object_key(
    clerk_user_id: str,
    session_id: str,
    analysis_id: str,
) -> str:
    return (
        f"users/{clerk_user_id}/sessions/{session_id}/"
        f"analysis/{analysis_id}/overlay.png"
    )

def guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


class MemoryStorage:
    """In-memory object store for tests and local runs without GCS."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        uri = f"mem://{key}"
        self._objects[uri] = (data, content_type)
        return uri

    def download_bytes(self, uri: str) -> bytes:
        if uri not in self._objects:
            raise FileNotFoundError(uri)
        return self._objects[uri][0]

    def delete_uri(self, uri: str) -> None:
        self._objects.pop(uri, None)

    def delete_prefix(self, prefix: str) -> None:
        needle = f"mem://{prefix}"
        for uri in list(self._objects):
            if uri.startswith(needle):
                del self._objects[uri]


class GcsStorage:
    def __init__(
        self,
        bucket_name: str,
        *,
        project: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        from google.cloud import storage
        from google.oauth2 import service_account

        credentials = None
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
        self._client = storage.Client(project=project or None, credentials=credentials)
        self._bucket = self._client.bucket(bucket_name)
        self._bucket_name = bucket_name

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self._bucket_name}/{key}"

    def download_bytes(self, uri: str) -> bytes:
        key = self._key_from_uri(uri)
        blob = self._bucket.blob(key)
        return blob.download_as_bytes()

    def delete_uri(self, uri: str) -> None:
        key = self._key_from_uri(uri)
        blob = self._bucket.blob(key)
        blob.delete(if_generation_match=None)

    def delete_prefix(self, prefix: str) -> None:
        blobs = self._client.list_blobs(self._bucket_name, prefix=prefix)
        for blob in blobs:
            blob.delete()

    def _key_from_uri(self, uri: str) -> str:
        prefix = f"gs://{self._bucket_name}/"
        if not uri.startswith(prefix):
            raise ValueError(f"URI not in configured bucket: {uri}")
        return uri[len(prefix) :]


_storage: ObjectStorage | None = None


def get_storage(settings: Settings | None = None) -> ObjectStorage:
    global _storage
    if _storage is not None:
        return _storage
    cfg = settings or get_settings()
    if cfg.gcs_bucket:
        _storage = GcsStorage(
            cfg.gcs_bucket,
            project=cfg.google_cloud_project or None,
            credentials_path=cfg.google_application_credentials or None,
        )
    else:
        _storage = MemoryStorage()
    return _storage


def set_storage(storage: ObjectStorage | None) -> None:
    global _storage
    _storage = storage
