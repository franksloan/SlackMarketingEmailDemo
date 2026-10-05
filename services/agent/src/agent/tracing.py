import json
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TRACES_DIR = Path(__file__).parents[2] / "traces"


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Recursively serialize Pydantic models, dicts, and lists to JSON-safe types."""
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Per-run accumulator
# ---------------------------------------------------------------------------

@dataclass
class _RunTrace:
    run_id: str
    user_request: str
    started_at: datetime
    node_entries: list[dict] = field(default_factory=list)


# Context variable — holds the active _RunTrace for the current async task tree
_current_run: ContextVar[_RunTrace | None] = ContextVar("_current_run", default=None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_run(user_request: str) -> str:
    """
    Begin a new trace run. Call once at the top of process_request.
    Returns the run_id.
    """
    run = _RunTrace(
        run_id=str(uuid.uuid4()),
        user_request=user_request,
        started_at=datetime.now(timezone.utc),
    )
    _current_run.set(run)
    return run.run_id


def finish_run() -> Path | None:
    """
    Close the current run, write the consolidated trace file, and return its path.
    Call in a finally block at the end of process_request.
    """
    run = _current_run.get()
    if run is None:
        return None

    _TRACES_DIR.mkdir(parents=True, exist_ok=True)

    completed_at = datetime.now(timezone.utc)
    total_duration_ms = (completed_at - run.started_at).total_seconds() * 1000

    nodes_called = [
        e["node"] if not e.get("label") else f"{e['node']}:{e['label']}"
        for e in run.node_entries
    ]

    trace = {
        "run_id": run.run_id,
        "user_request": run.user_request,
        "started_at": run.started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "total_duration_ms": round(total_duration_ms, 2),
        "nodes_called": nodes_called,
        "nodes": run.node_entries,
    }

    ts = run.started_at.strftime("%Y%m%d_%H%M%S")
    path = _TRACES_DIR / f"{ts}_{run.run_id[:8]}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, default=str)

    _current_run.set(None)
    return path


def save_trace(
    node: str,
    inputs: dict[str, Any],
    thinking_and_reasoning: str,
    outputs: dict[str, Any],
    duration_ms: float,
    label: str | None = None,
) -> None:
    """
    Append a node trace entry to the current run.
    Falls back to writing an individual file if no run is active (e.g. tests).
    """
    entry = {
        "node": node,
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round(duration_ms, 2),
        "inputs": _serialize(inputs),
        "thinking_and_reasoning": thinking_and_reasoning,
        "outputs": _serialize(outputs),
    }

    run = _current_run.get()
    if run is not None:
        run.node_entries.append(entry)
    else:
        # Fallback: write individual file for test / standalone use
        _TRACES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        suffix = f"_{label}" if label else ""
        path = _TRACES_DIR / f"{ts}_{node}{suffix}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, default=str)


def start_timer() -> float:
    """Return a start timestamp for use with elapsed_ms()."""
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    """Return milliseconds elapsed since start_timer()."""
    return (time.perf_counter() - start) * 1000
