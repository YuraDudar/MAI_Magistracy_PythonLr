"""Сервисы приёма и импорта. Не читают stdin, не обращаются к сети."""

from dataclasses import asdict, dataclass, field
from typing import Literal, NotRequired, TypedDict

from school_lab.errors import SubmissionError
from school_lab.hashing import submission_hash
from school_lab.parsing import parse_submission
from school_lab.repositories import SubmissionRepository
from school_lab.sources import SubmissionSource


@dataclass(frozen=True, slots=True)
class Acceptance:
    status: Literal["accepted", "duplicate"]
    submission_id: str
    submission_hash: str


class SubmissionService:
    """Приём сдачи: валидация, затем accepted / duplicate / conflict. Сохранённое не перезаписывается."""

    def __init__(self, repository: SubmissionRepository) -> None:
        self.repository = repository

    def accept(self, raw: object) -> Acceptance:
        submission = parse_submission(raw)
        digest = submission_hash(submission)
        previous = self.repository.get(submission.submission_id)
        if previous is not None:
            if submission_hash(previous) != digest:
                raise SubmissionError(
                    "conflict", "submission_id", "Для новой версии требуется новый submission_id"
                )
            return Acceptance("duplicate", submission.submission_id, digest)
        self.repository.add(submission)
        return Acceptance("accepted", submission.submission_id, digest)


class RecordError(TypedDict):
    line_no: int
    code: str
    field: str
    message: str
    source: NotRequired[str]


def record_error(line_no: int, exc: SubmissionError) -> RecordError:
    return {"line_no": line_no, "code": exc.code, "field": exc.field, "message": exc.message}


@dataclass
class ImportSummary:
    accepted: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    errors: list[RecordError] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def import_source(source: SubmissionSource, service: SubmissionService) -> ImportSummary:
    """Импорт с частичным успехом: ошибка строки фиксируется с номером, остальные обрабатываются.
    Неожиданные исключения не перехватываются."""
    summary = ImportSummary()
    with source.open() as records:
        for record in records:
            if record.error is not None:
                summary.errors.append(record_error(record.line_no, record.error))
                continue
            try:
                result = service.accept(record.raw)
            except SubmissionError as exc:
                summary.errors.append(record_error(record.line_no, exc))
            else:
                target = summary.accepted if result.status == "accepted" else summary.duplicate
                target.append(result.submission_id)
    return summary
