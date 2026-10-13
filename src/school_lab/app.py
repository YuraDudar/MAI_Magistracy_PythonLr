"""Точка сборки приложения: конфигурация -> зависимости. Глобального состояния нет."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import assert_never

from school_lab.analyzers import DeclarationAnalyzer, LengthAnalyzer, TemplateAnalyzer
from school_lab.config import LLMConfig, MLConfig
from school_lab.contracts import AnalyzerRegistry
from school_lab.feedback import FeedbackAnalyzer, LocalModelStub, ModelFeedbackGenerator, RequirementsBaseline
from school_lab.models import Assignment
from school_lab.preparation import FeaturePreparer, InputPreparer, PromptPreparer
from school_lab.repositories import InMemoryAssignmentRepository, InMemorySubmissionRepository
from school_lab.services import AnalysisService, SubmissionService


@dataclass(frozen=True)
class Application:
    submissions: InMemorySubmissionRepository
    submission_service: SubmissionService
    analysis_service: AnalysisService
    registry: AnalyzerRegistry


def make_preparer(config: LLMConfig | MLConfig) -> InputPreparer:
    """Неизвестная версия шаблона или схемы признаков отклоняется здесь, до первой сдачи."""
    match config:
        case LLMConfig():
            return PromptPreparer(config.prompt_template_version)
        case MLConfig():
            return FeaturePreparer(config.feature_schema_version)
        case _:
            assert_never(config)


def build_registry(config: LLMConfig | MLConfig) -> AnalyzerRegistry:
    preparer = make_preparer(config)
    registry = AnalyzerRegistry()
    registry.register("length", LengthAnalyzer)
    registry.register("template", TemplateAnalyzer)
    registry.register("declaration", DeclarationAnalyzer)
    registry.register("requirements", lambda: FeedbackAnalyzer("requirements", "1.0", RequirementsBaseline()))
    registry.register(
        "model-stub",
        lambda: FeedbackAnalyzer("model-stub", "1.0", ModelFeedbackGenerator(preparer, LocalModelStub())),
    )
    return registry


def build_application(config: LLMConfig | MLConfig, assignments: Iterable[Assignment]) -> Application:
    submissions = InMemorySubmissionRepository()
    registry = build_registry(config)
    analysis = AnalysisService(submissions, InMemoryAssignmentRepository(assignments), registry, config)
    return Application(submissions, SubmissionService(submissions), analysis, registry)
