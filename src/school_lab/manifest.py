"""Manifest корпуса: идентификаторы, хеши и версия обработки. Время запуска не входит."""

import json
from collections.abc import Iterable
from pathlib import Path

from school_lab.hashing import submission_hash
from school_lab.models import Submission

PROCESSING_VERSION = "ingestion-1"


def build_manifest(
    submissions: Iterable[Submission], processing_version: str = PROCESSING_VERSION
) -> dict[str, object]:
    """Детерминированный manifest: порядок импорта не влияет на результат."""
    items = [
        {
            "submission_id": item.submission_id,
            "student_id": item.student_id,
            "assignment_id": item.assignment_id,
            "submission_hash": submission_hash(item),
        }
        for item in sorted(submissions, key=lambda s: s.submission_id)
    ]
    return {"processing_version": processing_version, "count": len(items), "items": items}


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_manifest(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
