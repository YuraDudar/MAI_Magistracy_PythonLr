"""Устойчивые отпечатки на основе SHA-256 канонического JSON."""

import hashlib
import json

from school_lab.models import Submission


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def stable_hash(value: object) -> str:
    """SHA-256 канонического JSON. В отличие от hash(), не зависит от процесса."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def submission_hash(submission: Submission) -> str:
    """Отпечаток всей сдачи, включая идентификаторы и декларацию."""
    return stable_hash(submission.model_dump(mode="json"))
