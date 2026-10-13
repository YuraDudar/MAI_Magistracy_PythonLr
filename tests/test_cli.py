import json
from pathlib import Path

import pytest
from conftest import DATA_DIR

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
