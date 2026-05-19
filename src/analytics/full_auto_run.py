"""
full_auto_run.py
================
One-command orchestrator for full automatic data -> OLAP -> agent readiness flow.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable


def _resolve_default_paths() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    project_root = repo_root.parent
    mock_dir = project_root / "mock database"
    return {
        "etl_script": str(mock_dir / "load_mock_to_dw.py"),
        "source_sqlite": str(mock_dir / "magasin_mock.db"),
        "olap_output_dir": str(repo_root / "generated_olap"),
    }


def build_pipeline_commands(
    *,
    python_executable: str,
    etl_script: str,
    source_sqlite: str,
    olap_output_dir: str,
    process_ssas: bool,
    ssas_command: str,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "name": "etl_load_to_dw",
            "command": [python_executable, etl_script],
            "required": True,
        },
        {
            "name": "auto_olap_modeling",
            "command": [
                python_executable,
                str(Path(__file__).resolve().parent / "auto_olap_pipeline.py"),
                "--source-sqlite",
                source_sqlite,
                "--output-dir",
                olap_output_dir,
            ],
            "required": True,
        },
    ]
    if process_ssas:
        commands.append(
            {
                "name": "process_ssas_cube",
                "command": ssas_command,
                "required": False,
                "shell": True,
            }
        )
    return commands


def _run_command(
    command_spec: dict[str, Any],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    cmd = command_spec["command"]
    shell = bool(command_spec.get("shell", False))
    result = runner(cmd, shell=shell, capture_output=True, text=True)
    ok = result.returncode == 0
    return {
        "name": command_spec["name"],
        "ok": ok,
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "command": cmd,
        "required": command_spec.get("required", True),
    }


def run_full_auto_pipeline(
    *,
    python_executable: str,
    etl_script: str,
    source_sqlite: str,
    olap_output_dir: str,
    process_ssas: bool = False,
    ssas_command: str = "",
    dry_run: bool = False,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    Path(olap_output_dir).mkdir(parents=True, exist_ok=True)
    commands = build_pipeline_commands(
        python_executable=python_executable,
        etl_script=etl_script,
        source_sqlite=source_sqlite,
        olap_output_dir=olap_output_dir,
        process_ssas=process_ssas,
        ssas_command=ssas_command,
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "steps": commands}

    step_results: list[dict[str, Any]] = []
    for step in commands:
        res = _run_command(step, runner=runner)
        step_results.append(res)
        if not res["ok"] and step.get("required", True):
            return {"ok": False, "steps": step_results, "failed_step": step["name"]}
    return {"ok": True, "steps": step_results}


def olap_refresh_required(source_sqlite: str, olap_output_dir: str) -> bool:
    source = Path(source_sqlite)
    semantic_model = Path(olap_output_dir) / "semantic_model.json"
    if not source.exists():
        return False
    if not semantic_model.exists():
        return True
    return source.stat().st_mtime > semantic_model.stat().st_mtime


def ensure_olap_readiness(
    *,
    python_executable: str,
    etl_script: str,
    source_sqlite: str,
    olap_output_dir: str,
    auto_refresh_enabled: bool,
    force_refresh: bool = False,
    process_ssas: bool = False,
    ssas_command: str = "",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    required = force_refresh or olap_refresh_required(source_sqlite, olap_output_dir)
    if not auto_refresh_enabled:
        return {"ok": True, "skipped": True, "reason": "auto_refresh_disabled", "refresh_required": required}
    if not required:
        return {"ok": True, "skipped": True, "reason": "up_to_date", "refresh_required": False}
    result = run_full_auto_pipeline(
        python_executable=python_executable,
        etl_script=etl_script,
        source_sqlite=source_sqlite,
        olap_output_dir=olap_output_dir,
        process_ssas=process_ssas,
        ssas_command=ssas_command,
        dry_run=False,
        runner=runner,
    )
    result["refresh_required"] = True
    return result


def _status_file(olap_output_dir: str) -> Path:
    return Path(olap_output_dir) / "refresh_status.json"


def _lock_file(olap_output_dir: str) -> Path:
    return Path(olap_output_dir) / ".refresh.lock"


def _write_status(olap_output_dir: str, payload: dict[str, Any]) -> None:
    status_path = _status_file(olap_output_dir)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_status(olap_output_dir: str) -> dict[str, Any] | None:
    status_path = _status_file(olap_output_dir)
    if not status_path.exists():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _acquire_refresh_lock(olap_output_dir: str, run_id: str) -> bool:
    lock_path = _lock_file(olap_output_dir)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(run_id)
        return True
    except FileExistsError:
        return False


def _release_refresh_lock(olap_output_dir: str) -> None:
    lock_path = _lock_file(olap_output_dir)
    if lock_path.exists():
        lock_path.unlink(missing_ok=True)


def ensure_olap_readiness_async(
    *,
    python_executable: str,
    etl_script: str,
    source_sqlite: str,
    olap_output_dir: str,
    auto_refresh_enabled: bool,
    force_refresh: bool = False,
    process_ssas: bool = False,
    ssas_command: str = "",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    required = force_refresh or olap_refresh_required(source_sqlite, olap_output_dir)
    if not auto_refresh_enabled:
        return {"ok": True, "scheduled": False, "reason": "auto_refresh_disabled", "refresh_required": required}
    if not required:
        return {"ok": True, "scheduled": False, "reason": "up_to_date", "refresh_required": False}

    run_id = f"refresh-{uuid.uuid4()}"
    if not _acquire_refresh_lock(olap_output_dir, run_id):
        return {"ok": True, "scheduled": False, "reason": "refresh_already_running", "refresh_required": True}

    started_at = int(time.time())
    _write_status(
        olap_output_dir,
        {"state": "running", "run_id": run_id, "started_at": started_at, "refresh_required": True},
    )

    def _worker() -> None:
        try:
            result = run_full_auto_pipeline(
                python_executable=python_executable,
                etl_script=etl_script,
                source_sqlite=source_sqlite,
                olap_output_dir=olap_output_dir,
                process_ssas=process_ssas,
                ssas_command=ssas_command,
                dry_run=False,
                runner=runner,
            )
            _write_status(
                olap_output_dir,
                {
                    "state": "success" if result.get("ok") else "failed",
                    "run_id": run_id,
                    "started_at": started_at,
                    "ended_at": int(time.time()),
                    "result": result,
                    "refresh_required": True,
                },
            )
        except Exception as exc:
            _write_status(
                olap_output_dir,
                {
                    "state": "failed",
                    "run_id": run_id,
                    "started_at": started_at,
                    "ended_at": int(time.time()),
                    "error": str(exc),
                    "refresh_required": True,
                },
            )
        finally:
            _release_refresh_lock(olap_output_dir)

    thread = threading.Thread(target=_worker, name="olap-refresh-worker", daemon=True)
    thread.start()
    atexit.register(_release_refresh_lock, olap_output_dir)
    return {
        "ok": True,
        "scheduled": True,
        "reason": "refresh_started_in_background",
        "run_id": run_id,
        "refresh_required": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    defaults = _resolve_default_paths()
    p = argparse.ArgumentParser(description="Run full automatic DW + OLAP preparation pipeline.")
    p.add_argument("--python-executable", default=sys.executable)
    p.add_argument("--etl-script", default=defaults["etl_script"])
    p.add_argument("--source-sqlite", default=defaults["source_sqlite"])
    p.add_argument("--olap-output-dir", default=defaults["olap_output_dir"])
    p.add_argument("--process-ssas", action="store_true")
    p.add_argument(
        "--ssas-command",
        default=os.getenv(
            "DIVALTO_SSAS_PROCESS_CMD",
            "",
        ),
        help="Optional shell command used to process SSAS cube after model generation.",
    )
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    if args.process_ssas and not args.ssas_command.strip():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "process-ssas requested but no ssas-command provided (or DIVALTO_SSAS_PROCESS_CMD).",
                }
            )
        )
        return 2

    result = run_full_auto_pipeline(
        python_executable=args.python_executable,
        etl_script=args.etl_script,
        source_sqlite=args.source_sqlite,
        olap_output_dir=args.olap_output_dir,
        process_ssas=args.process_ssas,
        ssas_command=args.ssas_command,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
