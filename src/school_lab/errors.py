"""Доменные исключения. HTTP-статусы и коды завершения CLI назначают адаптеры."""

from typing import Literal

SubmissionErrorCode = Literal["invalid_json", "schema_error", "unsupported_version", "conflict"]


class SubmissionError(Exception):
    """Ошибка приёма одной сдачи: машинный код, поле и понятное сообщение."""

    def __init__(self, code: SubmissionErrorCode, field: str, message: str) -> None:
        super().__init__(message)
        self.code: SubmissionErrorCode = code
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}


class AnalysisFailure(Exception):
    """Отказ анализа: неверный контекст, некорректный отчёт или ответ модели."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class ConfigError(Exception):
    """Некорректная конфигурация или справочник заданий. Обнаруживается до обработки сдач."""
