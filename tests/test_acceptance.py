from collections.abc import Callable
from typing import Any

import pytest

from school_lab.errors import SubmissionError
from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import SubmissionService


def test_accept_duplicate_conflict(
    service: SubmissionService,
    repository: InMemorySubmissionRepository,
    raw_submission: dict[str, Any],
    changed: Callable[..., dict[str, Any]],
) -> None:
    first = service.accept(raw_submission)
    assert first.status == "accepted"
    stored = repository.get("sub-001")

    again = service.accept(changed())
    assert again.status == "duplicate"
    assert again.submission_hash == first.submission_hash

    with pytest.raises(SubmissionError) as caught:
        service.accept(changed(code="print('другая версия')\n"))
    assert caught.value.code == "conflict"
    assert repository.get("sub-001") == stored  # исходная запись не перезаписана
    assert len(repository) == 1


def test_invalid_submission_is_not_stored(
    service: SubmissionService,
    repository: InMemorySubmissionRepository,
    changed: Callable[..., dict[str, Any]],
) -> None:
    with pytest.raises(SubmissionError):
        service.accept(changed(student_id=""))
    assert len(repository) == 0


def test_new_version_needs_new_id(
    service: SubmissionService,
    repository: InMemorySubmissionRepository,
    changed: Callable[..., dict[str, Any]],
) -> None:
    service.accept(changed())
    result = service.accept(changed(submission_id="sub-001-v2", code="def solve(values):\n    return 1\n"))
    assert result.status == "accepted"
    assert len(repository) == 2
    first, second = repository.get("sub-001"), repository.get("sub-001-v2")
    assert first is not None and second is not None
    assert first.code != second.code


def test_repository_add_refuses_overwrite(
    service: SubmissionService, repository: InMemorySubmissionRepository, raw_submission: dict[str, Any]
) -> None:
    service.accept(raw_submission)
    stored = repository.get("sub-001")
    assert stored is not None
    with pytest.raises(SubmissionError) as caught:
        repository.add(stored)
    assert caught.value.code == "conflict"
