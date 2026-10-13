import json
from pathlib import Path

import pytest
from conftest import CONFIG_DIR, DATA_DIR

from school_lab.cli import main


def test_import_ok(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    code = main(["import", str(DATA_DIR / "submissions.jsonl"), "--manifest", str(manifest)])
    out, err = capsys.readouterr()
    assert code == 0 and err == ""
    result = json.loads(out)  # stdout - ровно один JSON
    assert len(result["accepted"]) == 12
    assert json.loads(manifest.read_text(encoding="utf-8"))["count"] == 12


def test_import_with_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["import", str(DATA_DIR / "submissions.jsonl"), str(DATA_DIR / "invalid_submissions.jsonl")])
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["duplicate"] == ["sub-001"]
    conflict = next(e for e in result["errors"] if e["code"] == "conflict")
    assert conflict["line_no"] == 2 and conflict["source"].endswith("invalid_submissions.jsonl")


def test_missing_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["import", str(tmp_path / "nope.jsonl")])
    out, err = capsys.readouterr()
    assert code == 2 and out == ""
    assert json.loads(err)["code"] == "source_unavailable"


ANALYZE = [
    "analyze",
    str(DATA_DIR / "submissions.jsonl"),
    "--assignments",
    str(DATA_DIR / "assignments.json"),
]


@pytest.mark.parametrize("mode", ["llm", "ml"])
def test_analyze(capsys: pytest.CaptureFixture[str], mode: str) -> None:
    code = main([*ANALYZE, "--config", str(CONFIG_DIR / f"{mode}.toml"), "--submission", "sub-001"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["failures"] == []
    assert sorted(r["analyzer_id"] for r in result["reports"]) == sorted(
        ["length", "template", "declaration", "requirements", "model-stub"]
    )


def test_analyze_unknown_analyzer(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([*ANALYZE, "--config", str(CONFIG_DIR / "llm.toml"), "--analyzer", "magic"])
    out, err = capsys.readouterr()
    assert code == 2 and out == "" and json.loads(err)["code"] == "config_error"


def test_analyze_bad_config(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('mode = "llm"\nprompt_template_version = "prompt-v999"\n', encoding="utf-8")
    code = main([*ANALYZE, "--config", str(bad)])
    assert code == 2 and json.loads(capsys.readouterr().err)["code"] == "config_error"
