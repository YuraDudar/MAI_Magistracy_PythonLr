"""Доменные модели. Все модели строгие, неизменяемые и отклоняют неизвестные поля."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

SCHEMA_VERSION = 1


class DomainModel(BaseModel):
    """Общая политика: без приведения типов, без лишних полей, без NaN/inf, frozen."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


def _nonempty(value: str) -> str:
    # strip() только для проверки: сохраняется исходная строка.
    if not value.strip():
        raise PydanticCustomError("empty_string", "Ожидается непустая строка")
    return value


def _aware_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise PydanticCustomError("timestamp", "Ожидается дата и время ISO 8601 с часовым поясом") from None
    if parsed.utcoffset() is None:
        raise PydanticCustomError("timestamp", "Часовой пояс обязателен")
    return value


def _supported_version(value: int) -> int:
    if value != SCHEMA_VERSION:
        raise PydanticCustomError(
            "unsupported_version", "Поддерживается версия схемы {supported}", {"supported": SCHEMA_VERSION}
        )
    return value


NonEmptyStr = Annotated[str, AfterValidator(_nonempty)]
# Хранится исходная строка: разные записи одного момента дают разные хеши (часть контракта).
AwareTimestamp = Annotated[str, AfterValidator(_aware_timestamp)]


class AIDeclaration(DomainModel):
    """Самоотчёт студента об использовании ИИ. Не является меткой происхождения текста."""

    used: bool
    tool: NonEmptyStr | None
    purpose: NonEmptyStr | None
    verified_by_student: bool

    @model_validator(mode="after")
    def _used_requires_details(self) -> "AIDeclaration":
        if self.used and (self.tool is None or self.purpose is None):
            raise PydanticCustomError("declaration", "При used=true обязательны инструмент и цель")
        return self


class Submission(DomainModel):
    """Неизменяемая версия работы. Новая версия оформляется новым submission_id."""

    schema_version: Annotated[int, AfterValidator(_supported_version)]
    submission_id: NonEmptyStr
    student_id: NonEmptyStr
    assignment_id: NonEmptyStr
    submitted_at: AwareTimestamp
    text: str
    code: str
    template_id: NonEmptyStr | None
    ai_declaration: AIDeclaration

    @model_validator(mode="after")
    def _text_or_code(self) -> "Submission":
        if not self.text.strip() and not self.code.strip():
            raise PydanticCustomError(
                "empty_submission", "Текст или код должны быть непустыми", {"field": "text/code"}
            )
        return self


class Requirement(DomainModel):
    """Требование задания. pattern - точная подстрока для локального baseline."""

    requirement_id: NonEmptyStr
    description: NonEmptyStr
    pattern: NonEmptyStr


class Assignment(DomainModel):
    assignment_id: NonEmptyStr
    allowed_template: str | None
    requirements: tuple[Requirement, ...] = Field(strict=False)
