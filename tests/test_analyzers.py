from typing import Any

import pytest
from conftest import make_submission

from school_lab.analyzers import DeclarationAnalyzer, LengthAnalyzer, TemplateAnalyzer
from school_lab.contracts import AnalysisContext
from school_lab.errors import AnalysisFailure
from school_lab.lines import nonempty_line_numbers, template_ranges
from school_lab.models import Submission


def test_nonempty_lines_use_original_numbers() -> None:
    assert nonempty_line_numbers("\n a \n\n b\n") == (2, 4)
    assert nonempty_line_numbers("") == ()


def test_length_analyzer(raw_submission: dict[str, Any], context: AnalysisContext) -> None:
    submission = make_submission(raw_submission, text="первая\n\n  \nвторая", code="\n\nx = 1\n")
    report = LengthAnalyzer().analyze(submission, context)
    (finding,) = report.findings
    assert finding.kind == "rubric_feedback" and finding.score is None
    assert "text=2, code=1" in finding.explanation
    assert [(e.field, e.start_line) for e in finding.evidence] == [("text", 1), ("text", 4), ("code", 3)]


@pytest.mark.parametrize(
    ("source", "template", "expected"),
    [
        ("a\nb\nc\n", "a\nb\n", ((1, 2),)),  # точное совпадение
        ("a\n b\nc\n", "a\nb\n", ()),  # изменён пробел - не совпадение
        ("a\nb\na\nb\n", "a\nb\n", ((1, 2), (3, 4))),  # два совпадения
        ("x\ny\n", "a\nb\n", ()),  # нет совпадений
        ("a\n", " \n", ()),  # пустой шаблон не совпадает со всем файлом
        ("a\n", "a\nb\n", ()),  # шаблон длиннее кода
    ],
)
def test_template_ranges(source: str, template: str, expected: tuple[tuple[int, int], ...]) -> None:
    assert template_ranges(source, template) == expected


def test_template_analyzer_marks_match_as_allowed(submission: Submission, context: AnalysisContext) -> None:
    report = TemplateAnalyzer().analyze(submission, context)
    (finding,) = report.findings
    assert finding.kind == "similarity"
    assert [(e.start_line, e.end_line) for e in finding.evidence] == [(1, 3)]
    assert "разрешено" in finding.explanation
    template_lines = context.assignment.allowed_template.splitlines()  # type: ignore[union-attr]
    assert submission.code.splitlines()[0:3] == template_lines  # evidence указывает на исходные строки


def test_template_evidence_after_shifted_code(
    raw_submission: dict[str, Any], context: AnalysisContext
) -> None:
    shifted = make_submission(raw_submission, code="# заголовок\n\n" + raw_submission["code"])
    (finding,) = TemplateAnalyzer().analyze(shifted, context).findings
    assert [(e.start_line, e.end_line) for e in finding.evidence] == [(3, 5)]


def test_template_analyzer_rejects_other_assignment(
    raw_submission: dict[str, Any], context: AnalysisContext
) -> None:
    other = make_submission(raw_submission, assignment_id="assignment-02")
    with pytest.raises(AnalysisFailure) as caught:
        TemplateAnalyzer().analyze(other, context)
    assert caught.value.code == "context_mismatch"


@pytest.mark.parametrize(
    ("declaration", "review", "phrase"),
    [
        ({"used": False, "tool": None, "purpose": None, "verified_by_student": True}, False, "не заявлено"),
        (
            {"used": True, "tool": "помощник", "purpose": "обсуждение", "verified_by_student": True},
            False,
            "помощник",
        ),
        (
            {"used": True, "tool": "помощник", "purpose": "обсуждение", "verified_by_student": False},
            True,
            "заявлено",
        ),
    ],
)
def test_declaration_analyzer(
    raw_submission: dict[str, Any],
    context: AnalysisContext,
    declaration: dict[str, Any],
    review: bool,
    phrase: str,
) -> None:
    report = DeclarationAnalyzer().analyze(
        make_submission(raw_submission, ai_declaration=declaration), context
    )
    assert report.review_required is review
    assert phrase in report.findings[0].explanation
