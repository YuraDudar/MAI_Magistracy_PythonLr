"""Чистые функции над строками исходника. Номера строк с 1, исходный текст не меняется."""


def nonempty_line_numbers(text: str) -> tuple[int, ...]:
    return tuple(number for number, line in enumerate(text.splitlines(), 1) if line.strip())


def template_ranges(source: str, template: str) -> tuple[tuple[int, int], ...]:
    """Включительные диапазоны точных совпадений блока строк шаблона (без нормализации пробелов)."""
    if not template.strip():
        return ()
    source_lines = source.splitlines()
    template_lines = template.splitlines()
    width = len(template_lines)
    return tuple(
        (index + 1, index + width)
        for index in range(len(source_lines) - width + 1)
        if source_lines[index : index + width] == template_lines
    )


def lines_containing(text: str, pattern: str) -> tuple[int, ...]:
    return tuple(number for number, line in enumerate(text.splitlines(), 1) if pattern in line)
