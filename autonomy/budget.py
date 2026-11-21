"""Hard resource budgets for an autonomous run.

The control plane must never consume an unbounded amount of work or money in a
single invocation.  A :class:`Budget` is loaded from the environment with hard
defaults; :class:`BudgetTracker` records actual usage reported by the model
(``modelUsage``) and reports the first exhausted limit.

Reason codes are stable and machine-readable:

``MAX_TASKS``
    The CLI requested more tasks than the hard per-run cap.
``WALL_CLOCK``
    The run exceeded its maximum wall-clock duration.
``TOKEN_BUDGET``
    The run consumed its token budget (input, output and cache tokens).
``COST_BUDGET``
    The run consumed its API-cost budget (``costUSD`` from ``modelUsage``).
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

MAX_TASKS = "MAX_TASKS"
WALL_CLOCK = "WALL_CLOCK"
TOKEN_BUDGET = "TOKEN_BUDGET"  # noqa: S105 - machine-readable reason code
COST_BUDGET = "COST_BUDGET"
BUDGET_REASONS = {MAX_TASKS, WALL_CLOCK, TOKEN_BUDGET, COST_BUDGET}

DEFAULT_MAX_TASKS = 5
DEFAULT_MAX_RUN_SECONDS = 3600.0
DEFAULT_MAX_TOKENS = 5_000_000
DEFAULT_MAX_COST_USD = 5.0

# Primary environment variables; the BA_AUTONOMY_* spellings are accepted as
# aliases so existing deployments keep working if they used the longer names.
_ENV_MAX_TASKS = ("BA_MAX_TASKS_PER_RUN", "BA_AUTONOMY_MAX_TASKS")
_ENV_MAX_RUN_SECONDS = ("BA_MAX_RUN_SECONDS", "BA_AUTONOMY_MAX_RUN_SECONDS")
_ENV_MAX_TOKENS = ("BA_MAX_TOKENS", "BA_AUTONOMY_MAX_TOKENS")
_ENV_MAX_COST_USD = ("BA_MAX_COST_USD", "BA_AUTONOMY_MAX_COST_USD")


class BudgetError(ValueError):
    """A configured budget is invalid."""


def _as_int(value: Any) -> int:
    try:
        number = int(value)
    except TypeError, ValueError:
        return 0
    return max(0, number)


def _as_float(value: Any) -> float:
    try:
        number = float(value)
    except TypeError, ValueError:
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, number)


def _env_raw(env: Mapping[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        raw = env.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _env_int(env: Mapping[str, str], keys: tuple[str, ...], default: int) -> int:
    raw = _env_raw(env, keys)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise BudgetError(f"{keys[0]} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise BudgetError(f"{keys[0]} must be non-negative, got {value}")
    return value


def _env_float(env: Mapping[str, str], keys: tuple[str, ...], default: float) -> float:
    raw = _env_raw(env, keys)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise BudgetError(f"{keys[0]} must be a number, got {raw!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise BudgetError(f"{keys[0]} must be a finite non-negative number, got {raw!r}")
    return value


@dataclass(frozen=True)
class Usage:
    """Normalised token and cost usage extracted from ``modelUsage``."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> Usage:
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            input_tokens=_as_int(value.get("input_tokens")),
            output_tokens=_as_int(value.get("output_tokens")),
            cache_read_tokens=_as_int(value.get("cache_read_tokens")),
            cache_creation_tokens=_as_int(value.get("cache_creation_tokens")),
            cost_usd=_as_float(value.get("cost_usd")),
        )

    @classmethod
    def from_model_usage(
        cls,
        model_usage: Mapping[str, Any] | None,
        *,
        total_cost_usd: float | None = None,
    ) -> Usage:
        """Sum every per-model entry of Claude Code's ``modelUsage`` object."""
        usage = cls()
        entries = model_usage.values() if isinstance(model_usage, Mapping) else ()
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            usage = usage + cls(
                input_tokens=_as_int(entry.get("inputTokens", entry.get("input_tokens"))),
                output_tokens=_as_int(entry.get("outputTokens", entry.get("output_tokens"))),
                cache_read_tokens=_as_int(
                    entry.get("cacheReadInputTokens", entry.get("cache_read_input_tokens"))
                ),
                cache_creation_tokens=_as_int(
                    entry.get("cacheCreationInputTokens", entry.get("cache_creation_input_tokens"))
                ),
                cost_usd=_as_float(entry.get("costUSD", entry.get("cost_usd"))),
            )
        if usage.cost_usd == 0.0 and total_cost_usd is not None:
            # Claude Code also reports the invocation total at the root; use it
            # only when per-model cost is unavailable.
            usage = Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_creation_tokens=usage.cache_creation_tokens,
                cost_usd=_as_float(total_cost_usd),
            )
        return usage


