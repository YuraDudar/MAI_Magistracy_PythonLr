# Онлайн-школа: приём работ и анализ сдач

| Студент                | Группа | Дисциплина |
| ---------------------- | ------ | ---------- |
| Дударь Юрий Мохсенович | М8О-105СВ-26       | Python, магистратура, 1 семестр |

> Система принимает сдачи лабораторных, строго их валидирует, хранит как неизменяемые версии и прогоняет через заменяемые анализаторы. Анализатор только фиксирует наблюдения; решение о нарушении принимает преподаватель.

Траектория: **AI и MLOps**. Один репозиторий на все четыре лабораторные: каждая следующая работа расширяет предыдущую.

---

## Оглавление

- [Лабораторные](#лабораторные)
- [Быстрый старт](#быстрый-старт)
- [ЛР 1 — Приём работ и расширяемые анализаторы](#лр-1--приём-работ-и-расширяемые-анализаторы)
- [Проверки качества](#проверки-качества)
- [Структура проекта](#структура-проекта)
- [Технологический стек](#технологический-стек)

---

## Лабораторные

| ЛР | Тема | Статус | Тег | Отчёт |
|---|---|---|---|---|
| 1 | Приём работ и расширяемые анализаторы | готово (основной + углублённый уровень) | `lab-1-stage-a`, `lab-1` | [reports/lab1.md](reports/lab1.md) |
| 2 | Анализ сходства и оценка качества | — | — | — |
| 3 | Конкурентная обработка и состояние системы | — | — | — |
| 4 | Надёжность интеллектуального сервиса и релиз | — | — | — |

---

## Быстрый старт

### Требования

- Python **≥ 3.12** (проверено на 3.12 и 3.14)
- Git

### Установка

Windows (PowerShell):

```powershell
git clone <repo-url>
cd lrPython
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

`-e` — editable-установка для разработки, `[dev]` добавляет pytest, mypy и ruff. После установки доступна команда `school-lab` (то же самое: `python -m school_lab.cli`).

> Если PowerShell не даёт активировать окружение: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Проверка, что всё работает

```powershell
python -m pytest
school-lab import data\submissions.jsonl
```

Ожидается `140 passed` и JSON с 12 принятыми сдачами.

---

## ЛР 1 — Приём работ и расширяемые анализаторы

### Что делает

```
JSONL ──► JSONLSource ──► decode_json ──► parse_submission ──► SubmissionService ──► Repository
          (файл закрывается    (синтаксис)     (схема,             (accepted /
           при любом выходе)                   Pydantic strict)     duplicate / conflict)
                                                                         │
AnalysisReport ◄── validate_report ◄── analyzer.analyze ◄── AnalyzerRegistry ◄── AnalysisService
                   (хеши, config_hash,   (submission +         (выбор по имени,
                    границы evidence)     AnalysisContext)      без if/elif)
```

- **Сдача неизменяема.** Тот же `submission_id` и то же содержимое → `duplicate`; другое содержимое → `conflict`, оригинал не перезаписывается. Новая версия работы — новый `submission_id`.
- **Частичный успех импорта.** Ошибочная строка попадает в отчёт с номером строки и файлом, остальные обрабатываются.
- **Отчёт привязан к версиям:** `submission_hash` (SHA-256 канонического JSON), `analyzer_id`, `analyzer_version`, `config_hash`.

### Команды

**Импорт** одного или нескольких JSONL-файлов в общий in-memory репозиторий:

```powershell
school-lab import data\submissions.jsonl
school-lab import data\submissions.jsonl data\invalid_submissions.jsonl
school-lab import data\submissions.jsonl --manifest out\manifest.json
```

| Аргумент | Описание |
|---|---|
| `paths` | Один или несколько JSONL-файлов |
| `--manifest PATH` | Сохранить manifest корпуса: id, хеши, версия обработки |

**Анализ** — импорт и запуск анализаторов по принятым сдачам:

```powershell
school-lab analyze data\submissions.jsonl --assignments data\assignments.json --config configs\llm.toml
school-lab analyze data\submissions.jsonl --assignments data\assignments.json --config configs\ml.toml --analyzer length --analyzer template --submission sub-007
```

| Аргумент | Описание |
|---|---|
| `paths` | JSONL-файлы сдач |
| `--assignments` | JSON-справочник заданий (обязательный) |
| `--config` | TOML-конфигурация режима `llm` / `ml` (обязательный) |
| `--analyzer NAME` | Можно повторять; по умолчанию запускаются все |
| `--submission ID` | Можно повторять; по умолчанию все принятые сдачи |

Результат — один JSON в stdout, диагностика фатальных ошибок — в stderr.

| Код выхода | Значение |
|---|---|
| `0` | Без ошибок |
| `1` | Есть ошибки отдельных записей или отказы анализа; корректные записи обработаны |
| `2` | Работа невозможна: нет файла, неверная конфигурация, неизвестный анализатор |

### Данные

| Файл | Содержимое |
|---|---|
| `data/submissions.jsonl` | 12 корректных сдач (учебный корпус из лекции) |
| `data/invalid_submissions.jsonl` | 19 строк: дубликат, конфликт, битый JSON, пустая строка, повтор ключа, NaN, ошибки схемы |
| `data/assignments.json` | Задания: разрешённый шаблон кода и требования R1–R3 |

Контракт сдачи (`schema_version = 1`): непустые `submission_id`, `student_id`, `assignment_id`; `submitted_at` в ISO 8601 с часовым поясом; хотя бы одно из `text`/`code` непустое; `ai_declaration` с полями `used`, `tool`, `purpose`, `verified_by_student` (при `used=true` обязательны `tool` и `purpose`). Неизвестные поля и приведение типов запрещены.

| Код ошибки | Когда |
|---|---|
| `invalid_json` | Строка не разбирается: битый JSON, пустая строка, повтор ключа, NaN/Infinity |
| `schema_error` | JSON корректен, но нарушает контракт |
| `unsupported_version` | `schema_version` ≠ 1 |
| `conflict` | `submission_id` уже занят другим содержимым |

### Анализаторы

| Имя | Что делает | `kind` |
|---|---|---|
| `length` | Считает непустые строки text и code; evidence на каждую строку | `rubric_feedback` |
| `template` | Ищет точные блоки разрешённого шаблона; совпадение помечается как разрешённое | `similarity` |
| `declaration` | Проверяет заполненность AI-декларации при `used=true` | `rubric_feedback` |
| `requirements` | Локальный baseline: ищет подстроку каждого требования в коде | `rubric_feedback` |
| `model-stub` | Stub модели: вход готовится по режиму (LLM/ML), ответ проходит валидацию | `rubric_feedback` |

Во всех анализаторах `score = null`: обоснованной числовой метрики в ЛР 1 нет. Новый анализатор подключается одной строкой `registry.register(...)` в `src/school_lab/app.py`; `AnalysisService` при этом не меняется.

### AI-траектория

| Требование | Реализация |
|---|---|
| Корпус и manifest с id, хешами, версией обработки | `manifest.py`, `import --manifest` |
| Исходные text/code отделены от признаков | `preparation.py` строит payload, `Submission` frozen |
| `ai_declaration` не используется как метка | Не передаётся ни в prompt, ни в признаки |
| Режим ML или LLM | `configs/ml.toml` (`feature_schema_version`), `configs/llm.toml` (`prompt_template_version`) |
| Интерфейсы подготовки входа и feedback | `InputPreparer`, `FeedbackGenerator`, `ModelAdapter` |
| Baseline и stub с одним контрактом результата | `RequirementsBaseline`, `LocalModelStub` → `ModelFeedback` v1 |
| `config_hash` | SHA-256 от задания и конфигурации режима |

**Углублённый уровень:** одни и те же контрактные тесты для `requirements` и `model-stub` в обоих режимах; ответ модели проверяется до создания отчёта (схема, лишние поля, набор критериев, ссылки evidence); `schema_version = 2` и неполный ответ отклоняются.

### Конфигурация

```toml
# configs/llm.toml
mode = "llm"
prompt_template_version = "prompt-v1"

# configs/ml.toml
mode = "ml"
feature_schema_version = "features-v1"
```

Неизвестная версия шаблона или схемы признаков отклоняется при сборке приложения, до обработки первой сдачи (exit 2).

### Ограничения

- Хранилище in-memory: данные живут до конца процесса (SQLite — ЛР 3).
- Проверка `get` → `add` в репозитории не атомарна между потоками (ЛР 3).
- `template` и `requirements` ищут точные совпадения: другое форматирование или имя переменной не распознаётся (сходство — ЛР 2).
- Stub не оценивает решение и проверяет только программную связку; реальной модели нет.
- Плагины-анализаторы выполняются с правами процесса; проверяется результат, а не код плагина.
- Размер строки JSONL не ограничивается.

---

## Проверки качества

```powershell
python -m pytest                 # 140 тестов
python -m pytest -v -k contract  # только контрактные тесты
mypy                             # строгая проверка типов (src, tests, scripts)
ruff check .                     # линтер
ruff format --check .            # форматирование
```

Замеры ЛР 1 (результаты — в `reports/lab1_bench.json`):

```powershell
python scripts/bench_lab1.py --out reports/lab1_bench.json
```

Проверка установки в чистое окружение (без `-e`, вне каталога проекта):

```powershell
py -3.14 -m venv $env:TEMP\clean
& $env:TEMP\clean\Scripts\python.exe -m pip install .
cd $env:TEMP
& $env:TEMP\clean\Scripts\school-lab.exe import <путь-к-проекту>\data\submissions.jsonl
```

---

## Структура проекта

```
├── configs/                  # режимы анализа: llm.toml, ml.toml
├── data/                     # учебный корпус, проблемные строки, задания
├── reports/                  # отчёты по лабораторным и результаты замеров
├── scripts/                  # скрипты замеров
├── src/school_lab/
│   ├── errors.py             # SubmissionError, AnalysisFailure, ConfigError
│   ├── models.py             # Submission, Assignment, Evidence, Finding, AnalysisReport
│   ├── parsing.py            # строгий JSON, валидация сдачи, загрузка заданий
│   ├── hashing.py            # канонический JSON, SHA-256
│   ├── lines.py              # номера строк, поиск блоков шаблона
│   ├── repositories.py       # протоколы и in-memory хранилища
│   ├── sources.py            # JSONLSource, InMemorySource
│   ├── services.py           # приём, импорт, запуск анализа
│   ├── contracts.py          # Analyzer, AnalysisContext, реестр, validate_report
│   ├── analyzers.py          # length, template, declaration
│   ├── config.py             # LLMConfig / MLConfig
│   ├── preparation.py        # подготовка входа модели (prompt / features)
│   ├── feedback.py           # baseline требований, stub модели, проверка ответа
│   ├── manifest.py           # manifest корпуса
│   ├── app.py                # сборка зависимостей
│   └── cli.py                # команды import и analyze
├── tests/                    # unit, контрактные и интеграционные тесты
└── pyproject.toml
```

---

## Технологический стек

| Слой | Технологии |
|---|---|
| Язык | Python 3.12+ |
| Модели и валидация | Pydantic 2 (strict, frozen, extra=forbid) |
| Тесты | pytest |
| Качество кода | mypy (strict), ruff |
| Сборка | setuptools, pyproject.toml, console script |
