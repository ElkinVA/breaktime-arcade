"""Per-invocation token and cost observability for the autonomy runner.

Only metadata is persisted: no prompts, responses, headers or secrets.  The
Claude Code JSON result does not expose the provider's exact request count, so
``request_count`` stays ``None`` unless the producer supplies it; ``num_turns``
is recorded separately and must not be presented as an exact API request
count.  Provider-reported and Claude-reported values keep an explicit source.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROVIDER_REPORTED = "provider_reported"
CLAUDE_CODE = "claude_code"
ORCHESTRATOR = "orchestrator"

INVOCATIONS_FILE = "invocations.jsonl"


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
    input_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    output_tokens: int
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


def from_run_result(
    result: Any,
    *,
    task_id: str | None = None,
    attempt_id: str | None = None,
    retry_count: int = 0,
    accepted_result: bool | None = None,
) -> InvocationMetrics:
    """Build a metadata-only record from a runner result.

    ``usage`` is Claude Code's ``modelUsage``-derived accounting.  Cache read
    is recorded as ``cache_hit_tokens``; cache creation plus ordinary input is
    recorded as ``cache_miss_tokens``.  These are Claude-reported values, not
    a provider invoice.
    """
    usage = result.usage
    model_usage = result.model_usage if isinstance(result.model_usage, dict) else {}
    model = str(getattr(result, "model", "") or "")
    return InvocationMetrics(
        task_id=task_id,
        attempt_id=attempt_id,
        agent_id=str(getattr(result, "agent", "") or ""),
        role=str(getattr(result, "role", "") or ""),
        session_id=getattr(result, "session_id", None),
        invocation_id=str(getattr(result, "invocation_id", "") or ""),
        model=model,
        reported_models=tuple(str(name) for name in model_usage),
        execution_channel=ORCHESTRATOR,
        request_count=getattr(result, "request_count", None),
        num_turns=getattr(result, "num_turns", None),
        input_tokens=usage.input_tokens,
        cache_hit_tokens=usage.cache_read_tokens,
        cache_miss_tokens=usage.input_tokens + usage.cache_creation_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=_model_usage_reasoning(model_usage),
        estimated_cost_usd=usage.cost_usd,
        started_at=getattr(result, "started_at", None),
        finished_at=getattr(result, "finished_at", None),
        status="ok" if getattr(result, "returncode", 0) == 0 else "error",
        accepted_result=accepted_result,
        retry_count=max(0, int(retry_count)),
        usage_source=CLAUDE_CODE,
    )


def record_invocation(root: Path, metrics: InvocationMetrics) -> Path:
    """Append one metadata record; never persist prompt/response content."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / INVOCATIONS_FILE
    line = json.dumps(metrics.as_dict(), ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def read_invocations(root: Path, *, include_corrupt: bool = False) -> list[dict[str, Any]]:
    path = Path(root) / INVOCATIONS_FILE
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    skipped = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
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


def _number(value: Any) -> int | float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    return 0


def summarize(
    records: list[dict[str, Any]],
    *,
    accepted_task_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Deduplicate and aggregate metadata records by task/role/agent/session."""
    by_invocation: dict[str, dict[str, Any]] = {}
    for record in records:
        if set(record) == {"corrupt_lines"}:
            # read_invocations(include_corrupt=True) marker, not a real event.
            continue
        invocation_id = str(record.get("invocation_id") or "")
        if not invocation_id:
            # Keep unidentifiable records but never merge them silently.
            invocation_id = f"anonymous:{len(by_invocation)}"
        # First record wins; duplicates must not silently replace counts.
        by_invocation.setdefault(invocation_id, record)

    totals: dict[str, float] = {
        "invocations": 0,
        "request_count_known": 0,
        "input_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_usd": 0.0,
        "retry_count": 0,
    }
    by_task: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_session: dict[str, dict[str, Any]] = {}

    def add(bucket: dict[str, dict[str, Any]], key: str, record: dict[str, Any]) -> None:
        item = bucket.setdefault(
            key,
            {
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
            },
        )
        item["invocations"] += 1
        request_count = record.get("request_count")
        if isinstance(request_count, int) and not isinstance(request_count, bool):
            item["request_count"] += max(0, request_count)
            item["request_count_known"] += 1
        for field in (
            "input_tokens",
            "cache_hit_tokens",
            "cache_miss_tokens",
            "output_tokens",
            "reasoning_tokens",
            "retry_count",
        ):
            item[field] += int(_number(record.get(field)))
        item["estimated_cost_usd"] += float(_number(record.get("estimated_cost_usd")))

    for record in by_invocation.values():
        totals["invocations"] += 1
        if isinstance(record.get("request_count"), int) and not isinstance(
            record.get("request_count"), bool
        ):
            totals["request_count_known"] += 1
        for field in (
            "input_tokens",
            "cache_hit_tokens",
            "cache_miss_tokens",
            "output_tokens",
            "reasoning_tokens",
            "retry_count",
        ):
            totals[field] += int(_number(record.get(field)))
        totals["estimated_cost_usd"] += float(_number(record.get("estimated_cost_usd")))
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

    accepted = accepted_task_ids or {
        str(record.get("task_id"))
        for record in by_invocation.values()
        if record.get("accepted_result") is True and record.get("task_id")
    }
    accepted_cost = sum(
        float(_number(record.get("estimated_cost_usd")))
        for record in by_invocation.values()
        if str(record.get("task_id")) in accepted
    )
    return {
        "totals": totals,
        "by_task": by_task,
        "by_role": by_role,
        "by_agent": by_agent,
        "by_model": by_model,
        "by_session": by_session,
        "accepted_tasks": len(accepted),
        "accepted_cost_usd": round(accepted_cost, 6),
    }
