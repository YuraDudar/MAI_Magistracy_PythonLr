import copy
from pathlib import Path
from typing import Any

import pytest
from conftest import CONFIG_DIR, DATA_DIR

from school_lab.config import LLMConfig, MLConfig, load_config, parse_config
from school_lab.errors import ConfigError
from school_lab.manifest import build_manifest, read_manifest, write_manifest
from school_lab.models import Assignment
from school_lab.parsing import load_assignments, parse_submission
from school_lab.preparation import FeaturePreparer, PromptPreparer


@pytest.fixture
def assignment() -> Assignment:
    return load_assignments(DATA_DIR / "assignments.json")[0]


def test_configs_from_files() -> None:
    assert load_config(CONFIG_DIR / "llm.toml") == LLMConfig(mode="llm", prompt_template_version="prompt-v1")
    assert load_config(CONFIG_DIR / "ml.toml") == MLConfig(mode="ml", feature_schema_version="features-v1")


@pytest.mark.parametrize(
    "raw",
    [
        {"mode": "rl"},
        {"mode": "llm"},
        {"mode": "llm", "prompt_template_version": " "},
        {"mode": "ml", "prompt_template_version": "prompt-v1"},
        {"mode": "ml", "feature_schema_version": "features-v1", "extra": 1},
    ],
)
def test_bad_config_rejected(raw: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_unknown_versions_rejected_early() -> None:
    with pytest.raises(ConfigError):
        PromptPreparer("prompt-v999")
    with pytest.raises(ConfigError):
        FeaturePreparer("features-v999")


@pytest.mark.parametrize("preparer", [PromptPreparer("prompt-v1"), FeaturePreparer("features-v1")])
def test_preparers_are_deterministic_and_keep_original(
    preparer: PromptPreparer | FeaturePreparer, raw_submission: dict[str, Any], assignment: Any
) -> None:
    raw_submission["ai_declaration"] = {
        "used": True,
        "tool": "SECRET-TOOL",
        "purpose": "SECRET-PURPOSE",
        "verified_by_student": True,
    }
    submission = parse_submission(raw_submission)
    before = submission.model_copy(deep=True)
    payload = preparer.prepare(submission, assignment)
    assert payload == preparer.prepare(submission, assignment)
    assert submission == before
    assert payload["requirements"] == ["R1", "R2", "R3"]
    # Самоотчёт о ИИ не попадает во вход модели.
    assert "SECRET" not in repr(payload) and "ai_declaration" not in repr(payload)


def test_feature_schema_v1(raw_submission: dict[str, Any], assignment: Any) -> None:
    payload = FeaturePreparer("features-v1").prepare(parse_submission(raw_submission), assignment)
    assert payload["features"] == {
        "text_nonempty_lines": 1,
        "code_nonempty_lines": 3,
        "template_blocks": 1,
        "requirements_matched": 3,
    }


def test_manifest_is_reproducible(public_submissions: list[dict[str, Any]], tmp_path: Path) -> None:
    parsed = [parse_submission(copy.deepcopy(raw)) for raw in public_submissions]
    manifest = build_manifest(parsed)
    assert manifest == build_manifest(reversed(parsed))
    assert manifest["count"] == 12 and manifest["processing_version"] == "ingestion-1"
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    reimported = [parse_submission(raw) for raw in public_submissions]
    assert read_manifest(path) == build_manifest(reimported)
    assert "code" not in repr(manifest["items"])  # manifest не содержит исходников
