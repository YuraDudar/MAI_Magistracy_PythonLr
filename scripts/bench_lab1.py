"""Замеры ЛР 1: импорт, анализ и цена проверки ответа модели (углубление AI).

Запуск: python scripts/bench_lab1.py --out reports/lab1_bench.json
Масштабные корпуса синтетические: копии учебных сдач с новыми submission_id.
"""

import argparse
import copy
import json
import platform
import statistics
import sys
import tempfile
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from school_lab.app import build_application, make_preparer
from school_lab.config import load_config
from school_lab.contracts import AnalysisContext, validate_report
from school_lab.feedback import LocalModelStub, parse_feedback
from school_lab.parsing import load_assignments
from school_lab.services import import_source
from school_lab.sources import JSONLSource

ROOT = Path(__file__).resolve().parent.parent


def make_corpus(path: Path, size: int) -> None:
    """Синтетический JSONL из size сдач на основе 12 учебных."""
    base = [
        json.loads(line)
        for line in (ROOT / "data/submissions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    with path.open("w", encoding="utf-8") as handle:
        for i in range(size):
            item = copy.deepcopy(base[i % len(base)])
            item["submission_id"] = f"bench-{i:06d}"
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def median_ms(action: Callable[[], object], repeats: int) -> tuple[float, list[float]]:
    runs = []
    for _ in range(repeats):
        start = perf_counter()
        action()
        runs.append((perf_counter() - start) * 1000)
    return statistics.median(runs), runs


def bench_import(sizes: list[int], repeats: int, workdir: Path) -> list[dict[str, object]]:
    config = load_config(ROOT / "configs/llm.toml")
    assignments = load_assignments(ROOT / "data/assignments.json")
    rows = []
    for size in sizes:
        path = workdir / f"corpus_{size}.jsonl"
        make_corpus(path, size)

        def run(path: Path = path, size: int = size) -> None:
            app = build_application(config, assignments)
            summary = import_source(JSONLSource(path), app.submission_service)
            assert len(summary.accepted) == size

        median, runs = median_ms(run, repeats)
        tracemalloc.start()
        run()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "records": size,
                "median_ms": round(median, 1),
                "runs_ms": [round(r, 1) for r in runs],
                "per_record_us": round(median * 1000 / size, 1),
                "peak_mib": round(peak / 2**20, 2),
            }
        )
    return rows


def bench_analyzers(size: int, repeats: int, workdir: Path) -> list[dict[str, object]]:
    config = load_config(ROOT / "configs/llm.toml")
    app = build_application(config, load_assignments(ROOT / "data/assignments.json"))
    path = workdir / f"corpus_{size}.jsonl"
    make_corpus(path, size)
    import_source(JSONLSource(path), app.submission_service)
    ids = [s.submission_id for s in app.submissions.list_all()]
    rows = []
    for name in app.registry.names():

        def run_all(name: str = name) -> None:
            for submission_id in ids:
                app.analysis_service.run(submission_id, name)

        median, _ = median_ms(run_all, repeats)
        rows.append(
            {
                "analyzer": name,
                "submissions": size,
                "median_ms": round(median, 1),
                "per_submission_us": round(median * 1000 / size, 1),
            }
        )
    return rows


def bench_validation(repeats: int, calls: int) -> dict[str, object]:
    """Цена углубления: проверка ответа модели и отчёта на границе относительно полного анализа."""
    config = load_config(ROOT / "configs/llm.toml")
    assignments = load_assignments(ROOT / "data/assignments.json")
    app = build_application(config, assignments)
    raw = json.loads((ROOT / "data/submissions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    app.submission_service.accept(raw)
    submission = app.submissions.get("sub-001")
    assert submission is not None
    context = AnalysisContext(assignment=assignments[0], config=config)
    payload = make_preparer(config).prepare(submission, assignments[0])
    stub = LocalModelStub()
    response = stub.generate(payload)
    report = app.analysis_service.run("sub-001", "model-stub")

    def per_call(action: Callable[[], object]) -> float:
        median, _ = median_ms(lambda: [action() for _ in range(calls)], repeats)
        return round(median * 1000 / calls, 1)

    return {
        "calls": calls,
        "stub_generate_us": per_call(lambda: stub.generate(payload)),
        "parse_feedback_us": per_call(lambda: parse_feedback(response, assignments[0])),
        "validate_report_us": per_call(lambda: validate_report(report, submission, context)),
        "full_model_stub_run_us": per_call(lambda: app.analysis_service.run("sub-001", "model-stub")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        result = {
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "processor": platform.processor() or platform.machine(),
            },
            "repeats": args.repeats,
            "import": bench_import(args.sizes, args.repeats, workdir),
            "analyzers": bench_analyzers(1000, args.repeats, workdir),
            "validation": bench_validation(args.repeats, calls=2000),
        }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
