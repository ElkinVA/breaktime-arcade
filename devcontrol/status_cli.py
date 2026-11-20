# ruff: noqa: E402, T201
"""Agent-side event emitter for BA Dev Control.

The autonomous session calls this CLI at phase transitions; the bot tails the
events file and sends concise notifications. This file never talks to Telegram
and never needs the bot token.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from devcontrol.config import default_runtime_dir  # noqa: E402
from devcontrol.store import RuntimePaths, StateStore, utc_now  # noqa: E402

PATHS = RuntimePaths(default_runtime_dir())

EVENTS = {
    "task_started",
    "task_completed",
    "review_accept",
    "review_reject",
    "blocked",
    "tests_failed",
    "owner_decision_required",
    "milestone",
    "security_critical",
    "session_stop",
    "error",
    "heartbeat",
    "commit",
    "push",
}


def _store() -> StateStore:
    return StateStore(PATHS)


def cmd_event(args: argparse.Namespace) -> int:
    if args.event not in EVENTS:
        print(f"unknown event: {args.event}", file=sys.stderr)
        return 2
    store = _store()
    payload = store.append_event(
        args.event,
        task=args.task,
        title=args.title,
        detail=(args.detail or "")[:2000],
        status=args.status,
    )
    store.update_state(
        last_event=args.event,
        last_event_at=payload["ts"],
        current_task=args.task or None,
        current_title=args.title or None,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    store = _store()
    payload = store.append_event(
        "heartbeat",
        task=args.task,
        status=args.status,
        detail=(args.detail or "")[:500],
    )
    store.update_state(
        heartbeat_at=payload["ts"],
        status=args.status or "RUNNING",
        current_task=args.task or None,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    store = _store()
    if args.consume:
        messages = store.consume_inbox()
    else:
        from devcontrol.store import read_jsonl

        messages = read_jsonl(PATHS.inbox)
    print(json.dumps(messages, ensure_ascii=False))
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    store = _store()
    record = store.write_pending_owner(
        {
            "task": args.task,
            "title": args.title,
            "question": args.question[:2000],
            "options": args.options or "",
        }
    )
    store.append_event(
        "owner_decision_required",
        task=args.task,
        title=args.title,
        detail=args.question[:2000],
    )
    print(json.dumps(record, ensure_ascii=False))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    store = _store()
    payload: dict[str, Any] = store.load_state()
    payload["now"] = utc_now()
    payload["paused"] = store.paused()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BA Dev Control agent event emitter")
    sub = parser.add_subparsers(dest="command", required=True)

    event = sub.add_parser("event", help="append a task/review/error event")
    event.add_argument("event", choices=sorted(EVENTS))
    event.add_argument("--task", default="")
    event.add_argument("--title", default="")
    event.add_argument("--detail", default="")
    event.add_argument("--status", default="")
    event.set_defaults(func=cmd_event)

    heartbeat = sub.add_parser("heartbeat", help="record that the session is alive")
    heartbeat.add_argument("--task", default="")
    heartbeat.add_argument("--status", default="RUNNING")
    heartbeat.add_argument("--detail", default="")
    heartbeat.set_defaults(func=cmd_heartbeat)

    inbox = sub.add_parser("inbox", help="read or consume owner messages")
    inbox.add_argument("--consume", action="store_true")
    inbox.set_defaults(func=cmd_inbox)

    pending = sub.add_parser("pending", help="request an owner decision")
    pending.add_argument("--task", required=True)
    pending.add_argument("--title", default="")
    pending.add_argument("--question", required=True)
    pending.add_argument("--options", default="")
    pending.set_defaults(func=cmd_pending)

    status = sub.add_parser("status", help="print the local runtime state")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
