"""Kiwix archive download and import workflow."""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)
from uuid import NAMESPACE_URL, UUID, uuid5

from linux_rag.data import KnowledgeSource, KnowledgeSourceType

__all__ = [
    "ArchiveImportResult",
    "ArchiveMetadata",
    "KiwixArchiveIngestor",
    "KiwixIngestionError",
    "KiwixIngestionResult",
]

logger = logging.getLogger(__name__)


class KiwixIngestionError(RuntimeError):
    """Raised when a Kiwix archive could not be processed."""


DownloadFunc = Callable[[str, Path], int]
ChecksumFunc = Callable[[Path], str]
ClockFunc = Callable[[], datetime]
CatalogResolver = Callable[[str], "ArchiveMetadata"]
CommandRunner = Callable[
    [Sequence[str], Mapping[str, str] | None, Optional[Path]],
    subprocess.CompletedProcess[str],
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _default_download(url: str, target: Path) -> int:
    """Stream a URL to ``target`` returning the number of bytes written."""

    with urllib.request.urlopen(url) as response:  # nosec B310 - trusted catalog URLs
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with target.open("wb") as fh:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                total += len(chunk)
        return total


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_subprocess(
    args: Sequence[str],
    env: Mapping[str, str] | None,
    cwd: Path | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env) if env is not None else None,
        text=True,
        capture_output=True,
    )


@dataclass(frozen=True, slots=True)
class ArchiveMetadata:
    """Describes an available Kiwix archive."""

    archive_id: str
    title: str
    download_url: str
    checksum: str | None = None
    language: str | None = None
    categories: Tuple[str, ...] = ()
    article_count: int | None = None


@dataclass(slots=True)
class ArchiveImportResult:
    """Outcome for a single archive import."""

    metadata: ArchiveMetadata
    zim_path: Path
    knowledge_sources: list[KnowledgeSource]
    bytes_downloaded: int
    refreshed: bool


@dataclass(slots=True)
class KiwixIngestionResult:
    """Summary for the entire Kiwix ingestion run."""

    imported: list[ArchiveImportResult]
    errors: list[str]
    total_articles: int
    total_bytes: int


class KiwixArchiveIngestor:
    """Download, verify, and register Kiwix archives for local retrieval."""

    def __init__(
        self,
        *,
        archives_dir: Path | str,
        extract_dir: Path | str,
        catalog_resolver: CatalogResolver,
        download_func: DownloadFunc | None = None,
        checksum_func: ChecksumFunc | None = None,
        command_runner: CommandRunner | None = None,
        clock: ClockFunc | None = None,
        library_path: Path | str | None = None,
        environment: MutableMapping[str, str] | None = None,
        kiwix_manage_bin: str = "kiwix-manage",
        logger_obj: logging.Logger | None = None,
    ) -> None:
        self._archives_dir = Path(archives_dir).expanduser().resolve()
        self._extract_dir = Path(extract_dir).expanduser().resolve()
        self._catalog_resolver = catalog_resolver
        self._download = download_func or _default_download
        self._checksum = checksum_func or _sha256_file
        self._run_command = command_runner or _run_subprocess
        self._clock = clock or _now_utc
        self._env = environment or {}
        self._kiwix_manage_bin = kiwix_manage_bin
        self._logger = logger_obj or logging.getLogger(__name__)
        self._library_path = (
            Path(library_path).expanduser().resolve()
            if library_path is not None
            else self._archives_dir / "library.xml"
        )

    def ingest_archives(
        self,
        archive_ids: Iterable[str],
        *,
        refresh: bool = False,
    ) -> KiwixIngestionResult:
        """Fetch and register each requested archive."""

        self._ensure_directories()

        imported: list[ArchiveImportResult] = []
        errors: list[str] = []
        total_bytes = 0
        total_articles = 0

        for archive_id in archive_ids:
            try:
                metadata = self._catalog_resolver(archive_id)
            except Exception as exc:
                message = f"{archive_id}: failed to resolve catalog metadata: {exc}"
                errors.append(message)
                self._logger.error(message)
                continue

            try:
                result = self._process_archive(metadata, refresh=refresh)
            except KiwixIngestionError as exc:
                errors.append(str(exc))
                self._logger.error("%s", exc)
                continue

            imported.append(result)
            total_bytes += result.bytes_downloaded
            total_articles += metadata.article_count or 0

        return KiwixIngestionResult(
            imported=imported,
            errors=errors,
            total_articles=total_articles,
            total_bytes=total_bytes,
        )

    def _ensure_directories(self) -> None:
        self._archives_dir.mkdir(parents=True, exist_ok=True)
        self._extract_dir.mkdir(parents=True, exist_ok=True)
        self._library_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._library_path.exists():
            # Create an empty library so kiwix-manage add succeeds.
            self._library_path.write_text("<library/>\n", encoding="utf-8")

    def _process_archive(
        self,
        metadata: ArchiveMetadata,
        *,
        refresh: bool,
    ) -> ArchiveImportResult:
        zim_path, downloaded_bytes = self._download_archive(metadata, refresh=refresh)
        checksum = self._checksum(zim_path)
        if metadata.checksum and metadata.checksum.lower() != checksum.lower():
            raise KiwixIngestionError(
                f"{metadata.archive_id}: checksum mismatch "
                f"(expected {metadata.checksum}, got {checksum})"
            )

        self._register_archive(zim_path, refresh=refresh)

        timestamp = self._clock()
        knowledge_source = KnowledgeSource(
            id=self._knowledge_id(zim_path),
            title=metadata.title,
            type=KnowledgeSourceType.WIKI_ARTICLE,
            section=metadata.language,
            source_path=zim_path.resolve(),
            checksum=checksum,
            ingested_at=timestamp,
            last_refreshed_at=timestamp if refresh else None,
        )

        return ArchiveImportResult(
            metadata=metadata,
            zim_path=zim_path,
            knowledge_sources=[knowledge_source],
            bytes_downloaded=downloaded_bytes,
            refreshed=refresh,
        )

    def _download_archive(
        self,
        metadata: ArchiveMetadata,
        *,
        refresh: bool,
    ) -> tuple[Path, int]:
        filename = Path(metadata.download_url).name or f"{metadata.archive_id}.zim"
        target_path = self._archives_dir / filename

        if refresh and target_path.exists():
            target_path.unlink()

        if target_path.exists():
            return target_path, 0

        with tempfile.NamedTemporaryFile(
            delete=False, dir=self._archives_dir, suffix=".download"
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            bytes_downloaded = self._download(metadata.download_url, tmp_path)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise KiwixIngestionError(
                f"{metadata.archive_id}: failed to download archive: {exc}"
            ) from exc

        os.replace(tmp_path, target_path)
        return target_path, int(bytes_downloaded)

    def _register_archive(self, zim_path: Path, *, refresh: bool) -> None:
        args = [
            self._kiwix_manage_bin,
            str(self._library_path),
            "add",
            str(zim_path),
        ]
        result = self._run_command(args, self._env, self._archives_dir)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            if not message:
                message = f"command exited with status {result.returncode}"
            # If the entry already exists, treat as success for non-refresh runs.
            if not refresh and "already part of the library" in message.lower():
                self._logger.debug(
                    "Archive %s already registered in library %s",
                    zim_path,
                    self._library_path,
                )
                return
            raise KiwixIngestionError(
                f"{zim_path.name}: kiwix-manage add failed: {message}"
            )

    def _knowledge_id(self, zim_path: Path) -> UUID:
        key = f"kiwix://{zim_path.name.lower()}"
        return uuid5(NAMESPACE_URL, key)
