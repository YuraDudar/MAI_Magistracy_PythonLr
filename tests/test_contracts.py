"""Контрактные тесты: одни и те же проверки для всех зарегистрированных анализаторов и обоих режимов."""

import math
from typing import Any

import pytest

from school_lab.app import Application, build_application, build_registry
from school_lab.config import LLMConfig, MLConfig
from school_lab.contracts import AnalysisContext, make_report, validate_report
from school_lab.errors import AnalysisFailure
from school_lab.hashing import submission_hash
from school_lab.models import AnalysisReport, Assignment, Evidence, Finding, Submission
from school_lab.parsing import parse_submission

ANALYZERS = ["length", "template", "declaration", "requirements", "model-stub"]
# sub-001 обычная, sub-003 с декларацией, sub-008 синтаксическая ошибка, sub-009 только комментарий,
# sub-010 инструкция внутри текста
SAMPLE_IDS = ["sub-001", "sub-003", "sub-008", "sub-009", "sub-010"]


@pytest.fixture
def samples(public_submissions: list[dict[str, Any]]) -> list[Submission]:
    return [parse_submission(raw) for raw in public_submissions if raw["submission_id"] in SAMPLE_IDS]


@pytest.mark.parametrize("name", ANALYZERS)
def test_analyzer_contract(
    name: str, config: LLMConfig | MLConfig, assignments: list[Assignment], samples: list[Submission]
) -> None:
    analyzer = build_registry(config).create(name)
    context = AnalysisContext(assignment=assignments[0], config=config)
    for submission in samples:
        before = submission.model_copy(deep=True)
        first = analyzer.analyze(submission, context)
        second = analyzer.analyze(submission, context)
        for report in (first, second):
            validate_report(report, submission, context)
            assert report.analyzer_id == name and report.analyzer_version
            assert report.submission_hash == submission_hash(submission)
            assert report.config_hash == context.config_hash
            assert all(f.explanation.strip() for f in report.findings)
        # Повторяемость смысла, а не идентичность: report_id и created_at разные.
        assert first.findings == second.findings
        assert first.review_required == second.review_required
        assert first.report_id != second.report_id
        assert submission == before


def _report(submission: Submission, context: AnalysisContext, *findings: Finding) -> AnalysisReport:
    return make_report(submission, context, analyzer_id="t", analyzer_version="1", findings=findings)


def _finding(**updates: Any) -> Finding:
    base: dict[str, Any] = {"kind": "rubric_feedback", "score": None, "evidence": (), "explanation": "ok"}
    return Finding.model_construct(**{**base, **updates})  # в обход валидации, как дефектный плагин


@pytest.mark.parametrize(
    "finding",
    [
        _finding(score=True),
        _finding(score=math.nan),
        _finding(score=1.5),
        _finding(score=-0.1),
        _finding(kind="verdict"),
        _finding(explanation="  "),
        _finding(
            evidence=(
                Evidence.model_construct(submission_id="sub-001", field="code", start_line=0, end_line=1),
            )
        ),
        _finding(
            evidence=(
                Evidence.model_construct(submission_id="sub-001", field="notes", start_line=1, end_line=1),  # type: ignore[arg-type]
            )
        ),
        _finding(evidence=(Evidence(submission_id="sub-001", field="code", start_line=1, end_line=99),)),
        _finding(evidence=(Evidence(submission_id="sub-999", field="code", start_line=1, end_line=1),)),
    ],
)
def test_validate_report_rejects_bad_findings(
    finding: Finding, submission: Submission, context: AnalysisContext
) -> None:
    with pytest.raises(AnalysisFailure) as caught:
        _report(submission, context, finding)
    assert caught.value.code == "invalid_report"


def test_evidence_last_line_is_valid(submission: Submission, context: AnalysisContext) -> None:
    last = len(submission.code.splitlines())
    evidence = Evidence(submission_id=submission.submission_id, field="code", start_line=1, end_line=last)
    _report(submission, context, Finding(kind="similarity", score=1, evidence=(evidence,), explanation="ok"))


def test_validate_report_rejects_other_version_and_config(
    raw_submission: dict[str, Any],
    submission: Submission,
    context: AnalysisContext,
    assignments: list[Assignment],
) -> None:
    report = _report(submission, context)
    other_version = parse_submission({**raw_submission, "text": "Другая версия"})
    with pytest.raises(AnalysisFailure, match="другую версию"):
        validate_report(report, other_version, context)
    other_context = context.model_copy(update={"assignment": assignments[1]})
    with pytest.raises(AnalysisFailure, match="конфигурации"):
        validate_report(report, submission, other_context)
    with pytest.raises(AnalysisFailure):
        validate_report({"report_id": "x"}, submission, context)


