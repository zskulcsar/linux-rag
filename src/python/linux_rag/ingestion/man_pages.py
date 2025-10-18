"""Man page ingestion pipeline producing `KnowledgeSource` records."""

from __future__ import annotations

import gzip
import hashlib
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from linux_rag.data import KnowledgeSource, KnowledgeSourceType

__all__ = [
    "ManPageIngestionError",
    "ManPageIngestionResult",
    "ManPageIngestor",
]

logger = logging.getLogger(__name__)


class ManPageIngestionError(RuntimeError):
    """Raised when a fatal error prevents man page ingestion."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _default_checksum(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class ManPageIngestionResult:
    """Summary of a man page ingestion run."""

    sources: list[KnowledgeSource]
    processed_count: int
    skipped_count: int
    errors: list[str]

    def __bool__(self) -> bool:
        return self.errors == []


class ManPageIngestor:
    """Convert local man pages into persisted text files and metadata records."""

    def __init__(
        self,
        *,
        output_dir: Path | str,
        checksum_fn: Callable[[str | bytes], str] = _default_checksum,
        clock: Callable[[], datetime] = _now_utc,
        logger_obj: logging.Logger | None = None,
    ) -> None:
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._checksum_fn = checksum_fn
        self._clock = clock
        self._logger = logger_obj or logging.getLogger(__name__)

    def ingest(
        self,
        man_root: Path | str,
        *,
        refresh: bool = False,
        include_sections: Sequence[str] | None = None,
    ) -> ManPageIngestionResult:
        """Scan the provided man page root and emit knowledge source records."""

        root = Path(man_root).expanduser().resolve()
        if not root.exists():
            raise ManPageIngestionError(f"man page root does not exist: {root}")
        if not root.is_dir():
            raise ManPageIngestionError(f"man page root must be a directory: {root}")

        if refresh and self._output_dir.exists():
            try:
                shutil.rmtree(self._output_dir)
            except OSError as exc:  # pragma: no cover - depends on filesystem state
                raise ManPageIngestionError(
                    f"failed to clear output directory '{self._output_dir}': {exc}"
                ) from exc

        self._output_dir.mkdir(parents=True, exist_ok=True)

        allowed_sections = None
        if include_sections:
            allowed_sections = {section.lower() for section in include_sections}

        sources: list[KnowledgeSource] = []
        skipped = 0
        errors: list[str] = []

        for source_path in self._discover_man_pages(root):
            relative = source_path.relative_to(root)
            metadata = self._extract_metadata(relative)
            if allowed_sections and metadata.section:
                if metadata.section.lower() not in allowed_sections:
                    continue

            try:
                text = self._read_content(source_path)
            except Exception as exc:
                message = f"{relative}: failed to read man page: {exc}"
                errors.append(message)
                self._logger.warning(message)
                continue

            normalized_text = self._normalize_text(text)
            checksum = self._checksum_fn(normalized_text)
            target_file = self._output_dir / metadata.relative_target
            target_file.parent.mkdir(parents=True, exist_ok=True)

            should_write = True
            if target_file.exists() and not refresh:
                try:
                    existing = target_file.read_text(encoding="utf-8")
                    existing_checksum = self._checksum_fn(existing)
                    if existing_checksum == checksum:
                        should_write = False
                        skipped += 1
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.debug(
                        "Failed to read existing man page copy %s: %s",
                        target_file,
                        exc,
                    )

            if should_write:
                try:
                    target_file.write_text(normalized_text, encoding="utf-8")
                except OSError as exc:
                    message = f"{relative}: failed to persist normalized content: {exc}"
                    errors.append(message)
                    self._logger.error(message)
                    continue

            timestamp = self._clock()
            knowledge = KnowledgeSource(
                id=self._source_id(metadata.relative_target),
                title=metadata.title,
                section=metadata.section,
                type=KnowledgeSourceType.MAN_PAGE,
                source_path=target_file.resolve(),
                checksum=checksum,
                ingested_at=timestamp,
                last_refreshed_at=timestamp if refresh else None,
            )
            sources.append(knowledge)

        return ManPageIngestionResult(
            sources=sources,
            processed_count=len(sources),
            skipped_count=skipped,
            errors=errors,
        )

    def _discover_man_pages(self, root: Path) -> Iterable[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                parent = path.parent.name.lower()
            except Exception:  # pragma: no cover - defensive
                parent = ""
            if parent.startswith("man"):
                yield path

    def _extract_metadata(self, relative: Path) -> "_ManPageMetadata":
        name = relative.name
        if name.endswith(".gz"):
            name = name[:-3]

        title_part, section = self._split_title_section(name)
        title = title_part.replace("_", " ").strip() or title_part.strip()
        section_value = section.strip() if section else None
        relative_target = relative
        if relative_target.suffix == ".gz":
            relative_target = relative_target.with_suffix("")

        if not title:
            title = relative_target.stem or relative_target.name

        return _ManPageMetadata(
            title=title,
            section=section_value,
            relative_target=relative_target,
        )

    def _read_content(self, path: Path) -> str:
        if path.suffix == ".gz":
            with gzip.open(path, "rb") as stream:
                raw = stream.read()
        else:
            raw = path.read_bytes()

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized

    def _split_title_section(self, filename: str) -> tuple[str, str | None]:
        if "." not in filename:
            return filename, None
        base, _, section = filename.rpartition(".")
        return base or filename, section or None

    def _source_id(self, relative_target: Path) -> UUID:
        key = f"man://{relative_target.as_posix().lower()}"
        return uuid5(NAMESPACE_URL, key)


@dataclass(slots=True)
class _ManPageMetadata:
    title: str
    section: str | None
    relative_target: Path
