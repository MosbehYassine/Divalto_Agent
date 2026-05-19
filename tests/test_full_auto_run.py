import os
import sys
import time
from pathlib import Path

_TESTS_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.abspath(os.path.join(_TESTS_DIR, "..", "src"))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from analytics.full_auto_run import (  # noqa: E402
    _read_status,
    build_pipeline_commands,
    ensure_olap_readiness,
    ensure_olap_readiness_async,
    olap_refresh_required,
    run_full_auto_pipeline,
)


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_pipeline_commands_without_ssas():
    cmds = build_pipeline_commands(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite="demo.db",
        olap_output_dir="out",
        process_ssas=False,
        ssas_command="",
    )
    assert len(cmds) == 2
    assert cmds[0]["name"] == "etl_load_to_dw"
    assert cmds[1]["name"] == "auto_olap_modeling"


def test_build_pipeline_commands_with_ssas():
    cmds = build_pipeline_commands(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite="demo.db",
        olap_output_dir="out",
        process_ssas=True,
        ssas_command="echo process",
    )
    assert len(cmds) == 3
    assert cmds[-1]["name"] == "process_ssas_cube"


def test_run_full_auto_pipeline_dry_run():
    result = run_full_auto_pipeline(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite="demo.db",
        olap_output_dir="out",
        dry_run=True,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert len(result["steps"]) == 2


def test_run_full_auto_pipeline_stops_on_required_failure(tmp_path):
    calls = {"n": 0}

    def fake_runner(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeCompleted(returncode=1, stderr="etl failed")
        return _FakeCompleted(returncode=0, stdout="ok")

    result = run_full_auto_pipeline(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite="demo.db",
        olap_output_dir=str(tmp_path / "out"),
        dry_run=False,
        runner=fake_runner,
    )
    assert result["ok"] is False
    assert result["failed_step"] == "etl_load_to_dw"
    assert len(result["steps"]) == 1


def test_olap_refresh_required_when_semantic_missing(tmp_path):
    source = tmp_path / "source.db"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    assert olap_refresh_required(str(source), str(out)) is True


def test_olap_refresh_required_when_source_newer(tmp_path):
    source = tmp_path / "source.db"
    out = tmp_path / "out"
    out.mkdir()
    semantic = out / "semantic_model.json"
    semantic.write_text("{}", encoding="utf-8")
    time.sleep(0.01)
    source.write_text("x", encoding="utf-8")
    assert olap_refresh_required(str(source), str(out)) is True


def test_ensure_olap_readiness_skips_when_disabled(tmp_path):
    source = tmp_path / "source.db"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    result = ensure_olap_readiness(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite=str(source),
        olap_output_dir=str(out),
        auto_refresh_enabled=False,
    )
    assert result["ok"] is True
    assert result["skipped"] is True


def test_ensure_olap_readiness_runs_when_required(tmp_path):
    source = tmp_path / "source.db"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    def fake_runner(*args, **kwargs):
        return _FakeCompleted(returncode=0, stdout="ok")

    result = ensure_olap_readiness(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite=str(source),
        olap_output_dir=str(out),
        auto_refresh_enabled=True,
        runner=fake_runner,
    )
    assert result["ok"] is True
    assert result["refresh_required"] is True


def test_ensure_olap_readiness_async_starts_background(tmp_path):
    source = tmp_path / "source.db"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    def fake_runner(*args, **kwargs):
        return _FakeCompleted(returncode=0, stdout="ok")

    result = ensure_olap_readiness_async(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite=str(source),
        olap_output_dir=str(out),
        auto_refresh_enabled=True,
        runner=fake_runner,
    )
    assert result["ok"] is True
    assert result["scheduled"] is True
    # Background thread scheduling can be slightly delayed on CI/Windows.
    status = None
    for _ in range(20):
        status = _read_status(str(out))
        if status is not None:
            break
        time.sleep(0.01)
    assert status is not None
    assert status["state"] in {"running", "success", "failed"}


def test_ensure_olap_readiness_async_skip_when_disabled(tmp_path):
    source = tmp_path / "source.db"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    result = ensure_olap_readiness_async(
        python_executable="python",
        etl_script="etl.py",
        source_sqlite=str(source),
        olap_output_dir=str(out),
        auto_refresh_enabled=False,
    )
    assert result["ok"] is True
    assert result["scheduled"] is False
