"""Конфигурация режима анализа: LLM хранит версию шаблона запроса, ML - версию схемы признаков."""

import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError

from school_lab.errors import ConfigError
from school_lab.models import DomainModel, NonEmptyStr


class LLMConfig(DomainModel):
    mode: Literal["llm"]
    prompt_template_version: NonEmptyStr


class MLConfig(DomainModel):
    mode: Literal["ml"]
    feature_schema_version: NonEmptyStr


AnalysisConfig = Annotated[LLMConfig | MLConfig, Field(discriminator="mode")]
_CONFIG = TypeAdapter[LLMConfig | MLConfig](AnalysisConfig)


def parse_config(raw: object) -> LLMConfig | MLConfig:
    try:
        return _CONFIG.validate_python(raw)
    except ValidationError as exc:
        raise ConfigError(
            f"Некорректная конфигурация: {exc.errors()[0]['msg']} ({exc.errors()[0]['loc']})"
        ) from exc


def load_config(path: Path) -> LLMConfig | MLConfig:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Конфигурация {path} не прочитана: {exc}") from exc
    return parse_config(raw)
