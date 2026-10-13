"""CLI: разбор аргументов, сборка зависимостей, вывод JSON в stdout и диагностики в stderr.
Коды завершения: 0 - без ошибок, 1 - ошибки отдельных записей, 2 - источник или конфигурация недоступны."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from school_lab.app import build_application
from school_lab.config import load_config
from school_lab.errors import AnalysisFailure, ConfigError
from school_lab.manifest import build_manifest, write_manifest
from school_lab.parsing import load_assignments
from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import ImportSummary, SubmissionService, import_source
from school_lab.sources import JSONLSource


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _fail(code: str, message: str) -> int:
    print(json.dumps({"code": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    return 2


def _import_files(paths: Sequence[Path], service: SubmissionService) -> ImportSummary:
    """Импорт нескольких файлов в один репозиторий; у ошибок указывается файл-источник."""
    total = ImportSummary()
    for path in paths:
        summary = import_source(JSONLSource(path), service)
        total.accepted += summary.accepted
        total.duplicate += summary.duplicate
        for error in summary.errors:
            total.errors.append({**error, "source": str(path)})
    return total


def _cmd_import(args: argparse.Namespace) -> int:
    repository = InMemorySubmissionRepository()
    try:
        summary = _import_files(args.paths, SubmissionService(repository))
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))
    if args.manifest is not None:
        write_manifest(args.manifest, build_manifest(repository.list_all()))
    _print_json(summary.to_dict())
    return 1 if summary.errors else 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    try:
        app = build_application(load_config(args.config), load_assignments(args.assignments))
    except ConfigError as exc:
        return _fail("config_error", str(exc))
    names = args.analyzer or list(app.registry.names())
    unknown = sorted(set(names) - set(app.registry.names()))
    if unknown:
        return _fail("config_error", f"Неизвестные анализаторы: {unknown}")
    try:
        summary = _import_files(args.paths, app.submission_service)
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))

    ids = args.submission or [s.submission_id for s in app.submissions.list_all()]
    reports: list[object] = []
    failures: list[dict[str, str]] = []
    for submission_id in ids:
        for name in names:
            try:
                report = app.analysis_service.run(submission_id, name)
            except AnalysisFailure as exc:
                failures.append({"submission_id": submission_id, "analyzer": name, **exc.to_dict()})
            else:
                reports.append(report.model_dump(mode="json"))
    _print_json({"import": summary.to_dict(), "reports": reports, "failures": failures})
    return 1 if summary.errors or failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="school-lab", description="Приём учебных сдач и анализ")
    commands = parser.add_subparsers(dest="command", required=True)

    import_cmd = commands.add_parser("import", help="Импорт JSONL-файлов сдач")
    import_cmd.add_argument("paths", nargs="+", type=Path)
    import_cmd.add_argument("--manifest", type=Path, help="Куда сохранить manifest корпуса")
    import_cmd.set_defaults(handler=_cmd_import)

    analyze_cmd = commands.add_parser("analyze", help="Импорт и анализ сдач")
    analyze_cmd.add_argument("paths", nargs="+", type=Path)
    analyze_cmd.add_argument("--assignments", type=Path, required=True, help="JSON-справочник заданий")
    analyze_cmd.add_argument("--config", type=Path, required=True, help="TOML-конфигурация режима llm/ml")
    analyze_cmd.add_argument("--analyzer", action="append", help="Имя анализатора (по умолчанию все)")
    analyze_cmd.add_argument("--submission", action="append", help="Анализировать только эти submission_id")
    analyze_cmd.set_defaults(handler=_cmd_analyze)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.handler(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
