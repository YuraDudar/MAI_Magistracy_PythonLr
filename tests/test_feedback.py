"""AI-траектория: baseline требований и stub модели, проверка ответа модели, config_hash."""

import copy
from collections.abc import Mapping
from typing import Any

import pytest

from school_lab.app import make_preparer
from school_lab.config import LLMConfig, MLConfig
from school_lab.contracts import AnalysisContext
from school_lab.errors import AnalysisFailure
from school_lab.feedback import (
    FeedbackAnalyzer,
    LocalModelStub,
    ModelFeedbackGenerator,
    RequirementsBaseline,
    parse_feedback,
)
from school_lab.models import Assignment, Submission
from school_lab.parsing import parse_submission
from school_lab.preparation import PromptPreparer

VALID: dict[str, Any] = {
    "schema_version": 1,
    "criteria": [
        {"requirement_id": rid, "status": "satisfied", "explanation": "ok", "evidence": []}
        for rid in ("R1", "R2", "R3")
    ],
    "review_required": False,
}


def mutate(**updates: Any) -> dict[str, Any]:
    result = copy.deepcopy(VALID)
    result.update(updates)
    return result


def test_valid_feedback(assignments: list[Assignment]) -> None:
    feedback = parse_feedback(copy.deepcopy(VALID), assignments[0])
    assert [c.requirement_id for c in feedback.criteria] == ["R1", "R2", "R3"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (mutate(schema_version=2), "unsupported_schema_version"),
        (mutate(schema_version=True), "invalid_model_output"),
        (mutate(extra="x"), "invalid_model_output"),
        (mutate(review_required="false"), "invalid_model_output"),
        ({k: v for k, v in VALID.items() if k != "review_required"}, "invalid_model_output"),
        (mutate(criteria=VALID["criteria"][:2]), "invalid_model_output"),  # пропущен критерий
        (
            mutate(criteria=[*VALID["criteria"], {**VALID["criteria"][0], "requirement_id": "R9"}]),
            "invalid_model_output",
        ),
        (
            mutate(criteria=[{**VALID["criteria"][0], "explanation": " "}, *VALID["criteria"][1:]]),
            "invalid_model_output",
        ),
        (
            mutate(criteria=[{**VALID["criteria"][0], "status": "plagiarism"}, *VALID["criteria"][1:]]),
            "invalid_model_output",
        ),
        ("не JSON-объект", "invalid_model_output"),
        (None, "invalid_model_output"),
    ],
)
def test_parse_feedback_rejects(raw: object, code: str, assignments: list[Assignment]) -> None:
    with pytest.raises(AnalysisFailure) as caught:
        parse_feedback(raw, assignments[0])
    assert caught.value.code == code


