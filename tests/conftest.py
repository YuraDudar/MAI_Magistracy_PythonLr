import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import SubmissionService

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def load_public() -> list[dict[str, Any]]:
    lines = (DATA_DIR / "submissions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


@pytest.fixture
def public_submissions() -> list[dict[str, Any]]:
    return load_public()


@pytest.fixture
def raw_submission() -> dict[str, Any]:
    """Свежая копия корректной сдачи sub-001 для каждого теста."""
    return copy.deepcopy(load_public()[0])


@pytest.fixture
def changed(raw_submission: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    def make(**updates: Any) -> dict[str, Any]:
        result = copy.deepcopy(raw_submission)
        result.update(updates)
        return result

    return make


@pytest.fixture
def repository() -> InMemorySubmissionRepository:
    return InMemorySubmissionRepository()


@pytest.fixture
def service(repository: InMemorySubmissionRepository) -> SubmissionService:
    return SubmissionService(repository)
