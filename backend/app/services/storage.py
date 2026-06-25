"""File storage for the archive: manuscript attachments and the asset library.

Local filesystem storage is the only backend today, but everything is written
against the :class:`StorageBackend` interface so a remote / object-storage
adapter (S3, GCS, …) can be dropped in later without touching callers.
Placeholder records (``placeholder:…`` keys) bypass storage entirely.
"""
from __future__ import annotations

import abc
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

PLACEHOLDER_PREFIX = "placeholder:"


def safe_filename(name: str | None) -> str:
    if not name:
        return "file"
    cleaned = _SAFE.sub("-", name).strip("-")
    return cleaned or "file"


def is_placeholder(key: str) -> bool:
    return key.startswith(PLACEHOLDER_PREFIX)


@dataclass
class StoredFile:
    storage_key: str
    size_bytes: int
    sha256: str


class StorageBackend(abc.ABC):
    """The storage contract every backend implements.

    Implement this for a remote/object store later: the routers and the asset
    service depend only on these methods, never on the filesystem directly.
    """

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def write(self, key: str, stream: BinaryIO) -> StoredFile: ...

    @abc.abstractmethod
    def open_stream(self, key: str) -> BinaryIO: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...

    def local_path(self, key: str) -> Path | None:
        """Filesystem path if this backend is local-backed, else ``None``.

        Lets the download endpoint use an efficient ``FileResponse`` on local
        storage while remote backends fall back to streaming ``open_stream``.
        """
        return None


class LocalFileStorage(StorageBackend):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def path_for(self, key: str) -> Path:
        return self._path(key)

    def local_path(self, key: str) -> Path | None:
        return self._path(key)

    def exists(self, key: str) -> bool:
        if is_placeholder(key):
            return False
        return self._path(key).is_file()

    def write(self, key: str, stream: BinaryIO) -> StoredFile:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as fh:
            while chunk := stream.read(64 * 1024):
                size += len(chunk)
                digest.update(chunk)
                fh.write(chunk)
        return StoredFile(storage_key=key, size_bytes=size, sha256=digest.hexdigest())

    def open_stream(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        if is_placeholder(key):
            return
        path = self._path(key)
        if path.is_file():
            path.unlink()


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Module-level cached storage backend, configured from settings."""
    global _storage
    if _storage is None:
        _storage = LocalFileStorage(settings.storage_path)
    return _storage
