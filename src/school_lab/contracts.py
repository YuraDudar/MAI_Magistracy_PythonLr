"""Контракт анализатора: контекст, реестр фабрик, создание и проверка отчёта на границе."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from school_lab.config import AnalysisConfig
from school_lab.errors import AnalysisFailure
from school_lab.hashing import stable_hash, submission_hash
from school_lab.models import AnalysisReport, Assignment, DomainModel, Finding, Submission


class AnalysisContext(DomainModel):
    """Требования задания и конфигурация анализа. config_hash фиксирует обе части."""

    assignment: Assignment
    config: AnalysisConfig

    @property
    def config_hash(self) -> str:
        return stable_hash(
            {
                "assignment": self.assignment.model_dump(mode="json"),
                "config": self.config.model_dump(mode="json"),
            }
        )


class Analyzer(Protocol):
    """Синхронный анализатор. Наследование не требуется: достаточно совместимой структуры."""

    @property
    def analyzer_id(self) -> str: ...
    @property
    def analyzer_version(self) -> str: ...
    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport: ...


AnalyzerFactory = Callable[[], Analyzer]


class AnalyzerRegistry:
    """Явный реестр фабрик. Новый анализатор подключается регистрацией, без правки сервиса."""

    def __init__(self) -> None:
        self._factories: dict[str, AnalyzerFactory] = {}

    def register(self, name: str, factory: AnalyzerFactory) -> None:
        if not name.strip() or name in self._factories:
            raise AnalysisFailure(
                "registry_error", f"Требуется непустое уникальное имя анализатора: {name!r}"
            )
        self._factories[name] = factory

    def create(self, name: str) -> Analyzer:
        try:
            factory = self._factories[name]
        except KeyError:
            raise AnalysisFailure("unknown_analyzer", f"Неизвестный анализатор: {name}") from None
        analyzer = factory()
        if analyzer.analyzer_id != name:
            raise AnalysisFailure("registry_error", f"Имя регистрации {name} не совпадает с analyzer_id")
        return analyzer

    def names(self) -> tuple[str, ...]:
        return tuple(self._factories)


def make_report(
    submission: Submission,
    context: AnalysisContext,
    *,
    analyzer_id: str,
    analyzer_version: str,
    findings: tuple[Finding, ...],
    review_required: bool = False,
) -> AnalysisReport:
    report = AnalysisReport(
        report_id=str(uuid4()),
        submission_id=submission.submission_id,
        submission_hash=submission_hash(submission),
        analyzer_id=analyzer_id,
        analyzer_version=analyzer_version,
        config_hash=context.config_hash,
        findings=findings,
        created_at=datetime.now(UTC).isoformat(),
        review_required=review_required,
    )
    validate_report(report, submission, context)
    return report


def validate_report(report: object, submission: Submission, context: AnalysisContext) -> AnalysisReport:
    """Проверка результата плагина: аннотация -> AnalysisReport её не гарантирует."""
    if not isinstance(report, AnalysisReport):
        raise AnalysisFailure("invalid_report", "Анализатор вернул не AnalysisReport")
    try:
        # Повторная валидация ловит объекты, собранные в обход проверок (model_copy, model_construct).
        AnalysisReport.model_validate(report.model_dump())
    except ValidationError as exc:
        raise AnalysisFailure("invalid_report", f"Отчёт нарушает схему: {exc.errors()[0]['msg']}") from exc
    if report.submission_id != submission.submission_id or report.submission_hash != submission_hash(
        submission
    ):
        raise AnalysisFailure("invalid_report", "Отчёт ссылается на другую версию сдачи")
    if report.config_hash != context.config_hash:
        raise AnalysisFailure("invalid_report", "Отчёт построен для другой конфигурации")
    for finding in report.findings:
        for evidence in finding.evidence:
            line_count = len(getattr(submission, evidence.field).splitlines())
            if evidence.submission_id != submission.submission_id:
                raise AnalysisFailure("invalid_report", "Evidence ссылается на другую сдачу")
            if evidence.end_line > line_count:
                raise AnalysisFailure("invalid_report", f"Evidence выходит за границы поля {evidence.field}")
    return report
