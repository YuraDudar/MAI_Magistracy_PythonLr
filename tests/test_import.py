import json
from pathlib import Path
from typing import Any

from conftest import DATA_DIR

from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import SubmissionService, import_source
from school_lab.sources import JSONLSource


def test_public_corpus_is_accepted_and_reimport_gives_duplicates(service: SubmissionService) -> None:
    first = import_source(JSONLSource(DATA_DIR / "submissions.jsonl"), service)
    second = import_source(JSONLSource(DATA_DIR / "submissions.jsonl"), service)
    assert len(first.accepted) == 12 and not first.errors
    assert len(second.duplicate) == 12 and not second.accepted and not second.errors


def test_invalid_file_reports_every_bad_line(
    service: SubmissionService, repository: InMemorySubmissionRepository
) -> None:
    import_source(JSONLSource(DATA_DIR / "submissions.jsonl"), service)
    stored_002 = repository.get("sub-002")
    summary = import_source(JSONLSource(DATA_DIR / "invalid_submissions.jsonl"), service)

    assert summary.accepted == []
    assert summary.duplicate == ["sub-001"]
    errors = {e["line_no"]: e["code"] for e in summary.errors}
    assert errors[2] == "conflict"
    assert {errors[n] for n in (3, 4, 5, 6)} == {"invalid_json"}
    assert errors[8] == "unsupported_version"
    assert sorted(errors) == list(range(2, 20))  # все строки кроме первой - ошибки
    assert repository.get("sub-002") == stored_002  # конфликт не перезаписал
    assert len(repository) == 12


def test_broken_line_does_not_stop_import(
    tmp_path: Path, raw_submission: dict[str, Any], service: SubmissionService
) -> None:
    second = {**raw_submission, "submission_id": "sub-x"}
    path = tmp_path / "mixed.jsonl"
    lines = [
        json.dumps(raw_submission),
        "{broken",
        json.dumps(raw_submission),
        json.dumps({**raw_submission, "text": "Другое содержимое"}),
        json.dumps({**raw_submission, "submission_id": "bad", "student_id": ""}),
        json.dumps(second),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = import_source(JSONLSource(path), service)
    assert summary.accepted == ["sub-001", "sub-x"]
    assert summary.duplicate == ["sub-001"]
    assert [(e["line_no"], e["code"]) for e in summary.errors] == [
        (2, "invalid_json"),
        (4, "conflict"),
        (5, "schema_error"),
    ]