@dataclass(frozen=True)
class Budget:
    """Hard limits for one ``orchestrator run`` invocation."""

    max_tasks: int = DEFAULT_MAX_TASKS
    max_run_seconds: float = DEFAULT_MAX_RUN_SECONDS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_cost_usd: float = DEFAULT_MAX_COST_USD

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Budget:
        source = os.environ if env is None else env
        return cls(
            max_tasks=_env_int(source, _ENV_MAX_TASKS, DEFAULT_MAX_TASKS),
            max_run_seconds=_env_float(source, _ENV_MAX_RUN_SECONDS, DEFAULT_MAX_RUN_SECONDS),
            max_tokens=_env_int(source, _ENV_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            max_cost_usd=_env_float(source, _ENV_MAX_COST_USD, DEFAULT_MAX_COST_USD),
        )

    def task_cap(self, requested: int | None) -> int:
        """Clamp a CLI task request to the hard cap."""
        if requested is None:
            return self.max_tasks
        return max(0, min(requested, self.max_tasks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tasks": self.max_tasks,
            "max_run_seconds": self.max_run_seconds,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
        }


@dataclass(frozen=True)
class BudgetStop:
    reason: str
    limit: float
    used: float
    usage: Usage

    def to_report(self, **extra: Any) -> dict[str, Any]:
        report: dict[str, Any] = {
            "status": "stopped",
            "reason": "BUDGET",
            "budget_reason": self.reason,
            "limit": self.limit,
            "used": self.used,
            "usage": self.usage.to_dict(),
        }
        report.update(extra)
        return report


class BudgetReached(RuntimeError):
    """Raised at a safe boundary once a hard budget is exhausted."""

    def __init__(self, stop: BudgetStop) -> None:
        super().__init__(f"budget exhausted: {stop.reason}")
        self.stop = stop


class BudgetTracker:
    """Accumulate actual usage and report the first exhausted limit."""

    def __init__(
        self,
        budget: Budget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget
        self._clock = clock
        self.started_at = clock()
        self.usage = Usage()

    def elapsed(self) -> float:
        return max(0.0, self._clock() - self.started_at)

    def add(self, usage: Usage) -> Usage:
        self.usage = self.usage + usage
        return self.usage

    def stop(self) -> BudgetStop | None:
        if self.usage.total_tokens >= self.budget.max_tokens:
            return BudgetStop(
                TOKEN_BUDGET,
                float(self.budget.max_tokens),
                float(self.usage.total_tokens),
                self.usage,
            )
        if self.usage.cost_usd >= self.budget.max_cost_usd:
            return BudgetStop(
                COST_BUDGET,
                self.budget.max_cost_usd,
                round(self.usage.cost_usd, 6),
                self.usage,
            )
        elapsed = self.elapsed()
        if elapsed >= self.budget.max_run_seconds:
            return BudgetStop(
                WALL_CLOCK,
                self.budget.max_run_seconds,
                round(elapsed, 3),
                self.usage,
            )
        return None
