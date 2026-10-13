"""Контракты хранилищ и in-memory реализации для ЛР 1."""

from collections.abc import Iterable
from typing import Protocol

from school_lab.errors import ConfigError, SubmissionError
from school_lab.models import Assignment, Submission


class SubmissionRepository(Protocol):
    def get(self, submission_id: str) -> Submission | None: ...
    def add(self, submission: Submission) -> None: ...
    def list_all(self) -> list[Submission]: ...


class AssignmentRepository(Protocol):
    def get(self, assignment_id: str) -> Assignment | None: ...


class InMemorySubmissionRepository:
    """Хранит сдачи в словаре. get+add не атомарны между потоками - для ЛР 1 допустимо."""

    def __init__(self) -> None:
        self._items: dict[str, Submission] = {}

    def get(self, submission_id: str) -> Submission | None:
        return self._items.get(submission_id)

    def add(self, submission: Submission) -> None:
        if submission.submission_id in self._items:
            raise SubmissionError("conflict", "submission_id", "Идентификатор уже сохранён")
        self._items[submission.submission_id] = submission

    def list_all(self) -> list[Submission]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)


class InMemoryAssignmentRepository:
    def __init__(self, assignments: Iterable[Assignment]) -> None:
        self._items: dict[str, Assignment] = {}
        for assignment in assignments:
            if assignment.assignment_id in self._items:
                raise ConfigError(f"Повтор задания {assignment.assignment_id}")
            self._items[assignment.assignment_id] = assignment

    def get(self, assignment_id: str) -> Assignment | None:
        return self._items.get(assignment_id)
