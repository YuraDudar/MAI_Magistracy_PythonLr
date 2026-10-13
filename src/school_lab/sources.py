"""Источники сдач. Контекст open() владеет ресурсом и выдаёт итератор записей."""

import copy
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from school_lab.errors import SubmissionError
from school_lab.parsing import decode_json


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Номер записи и разобранный JSON либо ошибка синтаксиса. Схему проверяет parser."""

    line_no: int
    raw: object = None
    error: SubmissionError | None = None


class SubmissionSource(Protocol):
    def open(self) -> AbstractContextManager[Iterator[SourceRecord]]: ...


class InMemorySource:
    """Источник из готовых объектов. Отдаёт копии, чтобы потребитель не менял исходные данные."""

    def __init__(self, values: Iterable[object]) -> None:
        self._values = copy.deepcopy(list(values))

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        def records() -> Iterator[SourceRecord]:
            for number, raw in enumerate(self._values, start=1):
                yield SourceRecord(number, copy.deepcopy(raw))

        yield records()


class JSONLSource:
    """Построчное чтение JSONL. Файл закрывается при выходе из контекста: полный проход,
    break или исключение потребителя. Пустая строка считается invalid_json."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.last_closed: bool | None = None  # для проверки освобождения ресурса в тестах

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        # Ошибка открытия (OSError) не превращается в ошибку записи: продолжать нечего.
        handle = self.path.open("r", encoding="utf-8-sig")
        try:
            with handle:
                yield self._records(handle)
        finally:
            self.last_closed = handle.closed

    @staticmethod
    def _records(lines: Iterable[str]) -> Iterator[SourceRecord]:
        for number, line in enumerate(lines, start=1):
            try:
                raw = decode_json(line)
            except SubmissionError as exc:
                yield SourceRecord(number, error=exc)
            else:
                yield SourceRecord(number, raw=raw)
