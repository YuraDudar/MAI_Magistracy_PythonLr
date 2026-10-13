import json
from pathlib import Path
from typing import Any

import pytest

from school_lab.sources import InMemorySource, JSONLSource, SubmissionSource


@pytest.fixture
def jsonl_path(tmp_path: Path, public_submissions: list[dict[str, Any]]) -> Path:
    path = tmp_path / "submissions.jsonl"
    path.write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in public_submissions), encoding="utf-8"
    )
    return path


@pytest.fixture(params=["memory", "jsonl"])
def source(
    request: pytest.FixtureRequest, public_submissions: list[dict[str, Any]], jsonl_path: Path
) -> SubmissionSource:
    if request.param == "memory":
        return InMemorySource(public_submissions)
    return JSONLSource(jsonl_path)


def test_source_contract(source: SubmissionSource, public_submissions: list[dict[str, Any]]) -> None:
    """Общий контракт: порядок, номера записей и данные совпадают у обеих реализаций."""
    with source.open() as records:
        loaded = list(records)
    assert [r.line_no for r in loaded] == list(range(1, len(public_submissions) + 1))
    assert [r.raw for r in loaded] == public_submissions
    assert all(r.error is None for r in loaded)


def test_source_can_be_reopened(source: SubmissionSource) -> None:
    for _ in range(2):
        with source.open() as records:
            assert next(records).line_no == 1


def test_jsonl_closes_file_after_full_read(jsonl_path: Path) -> None:
    source = JSONLSource(jsonl_path)
    with source.open() as records:
        for _ in records:
            pass
    assert source.last_closed is True


def test_jsonl_closes_file_on_early_break(jsonl_path: Path) -> None:
    source = JSONLSource(jsonl_path)
    with source.open() as records:
        next(records)
        assert source.last_closed is None  # пока внутри контекста, файл открыт
    assert source.last_closed is True


def test_jsonl_closes_file_on_consumer_error(jsonl_path: Path) -> None:
    source = JSONLSource(jsonl_path)
    with pytest.raises(RuntimeError, match="потребитель"), source.open() as records:
        next(records)
        raise RuntimeError("потребитель упал")
    assert source.last_closed is True


def test_missing_file_fails_on_open(tmp_path: Path) -> None:
    with pytest.raises(OSError), JSONLSource(tmp_path / "missing.jsonl").open():
        pass


def test_jsonl_bad_lines_become_record_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\n{broken\n\n[1]\n', encoding="utf-8")
    with JSONLSource(path).open() as records:
        loaded = list(records)
    assert [(r.line_no, r.error.code if r.error else None) for r in loaded] == [
        (1, None),
        (2, "invalid_json"),
        (3, "invalid_json"),
        (4, None),
    ]  # [1] - корректный JSON; неверную схему проверит parser


def test_in_memory_source_isolated_from_consumer(public_submissions: list[dict[str, Any]]) -> None:
    source = InMemorySource(public_submissions)
    with source.open() as records:
        first = next(records)
    assert isinstance(first.raw, dict)
    first.raw["student_id"] = "mutated"
    public_submissions[1]["student_id"] = "mutated-too"
    with source.open() as records:
        again: list[Any] = [r.raw for r in records]
    assert again[0]["student_id"] == "student-001"
    assert again[1]["student_id"] == "student-002"
