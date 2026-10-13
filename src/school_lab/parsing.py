"""Разбор внешних данных: синтаксис JSON отдельно от проверки схемы."""

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from school_lab.errors import ConfigError, SubmissionError, SubmissionErrorCode
from school_lab.models import Assignment, Submission

_MESSAGES = {
    "missing": "Обязательное поле отсутствует",
    "extra_forbidden": "Неизвестное поле не допускается",
    "string_type": "Ожидается строка без преобразования типа",
    "bool_type": "Ожидается bool, а не строка или число",
    "int_type": "Ожидается целое число; bool не допускается",
    "model_type": "Ожидается JSON-объект",
    "dict_type": "Ожидается JSON-объект",
}


def _reject_repeated_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SubmissionError("invalid_json", key, "Повтор ключа в JSON-объекте не допускается")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise SubmissionError("invalid_json", "json", f"Нестандартное значение не допускается: {value}")


def decode_json(line: str) -> object:
    """Строгий json.loads: без повторов ключей и NaN/Infinity."""
    if not line.strip():
        raise SubmissionError("invalid_json", "json", "Пустая строка вместо JSON-объекта")
    try:
        return json.loads(line, object_pairs_hook=_reject_repeated_keys, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise SubmissionError(
            "invalid_json", "json", f"Некорректный JSON: {exc.msg}, позиция {exc.pos}"
        ) from exc


def error_location(
    loc: Sequence[int | str], ctx: dict[str, object] | None, default: str = "submission"
) -> str:
    """Путь поля из ошибки Pydantic; для проверок уровня модели берётся ctx['field']."""
    if loc:
        return ".".join(str(part) for part in loc)
    return str((ctx or {}).get("field", default))


def to_submission_error(exc: ValidationError) -> SubmissionError:
    """Переводит первую ошибку Pydantic в доменную ошибку с понятным сообщением."""
    error = exc.errors()[0]
    field = error_location(error["loc"], error.get("ctx"))
    code: SubmissionErrorCode = (
        "unsupported_version" if error["type"] == "unsupported_version" else "schema_error"
    )
    return SubmissionError(code, field, _MESSAGES.get(error["type"], error["msg"]))


def parse_submission(raw: object) -> Submission:
    """Проверяет уже разобранный JSON-объект и создаёт Submission. Вход не изменяется."""
    try:
        return Submission.model_validate(raw)
    except ValidationError as exc:
        raise to_submission_error(exc) from exc


_ASSIGNMENTS = TypeAdapter(list[Assignment])


def load_assignments(path: Path) -> list[Assignment]:
    """Читает справочник заданий; ошибки файла и схемы превращаются в ConfigError."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        assignments = _ASSIGNMENTS.validate_python(raw)
    except (OSError, ValueError) as exc:  # ValidationError и JSONDecodeError - подклассы ValueError
        raise ConfigError(f"Справочник заданий {path} не загружен: {exc}") from exc
    ids = [item.assignment_id for item in assignments]
    if len(ids) != len(set(ids)):
        raise ConfigError("assignment_id в справочнике должны быть уникальны")
    return assignments