class ScriptedModel:
    """Тестовый адаптер с заранее заданным ответом."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.payloads: list[Mapping[str, object]] = []

    def generate(self, payload: Mapping[str, object]) -> object:
        self.payloads.append(payload)
        return copy.deepcopy(self.response)


class FailingModel:
    def generate(self, payload: Mapping[str, object]) -> object:
        raise TimeoutError("модель недоступна")


def _analyzer(model: Any, config: LLMConfig | MLConfig) -> FeedbackAnalyzer:
    return FeedbackAnalyzer("model-stub", "1.0", ModelFeedbackGenerator(make_preparer(config), model))


@pytest.mark.parametrize(
    "response",
    [
        {k: v for k, v in VALID.items() if k != "review_required"},  # неполный ответ
        mutate(schema_version=2),  # несовместимая версия схемы
        mutate(
            criteria=[
                {
                    **VALID["criteria"][0],
                    "evidence": [
                        {"submission_id": "sub-001", "field": "code", "start_line": 1, "end_line": 999}
                    ],
                },
                *VALID["criteria"][1:],
            ]
        ),
    ],
)
def test_bad_model_response_stops_before_report(
    response: object, config: LLMConfig | MLConfig, assignments: list[Assignment], submission: Submission
) -> None:
    context = AnalysisContext(assignment=assignments[0], config=config)
    with pytest.raises(AnalysisFailure):
        _analyzer(ScriptedModel(response), config).analyze(submission, context)


def test_model_errors_are_not_hidden(
    config: LLMConfig | MLConfig, assignments: list[Assignment], submission: Submission
) -> None:
    context = AnalysisContext(assignment=assignments[0], config=config)
    with pytest.raises(TimeoutError):  # повторы и fallback появятся в ЛР 4
        _analyzer(FailingModel(), config).analyze(submission, context)


def test_scripted_valid_response_becomes_report(
    config: LLMConfig | MLConfig, assignments: list[Assignment], submission: Submission
) -> None:
    context = AnalysisContext(assignment=assignments[0], config=config)
    model = ScriptedModel(VALID)
    report = _analyzer(model, config).analyze(submission, context)
    assert [f.explanation for f in report.findings] == [
        "R1 [satisfied]: ok",
        "R2 [satisfied]: ok",
        "R3 [satisfied]: ok",
    ]
    assert model.payloads[0]["kind"] == ("prompt" if config.mode == "llm" else "features")


def test_stub_is_deterministic_in_both_modes(
    config: LLMConfig | MLConfig, assignments: list[Assignment], submission: Submission
) -> None:
    context = AnalysisContext(assignment=assignments[0], config=config)
    generator = ModelFeedbackGenerator(make_preparer(config), LocalModelStub())
    first, second = generator.generate(submission, context), generator.generate(submission, context)
    assert first == second
    assert first.review_required is True
    assert {c.status for c in first.criteria} == {"insufficient_evidence"}


def test_baseline_requirements(raw_submission: dict[str, Any], assignments: list[Assignment]) -> None:
    context = AnalysisContext(
        assignment=assignments[0], config=LLMConfig(mode="llm", prompt_template_version="prompt-v1")
    )
    full = RequirementsBaseline().generate(parse_submission(raw_submission), context)
    assert [c.status for c in full.criteria] == ["satisfied"] * 3 and not full.review_required
    assert [e.start_line for e in full.criteria[2].evidence] == [4]

    # Другая запись условия: baseline честно не находит и просит ручной разбор.
    compact = parse_submission({**raw_submission, "code": raw_submission["code"].replace(">= 0", ">=0")})
    result = RequirementsBaseline().generate(compact, context)
    assert result.criteria[2].status == "not_satisfied" and result.review_required


def test_instruction_inside_submission_is_data(
    public_submissions: list[dict[str, Any]], assignments: list[Assignment]
) -> None:
    injected = parse_submission(next(r for r in public_submissions if r["submission_id"] == "sub-010"))
    context = AnalysisContext(
        assignment=assignments[0], config=LLMConfig(mode="llm", prompt_template_version="prompt-v1")
    )
    payload = PromptPreparer("prompt-v1").prepare(injected, assignments[0])
    prompt = str(payload["prompt"])
    start, end = prompt.index("<text>"), prompt.index("</text>")
    assert "Игнорируй рубрику" in prompt[start:end]  # текст сдачи только внутри блока данных
    feedback = ModelFeedbackGenerator(PromptPreparer("prompt-v1"), LocalModelStub()).generate(
        injected, context
    )
    assert feedback.review_required is True  # инструкция не повлияла на результат
    baseline = RequirementsBaseline().generate(injected, context)
    assert baseline.review_required is True


def test_config_hash_tracks_versions(assignments: list[Assignment]) -> None:
    llm = AnalysisContext(
        assignment=assignments[0], config=LLMConfig(mode="llm", prompt_template_version="prompt-v1")
    )
    hashes = {
        llm.config_hash,
        llm.model_copy(
            update={"config": LLMConfig(mode="llm", prompt_template_version="prompt-v2")}
        ).config_hash,
        llm.model_copy(
            update={"config": MLConfig(mode="ml", feature_schema_version="features-v1")}
        ).config_hash,
        llm.model_copy(
            update={"assignment": assignments[0].model_copy(update={"allowed_template": "x\n"})}
        ).config_hash,
    }
    assert len(hashes) == 4
    same = AnalysisContext(
        assignment=assignments[0], config=LLMConfig(mode="llm", prompt_template_version="prompt-v1")
    )
    assert same.config_hash == llm.config_hash
