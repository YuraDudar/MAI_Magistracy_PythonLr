"""Простые анализаторы ЛР 1. Ссылки evidence указывают на строки исходной сдачи."""

from typing import Literal

from school_lab.contracts import AnalysisContext, make_report
from school_lab.errors import AnalysisFailure
from school_lab.lines import nonempty_line_numbers, template_ranges
from school_lab.models import AnalysisReport, Evidence, Finding, Submission


class LengthAnalyzer:
    """Считает непустые строки text и code. Объём не оценивает качество, поэтому score=None."""

    analyzer_id = "length"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        text_lines = nonempty_line_numbers(submission.text)
        code_lines = nonempty_line_numbers(submission.code)
        by_field: tuple[tuple[Literal["text", "code"], tuple[int, ...]], ...] = (
            ("text", text_lines),
            ("code", code_lines),
        )
        evidence = tuple(
            Evidence(submission_id=submission.submission_id, field=field, start_line=n, end_line=n)
            for field, numbers in by_field
            for n in numbers
        )
        finding = Finding(
            kind="rubric_feedback",
            score=None,
            evidence=evidence,
            explanation=(
                f"Непустые строки: text={len(text_lines)}, code={len(code_lines)}. "
                "Длина не оценивает корректность решения."
            ),
        )
        return make_report(
            submission,
            context,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            findings=(finding,),
        )


class TemplateAnalyzer:
    """Ищет точные блоки разрешённого шаблона в коде. Совпадение разрешено и не является нарушением."""

    analyzer_id = "template"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        if submission.assignment_id != context.assignment.assignment_id:
            raise AnalysisFailure("context_mismatch", "Контекст относится к другому заданию")
        ranges = template_ranges(submission.code, context.assignment.allowed_template or "")
        evidence = tuple(
            Evidence(submission_id=submission.submission_id, field="code", start_line=start, end_line=end)
            for start, end in ranges
        )
        if ranges:
            explanation = (
                f"Найдено блоков разрешённого шаблона: {len(ranges)}. "
                "Совпадение с шаблоном разрешено и не является основанием для санкций."
            )
        else:
            explanation = (
                "Точное совпадение с разрешённым шаблоном не найдено. Нечёткое сходство не проверялось."
            )
        finding = Finding(kind="similarity", score=None, evidence=evidence, explanation=explanation)
        return make_report(
            submission,
            context,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            findings=(finding,),
        )


class DeclarationAnalyzer:
    """Проверяет, что при used=true декларация заполнена. Авторство текста не определяет."""

    analyzer_id = "declaration"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        declaration = submission.ai_declaration
        complete = bool(
            declaration.tool
            and declaration.tool.strip()
            and declaration.purpose
            and declaration.purpose.strip()
        )
        if not declaration.used:
            explanation = "Использование ИИ не заявлено. Авторство текста автоматически не определялось."
        elif complete:
            explanation = (
                f"Использование ИИ заявлено: инструмент «{declaration.tool}», цель «{declaration.purpose}»."
            )
        else:
            explanation = "Использование ИИ заявлено, но инструмент или цель не указаны."
        finding = Finding(kind="rubric_feedback", score=None, evidence=(), explanation=explanation)
        return make_report(
            submission,
            context,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            findings=(finding,),
            review_required=declaration.used and (not complete or not declaration.verified_by_student),
        )
