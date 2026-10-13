"""CLI: разбор аргументов, сборка зависимостей, вывод JSON в stdout и диагностики в stderr.
Коды завершения: 0 - без ошибок, 1 - ошибки отдельных записей, 2 - источник или конфигурация недоступны."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from school_lab.manifest import build_manifest, write_manifest
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="school-lab", description="Приём учебных сдач и анализ")
    commands = parser.add_subparsers(dest="command", required=True)

    import_cmd = commands.add_parser("import", help="Импорт JSONL-файлов сдач")
    import_cmd.add_argument("paths", nargs="+", type=Path)
    import_cmd.add_argument("--manifest", type=Path, help="Куда сохранить manifest корпуса")
    import_cmd.set_defaults(handler=_cmd_import)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.handler(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
