import copy
from typing import Any

import pytest
from pydantic import ValidationError

from school_lab.errors import SubmissionError
from school_lab.hashing import submission_hash
from school_lab.models import Submission
from school_lab.parsing import decode_json, parse_submission

DECLARATION = {"used": False, "tool": None, "purpose": None, "verified_by_student": True}


def test_valid_submission_keeps_original_content(raw_submission: dict[str, Any]) -> None:
    submission = parse_submission(raw_submission)
    assert submission.model_dump(mode="json") == raw_submission
    assert submission.code == raw_submission["code"]  # переводы строк сохранены


@pytest.mark.parametrize(
    ("updates", "code", "field"),
    [
        ({"schema_version": True}, "schema_error", "schema_version"),
        ({"schema_version": "1"}, "schema_error", "schema_version"),
        ({"schema_version": 2}, "unsupported_version", "schema_version"),
        ({"code": 123}, "schema_error", "code"),
        ({"submitted_at": "2026-09-01T10:00:00"}, "schema_error", "submitted_at"),
        ({"submitted_at": "вчера"}, "schema_error", "submitted_at"),
        ({"student_id": ""}, "schema_error", "student_id"),
        ({"student_id": "  "}, "schema_error", "student_id"),
        ({"student_id": None}, "schema_error", "student_id"),
        ({"student_id": 42}, "schema_error", "student_id"),
        ({"unknown": "value"}, "schema_error", "unknown"),
        ({"text": " ", "code": "\n"}, "schema_error", "text/code"),
        ({"template_id": " "}, "schema_error", "template_id"),
        ({"ai_declaration": [DECLARATION]}, "schema_error", "ai_declaration"),
        ({"ai_declaration": {**DECLARATION, "used": "false"}}, "schema_error", "ai_declaration.used"),
        ({"ai_declaration": {**DECLARATION, "extra": 1}}, "schema_error", "ai_declaration.extra"),
        (
            {"ai_declaration": {"used": True, "tool": None, "purpose": None, "verified_by_student": False}},
            "schema_error",
            "ai_declaration",
        ),
        (
            {"ai_declaration": {**DECLARATION, "used": True, "tool": "x", "purpose": " "}},
            "schema_error",
            "ai_declaration.purpose",
        ),
    ],
)
def test_invalid_fields_give_clear_errors(
    raw_submission: dict[str, Any], updates: dict[str, Any], code: str, field: str
) -> None:
    raw_submission.update(updates)
    before = copy.deepcopy(raw_submission)
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw_submission)
    assert (caught.value.code, caught.value.field) == (code, field)
    assert caught.value.message
    assert raw_submission == before  # вход не изменён


@pytest.mark.parametrize("missing", ["student_id", "ai_declaration", "text"])
def test_missing_field(raw_submission: dict[str, Any], missing: str) -> None:
    del raw_submission[missing]
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw_submission)
    assert (caught.value.code, caught.value.field) == ("schema_error", missing)


def test_missing_nested_field(raw_submission: dict[str, Any]) -> None:
    del raw_submission["ai_declaration"]["tool"]
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw_submission)
    assert caught.value.field == "ai_declaration.tool"


def test_typo_in_field_name_is_not_silently_dropped(raw_submission: dict[str, Any]) -> None:
    raw_submission["studnet_id"] = raw_submission.pop("student_id")
    with pytest.raises(SubmissionError):
        parse_submission(raw_submission)


def test_not_an_object() -> None:
    with pytest.raises(SubmissionError) as caught:
        parse_submission([1, 2])
    assert caught.value.field == "submission"


def test_timezone_z_is_accepted(raw_submission: dict[str, Any]) -> None:
    raw_submission["submitted_at"] = "2026-09-01T07:01:00Z"
    assert parse_submission(raw_submission).submitted_at == "2026-09-01T07:01:00Z"


def test_submission_is_frozen(raw_submission: dict[str, Any]) -> None:
    submission = parse_submission(raw_submission)
    with pytest.raises(ValidationError):
        submission.student_id = "other"  # type: ignore[misc]


def test_direct_constructor_also_validates(raw_submission: dict[str, Any]) -> None:
    raw_submission["schema_version"] = True
    with pytest.raises(ValidationError):
        Submission(**raw_submission)


@pytest.mark.parametrize(
    "line",
    ["{broken", "", "   \n", '{"a": 1, "a": 2}', '{"score": NaN}', '{"score": Infinity}'],
)
def test_decode_json_rejects(line: str) -> None:
    with pytest.raises(SubmissionError) as caught:
        decode_json(line)
    assert caught.value.code == "invalid_json"


def test_hash_ignores_key_order_but_tracks_content(raw_submission: dict[str, Any]) -> None:
    original = parse_submission(raw_submission)
    reordered = parse_submission(dict(reversed(list(raw_submission.items()))))
    assert submission_hash(reordered) == submission_hash(original)
    assert submission_hash(original.model_copy(update={"code": original.code + "\n"})) != submission_hash(
        original
    )
    assert submission_hash(original.model_copy(update={"student_id": "x"})) != submission_hash(original)
