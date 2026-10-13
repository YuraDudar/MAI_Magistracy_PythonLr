"""Обратная связь по рубрике: общий контракт результата для локального baseline и модели.
Ответ модели - недоверенные данные: проверяется схема, версия и набор критериев."""

from collections.abc import Mapping
from typing import Annotated, Literal, Protocol

from pydantic import AfterValidator, Field, ValidationError
from pydantic_core import PydanticCustomError

from school_lab.contracts import AnalysisContext, make_report
from school_lab.errors import AnalysisFailure
from school_lab.lines import lines_containing
from school_lab.models import (
    AnalysisReport,
    Assignment,
    DomainModel,
    Evidence,
    Finding,
    NonEmptyStr,
    Submission,
)
from school_lab.parsing import error_location
from school_lab.preparation import InputPreparer

FEEDBACK_SCHEMA_VERSION = 1


def _feedback_version(value: int) -> int:
    if value != FEEDBACK_SCHEMA_VERSION:
        raise PydanticCustomError(
            "unsupported_version",
            "Поддерживается версия ответа {supported}",
            {"supported": FEEDBACK_SCHEMA_VERSION},
        )
    return value


class CriterionFeedback(DomainModel):
    requirement_id: NonEmptyStr
    status: Literal["satisfied", "not_satisfied", "insufficient_evidence"]
    explanation: NonEmptyStr
    evidence: tuple[Evidence, ...] = Field(strict=False)


class ModelFeedback(DomainModel):
    """Контракт результата feedback (версия 1). Неизвестные поля и другая версия отклоняются."""

    schema_version: Annotated[int, AfterValidator(_feedback_version)]
    criteria: tuple[CriterionFeedback, ...] = Field(strict=False)
    review_required: bool


def parse_feedback(raw: object, assignment: Assignment) -> ModelFeedback:
    """Проверяет ответ до создания отчёта. Набор критериев должен совпасть с рубрикой задания."""
    try:
        feedback = ModelFeedback.model_validate(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        code = (
            "unsupported_schema_version" if error["type"] == "unsupported_version" else "invalid_model_output"
        )
        where = error_location(error["loc"], error.get("ctx"), default="feedback")
        raise AnalysisFailure(code, f"Ответ модели отклонён: {where}: {error['msg']}") from exc
    expected = sorted(r.requirement_id for r in assignment.requirements)
    received = sorted(c.requirement_id for c in feedback.criteria)
    if received != expected:
        raise AnalysisFailure(
            "invalid_model_output", f"Критерии ответа {received} не совпадают с рубрикой {expected}"
        )
    return feedback


class FeedbackGenerator(Protocol):
    """Интерфейс формирования feedback. Реализации: локальный baseline и обёртка над моделью."""

    def generate(self, submission: Submission, context: AnalysisContext) -> ModelFeedback: ...


class ModelAdapter(Protocol):
    """Внешняя модель. Возвращает object: ответ ещё не проверен."""

    def generate(self, payload: Mapping[str, object]) -> object: ...


class RequirementsBaseline:
    """Локальный анализатор требований: ищет подстроку требования в коде.
    Найденная строка не доказывает корректность алгоритма, отсутствие - не доказывает ошибку."""

    def generate(self, submission: Submission, context: AnalysisContext) -> ModelFeedback:
        criteria = []
        for requirement in context.assignment.requirements:
            found = lines_containing(submission.code, requirement.pattern)
            evidence = tuple(
                Evidence(submission_id=submission.submission_id, field="code", start_line=n, end_line=n)
                for n in found
            )
            if found:
                status: Literal["satisfied", "not_satisfied"] = "satisfied"
                explanation = (
                    f"{requirement.description}: найдено «{requirement.pattern}» в строках {list(found)}."
                )
            else:
                status = "not_satisfied"
                explanation = (
                    f"{requirement.description}: «{requirement.pattern}» не найдено. "
                    "Возможна другая запись - нужна ручная проверка."
                )
            criteria.append(
                CriterionFeedback(
                    requirement_id=requirement.requirement_id,
                    status=status,
                    explanation=explanation,
                    evidence=evidence,
                )
            )
        return ModelFeedback(
            schema_version=FEEDBACK_SCHEMA_VERSION,
            criteria=tuple(criteria),
            review_required=any(c.status != "satisfied" for c in criteria),
        )


class LocalModelStub:
    """Детерминированный stub без сети: проверяет связку, а не качество модели."""

    def generate(self, payload: Mapping[str, object]) -> object:
        requirements = payload.get("requirements")
        ids = [r for r in requirements if isinstance(r, str)] if isinstance(requirements, list) else []
        return {
            "schema_version": FEEDBACK_SCHEMA_VERSION,
            "criteria": [
                {
                    "requirement_id": requirement_id,
                    "status": "insufficient_evidence",
                    "explanation": f"Stub модели ({payload.get('kind')}): решение не оценивалось.",
                    "evidence": [],
                }
                for requirement_id in ids
            ],
            "review_required": True,
        }


class ModelFeedbackGenerator:
    """Подготовка входа -> вызов модели -> проверка ответа. Режим (LLM/ML) задаёт preparer."""

    def __init__(self, preparer: InputPreparer, model: ModelAdapter) -> None:
        self.preparer = preparer
        self.model = model

    def generate(self, submission: Submission, context: AnalysisContext) -> ModelFeedback:
        payload = self.preparer.prepare(submission, context.assignment)
        return parse_feedback(self.model.generate(payload), context.assignment)


class FeedbackAnalyzer:
    """Анализатор поверх любого FeedbackGenerator: одинаковая форма отчёта для baseline и модели."""

    def __init__(self, analyzer_id: str, analyzer_version: str, generator: FeedbackGenerator) -> None:
        self.analyzer_id = analyzer_id
        self.analyzer_version = analyzer_version
        self.generator = generator

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        feedback = self.generator.generate(submission, context)
        findings = tuple(
            Finding(
                kind="rubric_feedback",
                score=None,
                evidence=c.evidence,
                explanation=f"{c.requirement_id} [{c.status}]: {c.explanation}",
            )
            for c in feedback.criteria
        )
        return make_report(
            submission,
            context,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            findings=findings,
            review_required=feedback.review_required,
        )
