"""Per-invocation token and cost observability for the autonomy runner.

Only metadata is persisted: no prompts, responses, headers or secrets.  The
Claude Code JSON result does not expose the provider's exact request count, so
``request_count`` stays ``None`` unless the producer supplies it; ``num_turns``
is recorded separately and must not be presented as an exact API request
count.  Provider-reported and Claude-reported values keep an explicit source.

The journal is an append-only event log: ``invocation_started`` is written
before the child process starts and exactly one ``invocation_finished`` is
written for every terminal outcome.  Usage unknown for failures, timeouts and
interruptions is represented as ``None`` with ``usage_known=False``; it is
never replaced by zeros or an estimate.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomy.budget import Usage

PROVIDER_REPORTED = "provider_reported"
CLAUDE_CODE = "claude_code"
ORCHESTRATOR = "orchestrator"

INVOCATIONS_FILE = "invocations.jsonl"
LOCK_FILE = "invocations.lock"
SCHEMA_VERSION = 2
STARTED_EVENT = "invocation_started"
FINISHED_EVENT = "invocation_finished"

TERMINAL_STATUSES = frozenset({"ok", "failed", "timeout", "cancelled", "interrupted", "unknown"})
ERROR_TYPES = frozenset(
    {
        "api_error",
        "invalid_output",
        "model_mismatch",
        "launch_error",
        "timeout",
        "operator_interrupt",
        "orchestrator_gone",
        "host_reboot",
        "pid_reused",
        "abandoned_unknown",
    }
)
TOKEN_FIELDS = (
    "input_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "output_tokens",
    "reasoning_tokens",
)
_COST_FIELD = "estimated_cost_usd"
_IDENTITY_FIELDS = (
    "task_id",
    "attempt_id",
    "agent_id",
    "role",
    "session_id",
    "model",
    "started_at",
    "retry_count",
)


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """Task binding supplied by the orchestrator for one model invocation."""

    task_id: str | None = None
    attempt_id: str | None = None
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class InvocationStart:
    """Metadata written before the child process is spawned."""

    invocation_id: str
    agent_id: str
    role: str
    model: str
    started_at: str | None
    task_id: str | None = None
    attempt_id: str | None = None
    retry_count: int = 0
    execution_channel: str = ORCHESTRATOR
    owner_pid: int | None = None
    owner_pid_start_ticks: int | None = None
    boot_id: str | None = None
    host: str | None = None
    usage_source: str = CLAUDE_CODE
    schema_version: int = SCHEMA_VERSION
    event: str = STARTED_EVENT

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InvocationMetrics:
    task_id: str | None
    attempt_id: str | None
    agent_id: str
    role: str
    session_id: str | None
    invocation_id: str
    model: str
    reported_models: tuple[str, ...]
    execution_channel: str
    request_count: int | None
    num_turns: int | None
    input_tokens: int | None
    cache_hit_tokens: int | None
    cache_miss_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    estimated_cost_usd: float | None
    started_at: str | None
    finished_at: str | None
    status: str
    accepted_result: bool | None
    retry_count: int
    usage_source: str
    provider_request_count: int | None = None
    provider_cache_hit_tokens: int | None = None
    provider_cache_miss_tokens: int | None = None
    schema_version: int = SCHEMA_VERSION
    event: str = FINISHED_EVENT
    error_type: str | None = None
    exit_code: int | None = None
    is_error: bool | None = None
    usage_known: bool = True
    request_count_known: bool = False
    duration_seconds: float | None = None
    inferred: bool = False
    reconciled_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_run_result(
        cls,
        result: Any,
        *,
        task_id: str | None = None,
        attempt_id: str | None = None,
        retry_count: int = 0,
        accepted_result: bool | None = None,
    ) -> InvocationMetrics:
        return from_run_result(
            result,
            task_id=task_id,
            attempt_id=attempt_id,
            retry_count=retry_count,
            accepted_result=accepted_result,
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _model_usage_reasoning(model_usage: dict[str, Any]) -> int | None:
    found = False
    total = 0
    for entry in model_usage.values():
        if not isinstance(entry, dict):
            continue
        value = entry.get("reasoningTokens", entry.get("reasoning_tokens"))
        if isinstance(value, int) and not isinstance(value, bool):
            found = True
            total += max(0, value)
    return total if found else None


def _usage_is_known(model_usage: Any) -> bool:
    """True only when Claude reported at least one non-zero token value.

    Crash recovery can zero the cost fields of an error result; zeros alone
    are therefore not treated as reliable usage.
    """
    if not isinstance(model_usage, dict) or not model_usage:
        return False
    for entry in model_usage.values():
        if not isinstance(entry, dict):
            continue
        for key in (
            "inputTokens",
            "outputTokens",
            "cacheReadInputTokens",
            "cacheCreationInputTokens",
            "reasoningTokens",
            "reasoning_tokens",
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            value = entry.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return True
    return False


def _normalise_request_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _normalise_num_turns(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def from_outcome(
    *,
    invocation_id: str,
    agent: str,
    role: str,
    model: str,
    status: str,
    task_id: str | None = None,
    attempt_id: str | None = None,
    retry_count: int = 0,
    session_id: str | None = None,
    model_usage: dict[str, Any] | None = None,
    total_cost_usd: float | None = None,
    request_count: int | None = None,
    num_turns: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_seconds: float | None = None,
    error_type: str | None = None,
    exit_code: int | None = None,
    is_error: bool | None = None,
    usage_known: bool | None = None,
    accepted_result: bool | None = None,
    inferred: bool = False,
    reconciled_at: str | None = None,
    execution_channel: str = ORCHESTRATOR,
) -> InvocationMetrics:
    """Build a terminal record; unknown usage is stored as ``None``."""
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"unknown invocation status: {status}")
    if error_type is not None and error_type not in ERROR_TYPES:
        raise ValueError(f"unknown invocation error_type: {error_type}")
    model_usage = model_usage if isinstance(model_usage, dict) else {}
    known = _usage_is_known(model_usage) if usage_known is None else bool(usage_known)
    usage = Usage.from_model_usage(model_usage, total_cost_usd=total_cost_usd)
    request = _normalise_request_count(request_count)
    turns = _normalise_num_turns(num_turns)
    return InvocationMetrics(
        task_id=task_id,
        attempt_id=attempt_id,
        agent_id=str(agent or ""),
        role=str(role or ""),
        session_id=session_id,
        invocation_id=invocation_id,
        model=str(model or ""),
        reported_models=tuple(str(name) for name in model_usage),
        execution_channel=execution_channel,
        request_count=request,
        num_turns=turns,
        input_tokens=usage.input_tokens if known else None,
        cache_hit_tokens=usage.cache_read_tokens if known else None,
        cache_miss_tokens=(usage.input_tokens + usage.cache_creation_tokens) if known else None,
        output_tokens=usage.output_tokens if known else None,
        reasoning_tokens=_model_usage_reasoning(model_usage) if known else None,
        estimated_cost_usd=usage.cost_usd if known else None,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        accepted_result=accepted_result,
        retry_count=max(0, int(retry_count)),
        usage_source=CLAUDE_CODE,
        error_type=error_type,
        exit_code=exit_code,
        is_error=is_error,
        usage_known=known,
        request_count_known=request is not None,
        duration_seconds=duration_seconds,
        inferred=inferred,
        reconciled_at=reconciled_at,
    )


def from_run_result(
    result: Any,
    *,
    task_id: str | None = None,
    attempt_id: str | None = None,
    retry_count: int = 0,
    accepted_result: bool | None = None,
) -> InvocationMetrics:
    """Build a terminal record from a successful runner result."""
    return from_outcome(
        invocation_id=str(getattr(result, "invocation_id", "") or ""),
        agent=str(getattr(result, "agent", "") or ""),
        role=str(getattr(result, "role", "") or ""),
        model=str(getattr(result, "model", "") or ""),
        status="ok",
        task_id=task_id,
        attempt_id=attempt_id,
        retry_count=retry_count,
        session_id=getattr(result, "session_id", None),
        model_usage=getattr(result, "model_usage", None),
        total_cost_usd=getattr(result, "total_cost_usd", None),
        request_count=getattr(result, "request_count", None),
        num_turns=getattr(result, "num_turns", None),
        started_at=getattr(result, "started_at", None),
        finished_at=getattr(result, "finished_at", None),
        duration_seconds=getattr(result, "duration_seconds", None),
        exit_code=getattr(result, "returncode", None),
        is_error=False,
        accepted_result=accepted_result,
    )


def from_failure(
    *,
    invocation_id: str,
    agent: str,
    role: str,
    model: str,
    status: str = "failed",
    error_type: str | None = None,
    **kwargs: Any,
) -> InvocationMetrics:
    """Build a failed/timeout/cancelled/interrupted terminal record."""
    return from_outcome(
        invocation_id=invocation_id,
        agent=agent,
        role=role,
        model=model,
        status=status,
        error_type=error_type,
        **kwargs,
    )


def boot_id() -> str | None:
    """Return the host boot id used to detect a reboot; ``None`` if unavailable."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def pid_start_ticks(pid: int | None) -> int | None:
    """Return field 22 of ``/proc/<pid>/stat`` for PID-reuse detection."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 2 :].split()
    # After comm/state, field 22 (starttime) is index 19 of the remainder.
    if len(fields) <= 19:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def _probe_pid(pid: int | None, start_ticks: int | None) -> str:
    if not isinstance(pid, int) or pid <= 0:
        return "unknown"
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return "dead"
    except OSError:
        return "unknown"
    close = raw.rfind(")")
    if close < 0:
        return "unknown"
    fields = raw[close + 2 :].split()
    if len(fields) <= 19:
        return "unknown"
    try:
        actual = int(fields[19])
    except ValueError:
        return "unknown"
    if start_ticks is not None and actual != start_ticks:
        return "reused"
    return "alive"


def _append_record(root: Path, payload: dict[str, Any]) -> Path:
    """Append one newline-terminated record under an advisory writer lock."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / INVOCATIONS_FILE
    lock_path = root / LOCK_FILE
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                written = 0
                while written < len(data):
                    chunk = os.write(fd, data[written:])
                    if chunk <= 0:
                        raise OSError("short write to invocation journal")
                    written += chunk
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return path


