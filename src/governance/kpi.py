from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


@dataclass(slots=True)
class AuditAggregate:
    runs: int
    ws_attempts: int
    ws_failures: int
    plan_blocked: int
    hitl_signals: int
    avg_duration_ms: float | None


def _read_jsonl(path: Path, *, limit: int) -> Iterable[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    emitted = 0
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
                emitted += 1
                if emitted >= limit:
                    break
    return rows


def summarize_audit_file(path: str | Path, *, max_records: int = 5_000) -> AuditAggregate:
    """
    Cheap offline KPI rollup over persisted JSONL audits (Phase 7 observability helpers).

    *Exactness / business accuracy* is not derivable without labelled evaluation suites—see Phase 7 doc.
    """
    file_path = Path(path).expanduser()
    records = list(_read_jsonl(file_path, limit=max_records))
    durations: list[float] = []
    ws_attempts = 0
    ws_failures = 0
    blocked = 0
    advisory_hits = 0

    for record in records:
        duration_value = record.get("duration_ms")
        if isinstance(duration_value, (int, float)):
            durations.append(float(duration_value))

        execution = record.get("execution")
        if isinstance(execution, dict):
            inner_gov = execution.get("governance")
            if isinstance(inner_gov, dict) and inner_gov.get("plan_blocked"):
                blocked += 1

            steps = execution.get("steps")
            if isinstance(steps, list):
                ws_attempts += len(steps)
                ws_failures += sum(1 for step in steps if isinstance(step, dict) and step.get("ok") is False)

        top_meta = record.get("governance")
        if isinstance(top_meta, dict):
            signals = top_meta.get("signals")
            if isinstance(signals, list):
                advisory_hits += len(signals)

    avg_duration = mean(durations) if durations else None
    return AuditAggregate(
        runs=len(records),
        ws_attempts=ws_attempts,
        ws_failures=ws_failures,
        plan_blocked=blocked,
        hitl_signals=advisory_hits,
        avg_duration_ms=avg_duration,
    )