def test_registry_rules() -> None:
    registry = build_registry(LLMConfig(mode="llm", prompt_template_version="prompt-v1"))
    with pytest.raises(AnalysisFailure):
        registry.register("length", lambda: registry.create("template"))  # повтор имени
    with pytest.raises(AnalysisFailure):
        registry.register(" ", lambda: registry.create("template"))
    with pytest.raises(AnalysisFailure) as unknown:
        registry.create("nope")
    assert unknown.value.code == "unknown_analyzer"
    registry.register("alias", lambda: registry.create("length"))
    with pytest.raises(AnalysisFailure, match="не совпадает"):
        registry.create("alias")


class RaisingAnalyzer:
    analyzer_id = "raising"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        raise ZeroDivisionError("дефект плагина")


class WrongHashAnalyzer:
    analyzer_id = "wrong-hash"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        good = make_report(
            submission, context, analyzer_id=self.analyzer_id, analyzer_version="1.0", findings=()
        )
        return good.model_copy(update={"submission_hash": "incorrect"})


class WrongVersionAnalyzer:
    analyzer_id = "wrong-version"
    analyzer_version = "2.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return make_report(
            submission, context, analyzer_id=self.analyzer_id, analyzer_version="1.0", findings=()
        )


@pytest.fixture
def app(assignments: list[Assignment], public_submissions: list[dict[str, Any]]) -> Application:
    application = build_application(LLMConfig(mode="llm", prompt_template_version="prompt-v1"), assignments)
    for raw in public_submissions:
        application.submission_service.accept(raw)
    return application


@pytest.mark.parametrize(
    ("analyzer", "code"),
    [
        (RaisingAnalyzer, "analyzer_error"),
        (WrongHashAnalyzer, "invalid_report"),
        (WrongVersionAnalyzer, "invalid_report"),
    ],
)
def test_service_stops_broken_analyzer_and_keeps_submission(
    app: Application, analyzer: Any, code: str
) -> None:
    app.registry.register(analyzer.analyzer_id, analyzer)
    stored = app.submissions.get("sub-001")
    with pytest.raises(AnalysisFailure) as caught:
        app.analysis_service.run("sub-001", analyzer.analyzer_id)
    assert caught.value.code == code
    assert app.submissions.get("sub-001") == stored
    assert app.analysis_service.run("sub-001", "length").findings  # остальные анализаторы работают


def test_service_errors(app: Application, raw_submission: dict[str, Any]) -> None:
    with pytest.raises(AnalysisFailure) as missing:
        app.analysis_service.run("sub-404", "length")
    assert missing.value.code == "not_found"
    app.submission_service.accept(
        {**raw_submission, "submission_id": "sub-x", "assignment_id": "assignment-77"}
    )
    with pytest.raises(AnalysisFailure) as unknown:
        app.analysis_service.run("sub-x", "length")
    assert unknown.value.code == "unknown_assignment"


class MissingExplanationAnalyzer:
    """Новый анализатор подключается только регистрацией: AnalysisService не меняется."""

    analyzer_id = "missing-explanation"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        empty_text = not submission.text.strip() and bool(submission.code.strip())
        finding = Finding(
            kind="rubric_feedback",
            score=None,
            evidence=(),
            explanation="Пояснение отсутствует." if empty_text else "Пояснение присутствует.",
        )
        return make_report(
            submission,
            context,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            findings=(finding,),
            review_required=empty_text,
        )


def test_new_analyzer_by_registration_only(app: Application, raw_submission: dict[str, Any]) -> None:
    app.registry.register("missing-explanation", MissingExplanationAnalyzer)
    app.submission_service.accept({**raw_submission, "submission_id": "sub-no-text", "text": ""})
    assert app.analysis_service.run("sub-no-text", "missing-explanation").review_required is True
    assert app.analysis_service.run("sub-001", "missing-explanation").review_required is False


def test_end_to_end_all_reports(app: Application) -> None:
    reports = [
        app.analysis_service.run(s.submission_id, name)
        for s in app.submissions.list_all()
        for name in ANALYZERS
    ]
    assert len(reports) == 12 * len(ANALYZERS)