def record_started(root: Path, start: InvocationStart) -> Path:
    return _append_record(root, start.as_dict())


def record_finished(root: Path, metrics: InvocationMetrics) -> Path:
    """Append one terminal record; never persist prompt/response content."""
    return _append_record(root, metrics.as_dict())


def record_invocation(root: Path, metrics: InvocationMetrics) -> Path:
    """Compatibility alias for the pre-lifecycle terminal writer."""
    return record_finished(root, metrics)


def read_invocations(root: Path, *, include_corrupt: bool = False) -> list[dict[str, Any]]:
    path = Path(root) / INVOCATIONS_FILE
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    skipped = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines(keepends=True)
    for index, raw in enumerate(lines):
        if not raw.endswith("\n") and index == len(lines) - 1:
            # A crash can leave a partial tail; it is not a complete record.
            skipped += 1
            continue
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            skipped += 1
    if include_corrupt and skipped:
        records.append({"corrupt_lines": skipped})
    return records


def _normalise_finish(record: dict[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.setdefault("event", FINISHED_EVENT)
    value.setdefault("schema_version", 1)
    value.setdefault("inferred", False)
    value.setdefault("usage_known", True)
    raw_request = value.get("request_count")
    value.setdefault(
        "request_count_known",
        isinstance(raw_request, int) and not isinstance(raw_request, bool),
    )
    status = value.get("status")
    if status in (None, ""):
        value["status"] = "ok"
    elif status == "error":
        value["status"] = "failed"
    if value.get("event") != FINISHED_EVENT:
        value["event"] = FINISHED_EVENT
    return value


def reconstruct_invocations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge start/finish events into one record per ``invocation_id``.

    Legacy terminal-only records remain authoritative.  An inferred terminal
    never overrides an authoritative one; duplicates keep the first event.
    """
    starts: dict[str, dict[str, Any]] = {}
    authoritative: dict[str, dict[str, Any]] = {}
    inferred: dict[str, dict[str, Any]] = {}
    anonymous = 0
    for record in records:
        if set(record) == {"corrupt_lines"}:
            continue
        event = record.get("event")
        invocation_id = str(record.get("invocation_id") or "")
        if not invocation_id:
            invocation_id = f"anonymous:{anonymous}"
            anonymous += 1
        if event == STARTED_EVENT:
            starts.setdefault(invocation_id, dict(record))
            continue
        normalised = _normalise_finish(record)
        if normalised.get("inferred") is True:
            inferred.setdefault(invocation_id, normalised)
        else:
            authoritative.setdefault(invocation_id, normalised)

    merged: list[dict[str, Any]] = []
    for invocation_id in sorted(set(starts) | set(authoritative) | set(inferred)):
        start = starts.get(invocation_id)
        finish = authoritative.get(invocation_id) or inferred.get(invocation_id)
        value: dict[str, Any] = dict(start or {})
        if finish is not None:
            for key, item in finish.items():
                if item is None and value.get(key) is not None and key in _IDENTITY_FIELDS:
                    continue
                value[key] = item
            value["event"] = FINISHED_EVENT
            value.setdefault("status", "ok")
            value.setdefault("usage_known", True)
        else:
            value["event"] = STARTED_EVENT
            value["status"] = "started"
            value["usage_known"] = False
            value["inferred"] = False
            for key in (*TOKEN_FIELDS, _COST_FIELD):
                value.setdefault(key, None)
            for key in (
                "finished_at",
                "duration_seconds",
                "reconciled_at",
                "error_type",
                "exit_code",
                "session_id",
                "request_count",
                "num_turns",
            ):
                value.setdefault(key, None)
        value["invocation_id"] = invocation_id
        value["usage_known"] = bool(value.get("usage_known", True))
        value["inferred"] = bool(value.get("inferred", False))
        merged.append(value)
    return merged


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _stale_after_seconds() -> int:
    raw = os.environ.get("BA_INVOCATION_STALE_SECONDS", "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    try:
        timeout = int(os.environ.get("BA_MODEL_TIMEOUT", "900"))
    except ValueError:
        timeout = 900
    return max(60, timeout * 2 + 300)


def reconcile_invocations(
    root: Path,
    *,
    now: datetime | str | None = None,
    current_boot_id: str | None = None,
    pid_probe: Any = None,
    stale_after_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Close started invocations whose owner/host is provably gone.

    The function is idempotent: once a terminal record exists, the invocation
    is skipped.  A live owner process is never touched.
    """
    records = read_invocations(root)
    starts: dict[str, dict[str, Any]] = {}
    finished: set[str] = set()
    for record in records:
        if set(record) == {"corrupt_lines"}:
            continue
        invocation_id = str(record.get("invocation_id") or "")
        if not invocation_id:
            continue
        if record.get("event") == STARTED_EVENT:
            starts.setdefault(invocation_id, record)
        else:
            finished.add(invocation_id)

    moment = _parse_iso(now) if not isinstance(now, datetime) else now
    if moment is None:
        moment = datetime.now(UTC)
    elif moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    boot = current_boot_id if current_boot_id is not None else boot_id()
    stale = stale_after_seconds if stale_after_seconds is not None else _stale_after_seconds()
    probe = pid_probe or _probe_pid

    written: list[dict[str, Any]] = []
    for invocation_id, start in starts.items():
        if invocation_id in finished:
            continue
        status: str | None = None
        error_type: str | None = None
        record_boot = start.get("boot_id")
        if record_boot and boot and record_boot != boot:
            status, error_type = "interrupted", "host_reboot"
        else:
            owner_pid = start.get("owner_pid")
            owner_ticks = start.get("owner_pid_start_ticks")
            if isinstance(owner_pid, int) and owner_pid > 0:
                try:
                    state = probe(owner_pid, owner_ticks)
                except Exception:
                    state = "unknown"
                if state == "dead":
                    status, error_type = "interrupted", "orchestrator_gone"
                elif state == "reused":
                    status, error_type = "interrupted", "pid_reused"
                elif state == "alive":
                    continue
            if status is None:
                started_at = _parse_iso(start.get("started_at"))
                if started_at is None:
                    # No owner and no parseable start time: liveness cannot be
                    # verified, so do not leave the record pending forever.
                    status, error_type = "unknown", "abandoned_unknown"
                else:
                    age = (moment - started_at).total_seconds()
                    if age > stale:
                        status, error_type = "unknown", "abandoned_unknown"
        if status is None:
            continue
        metrics = from_failure(
            invocation_id=invocation_id,
            agent=str(start.get("agent_id") or ""),
            role=str(start.get("role") or ""),
            model=str(start.get("model") or ""),
            status=status,
            error_type=error_type,
            task_id=start.get("task_id"),
            attempt_id=start.get("attempt_id"),
            retry_count=int(start.get("retry_count") or 0),
            started_at=start.get("started_at"),
            finished_at=None,
            duration_seconds=None,
            exit_code=None,
            is_error=None,
            usage_known=False,
            inferred=True,
            reconciled_at=moment.isoformat(),
            execution_channel=str(start.get("execution_channel") or ORCHESTRATOR),
        )
        record_finished(root, metrics)
        written.append(metrics.as_dict())
    return written


def _number(value: Any) -> int | float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    return 0


def _bucket() -> dict[str, Any]:
    return {
        "invocations": 0,
        "request_count": 0,
        "request_count_known": 0,
        "input_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_usd": 0.0,
        "retry_count": 0,
        "usage_known_invocations": 0,
        "usage_unknown_invocations": 0,
    }


def summarize(
    records: list[dict[str, Any]],
    *,
    accepted_task_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Deduplicate and aggregate start/finish events by all report dimensions."""
    merged = reconstruct_invocations(records)
    totals = _bucket()
    totals.update(
        {
            "pending_invocations": 0,
            "inferred_invocations": 0,
        }
    )
    by_task: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_session: dict[str, dict[str, Any]] = {}
    by_status: dict[str, dict[str, Any]] = {}

    def add(bucket: dict[str, dict[str, Any]], key: str, record: dict[str, Any]) -> None:
        item = bucket.setdefault(key, _bucket())
        item["invocations"] += 1
        request_count = record.get("request_count")
        if isinstance(request_count, int) and not isinstance(request_count, bool):
            item["request_count"] += max(0, request_count)
            item["request_count_known"] += 1
        if record.get("usage_known"):
            for field in (*TOKEN_FIELDS, _COST_FIELD):
                item[field] += _number(record.get(field))
            item["usage_known_invocations"] += 1
        else:
            item["usage_unknown_invocations"] += 1
        item["retry_count"] += int(_number(record.get("retry_count")))

    for record in merged:
        status = str(record.get("status") or "unknown")
        if status not in TERMINAL_STATUSES:
            status = "pending" if status == "started" else status
        totals["invocations"] += 1
        request_count = record.get("request_count")
        if isinstance(request_count, int) and not isinstance(request_count, bool):
            totals["request_count"] += max(0, request_count)
            totals["request_count_known"] += 1
        if record.get("usage_known"):
            for field in (*TOKEN_FIELDS, _COST_FIELD):
                totals[field] += _number(record.get(field))
            totals["usage_known_invocations"] += 1
        else:
            totals["usage_unknown_invocations"] += 1
            if status == "pending":
                totals["pending_invocations"] += 1
        if record.get("inferred"):
            totals["inferred_invocations"] += 1
        totals["retry_count"] += int(_number(record.get("retry_count")))
        task_key = str(record.get("task_id") or "(unassigned)")
        role_key = str(record.get("role") or "(unknown)")
        agent_key = str(record.get("agent_id") or "(unknown)")
        model_key = str(record.get("model") or "(unknown)")
        session_key = str(record.get("session_id") or "(unknown)")
        add(by_task, task_key, record)
        add(by_role, role_key, record)
        add(by_agent, agent_key, record)
        add(by_model, model_key, record)
        add(by_session, session_key, record)
        add(by_status, status, record)

    if accepted_task_ids is not None:
        accepted = accepted_task_ids
    else:
        accepted = {
            str(record.get("task_id"))
            for record in merged
            if record.get("accepted_result") is True and record.get("task_id")
        }
    accepted_cost = 0.0
    accepted_unknown = 0
    for record in merged:
        if str(record.get("task_id")) not in accepted:
            continue
        if record.get("usage_known"):
            accepted_cost += float(_number(record.get(_COST_FIELD)))
        else:
            accepted_unknown += 1
    totals["estimated_cost_usd"] = round(float(totals["estimated_cost_usd"]), 6)
    return {
        "totals": totals,
        "by_task": by_task,
        "by_role": by_role,
        "by_agent": by_agent,
        "by_model": by_model,
        "by_session": by_session,
        "by_status": by_status,
        "accepted_tasks": len(accepted),
        "accepted_cost_usd": round(accepted_cost, 6),
        "accepted_cost_unknown_usage_invocations": accepted_unknown,
    }


def main(argv: list[str] | None = None) -> int:
    """Manual, side-effect-limited reconciliation entry point (no scheduler)."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reconcile = sub.add_parser("reconcile", help="close orphaned started invocations")
    reconcile.add_argument(
        "--root",
        default=str(Path.cwd() / ".autonomy"),
        help="autonomy state directory containing invocations.jsonl",
    )
    args = parser.parse_args(argv)
    if args.command == "reconcile":
        written = reconcile_invocations(Path(args.root))
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))  # noqa: T201
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
