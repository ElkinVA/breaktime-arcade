"""Dev-only Live Room load diagnostic.

Creates isolated rooms/users, drives polling and ready commands with real
PostgreSQL connections, prints latency/query/lock metrics, and removes its
data. It is intentionally not part of the normal test gate.
"""

from __future__ import annotations

import math
import resource
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.models import User
from apps.catalog.models import Game
from apps.rooms.models import Room, RoomMember
from apps.rooms.services.rooms import create_room, execute_command, join_room, read_room

LOADTEST_PREFIX = "loadtest_"


@dataclass
class ActiveRoom:
    room_id: UUID
    users: list[User]
    room_code: str


@dataclass
class Metrics:
    latencies: list[float] = field(default_factory=list)
    queries: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    version_changes: int = 0


def _request(user: User):
    request = RequestFactory().post("/")
    request.user = user
    return request


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _read_once(user: User, room_id: UUID) -> tuple[float, int]:
    query_count = 0

    def count(execute, sql, params, many, context):
        nonlocal query_count
        query_count += 1
        return execute(sql, params, many, context)

    started = time.perf_counter()
    with connection.execute_wrapper(count):
        read_room(_request(user), room_id)
    return (time.perf_counter() - started) * 1000, query_count


class Command(BaseCommand):
    help = "Measure Live Room polling/command latency against the real PostgreSQL."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--rooms", type=int, default=1)
        parser.add_argument("--players", type=int, default=4)
        parser.add_argument("--seconds", type=int, default=15)
        parser.add_argument("--poll-ms", type=int, default=1200)

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("room_loadtest is a dev-only diagnostic command")
        rooms_count = min(max(1, int(options["rooms"])), 20)
        players = int(options["players"])
        seconds = min(max(1, int(options["seconds"])), 600)
        poll_ms = min(max(100, int(options["poll_ms"])), 10_000)
        if not 4 <= players <= 12:
            raise CommandError("--players must be between 4 and 12")

        game = (
            Game.objects.filter(technical_id__in=["whos_undercover_live", "whos_undercover"])
            .filter(status=Game.STATUS_PUBLISHED, current_version__isnull=False)
            .order_by("technical_id")
            .first()
        )
        if game is None:
            raise CommandError("no published Live Room game found")

        run_tag = f"{LOADTEST_PREFIX}{uuid4().hex[:10]}"
        users: list[User] = []
        active_rooms: list[ActiveRoom] = []
        command_room: ActiveRoom | None = None
        metrics = Metrics()
        command_latencies: list[float] = []
        command_errors: list[str] = []
        lock_wait_samples: list[int] = []
        cpu_start = resource.getrusage(resource.RUSAGE_SELF)
        started = time.monotonic()
        try:
            for room_index in range(rooms_count):
                room_users = [
                    User.objects.create_user(
                        login=f"{run_tag}_{room_index}_{player_index}",
                        password=uuid4().hex,
                    )
                    for player_index in range(players)
                ]
                users.extend(room_users)
                room, _host_member = self._create_room(
                    game,
                    room_users[0],
                    players,
                    f"Load host {room_index}",
                )
                active_rooms.append(
                    ActiveRoom(room_id=room.id, users=room_users, room_code=room.code)
                )
                for player in room_users[1:]:
                    join_room(
                        _request(player),
                        HttpResponse(),
                        code=room.code,
                        name=player.get_username(),
                    )
                    execute_command(
                        _request(player),
                        room.id,
                        command="ready",
                        payload={"ready": True},
                        request_id=None,
                        expected_version=None,
                    )
                execute_command(
                    _request(room_users[0]),
                    room.id,
                    command="start",
                    payload={},
                    request_id=None,
                    expected_version=None,
                )

            command_users = [
                User.objects.create_user(
                    login=f"{run_tag}_command_{index}",
                    password=uuid4().hex,
                )
                for index in range(4)
            ]
            users.extend(command_users)
            command_room_obj, _command_host = self._create_room(
                game, command_users[0], 4, "Command host"
            )
            command_room = ActiveRoom(
                room_id=command_room_obj.id,
                users=command_users,
                room_code=command_room_obj.code,
            )
            for player in command_users[1:]:
                join_room(
                    _request(player),
                    HttpResponse(),
                    code=command_room_obj.code,
                    name=player.get_username(),
                )

            deadline = time.monotonic() + seconds
            workers: list[threading.Thread] = []
            for active in active_rooms:
                for user in active.users:
                    workers.append(
                        threading.Thread(
                            target=self._poll_worker,
                            args=(active.room_id, user, deadline, poll_ms, metrics),
                        )
                    )
            command_worker = threading.Thread(
                target=self._command_worker,
                args=(command_room, deadline, command_latencies, command_errors),
            )
            sampler = threading.Thread(
                target=self._lock_sampler,
                args=(deadline, lock_wait_samples),
            )
            for worker in [*workers, command_worker, sampler]:
                worker.start()
            for worker in [*workers, command_worker, sampler]:
                worker.join(timeout=seconds + 30)

            elapsed = max(0.001, time.monotonic() - started)
            cpu_end = resource.getrusage(resource.RUSAGE_SELF)
            self._report(
                game.technical_id,
                rooms_count,
                players,
                seconds,
                poll_ms,
                elapsed,
                metrics,
                command_latencies,
                command_errors,
                lock_wait_samples,
                cpu_start,
                cpu_end,
            )
            if any(worker.is_alive() for worker in [*workers, command_worker, sampler]):
                self.stdout.write("WARNING: one or more load workers did not finish")
        finally:
            room_ids = [item.room_id for item in active_rooms]
            if command_room is not None:
                room_ids.append(command_room.room_id)
            Room.objects.filter(pk__in=room_ids).delete()
            User.objects.filter(pk__in=[user.pk for user in users]).delete()
            connections.close_all()

    @staticmethod
    def _create_room(game: Game, host: User, players: int, name: str) -> tuple[Room, RoomMember]:
        return create_room(
            _request(host),
            HttpResponse(),
            game_id=game.technical_id,
            max_players=players,
            name=name,
        )

    @staticmethod
    def _poll_worker(
        room_id: UUID,
        user: User,
        deadline: float,
        poll_ms: int,
        metrics: Metrics,
    ) -> None:
        jitter = ((user.pk.int % 200) / 1000.0) - 0.1
        last_version = 0
        try:
            while time.monotonic() < deadline:
                try:
                    latency, query_count = _read_once(user, room_id)
                    metrics.latencies.append(latency)
                    metrics.queries.append(query_count)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT version FROM rooms_room WHERE id = %s", [room_id])
                        row = cursor.fetchone()
                    version = int(row[0]) if row else 0
                    if last_version and version != last_version:
                        metrics.version_changes += 1
                    last_version = version
                except Exception as exc:  # noqa: BLE001 - diagnostic aggregation
                    metrics.errors.append(type(exc).__name__)
                time.sleep(max(0.05, poll_ms / 1000 + jitter))
        finally:
            connections.close_all()

    @staticmethod
    def _command_worker(
        command_room: ActiveRoom,
        deadline: float,
        latencies: list[float],
        errors: list[str],
    ) -> None:
        guest = command_room.users[1]
        toggle = False
        try:
            while time.monotonic() < deadline:
                started = time.perf_counter()
                try:
                    execute_command(
                        _request(guest),
                        command_room.room_id,
                        command="ready",
                        payload={"ready": toggle},
                        request_id=uuid4(),
                        expected_version=None,
                    )
                    latencies.append((time.perf_counter() - started) * 1000)
                    toggle = not toggle
                except Exception as exc:  # noqa: BLE001 - diagnostic aggregation
                    errors.append(type(exc).__name__)
                time.sleep(1.0)
        finally:
            connections.close_all()

    @staticmethod
    def _lock_sampler(deadline: float, samples: list[int]) -> None:
        try:
            while time.monotonic() < deadline:
                try:
                    with connections["default"].cursor() as cursor:
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() "
                            "AND wait_event_type = 'Lock'"
                        )
                        row = cursor.fetchone()
                    samples.append(int(row[0]) if row else 0)
                except Exception:  # noqa: BLE001, S110 - diagnostic sampler
                    pass
                time.sleep(0.5)
        finally:
            connections.close_all()

    def _report(
        self,
        game_id: str,
        rooms_count: int,
        players: int,
        seconds: int,
        poll_ms: int,
        elapsed: float,
        metrics: Metrics,
        command_latencies: list[float],
        command_errors: list[str],
        lock_wait_samples: list[int],
        cpu_start: resource.struct_rusage,
        cpu_end: resource.struct_rusage,
    ) -> None:
        read_count = len(metrics.latencies)
        command_count = len(command_latencies)
        self.stdout.write("Live Room load baseline")
        self.stdout.write(
            f"environment: django={settings.DEBUG} db={connection.vendor} "
            f"rooms={rooms_count} players={players} seconds={seconds} poll_ms={poll_ms}"
        )
        self.stdout.write(
            f"read: count={read_count} rps={read_count / elapsed:.2f} "
            f"p50={_percentile(metrics.latencies, 0.50):.1f}ms "
            f"p95={_percentile(metrics.latencies, 0.95):.1f}ms "
            f"p99={_percentile(metrics.latencies, 0.99):.1f}ms "
            f"max={max(metrics.latencies, default=0):.1f}ms"
        )
        self.stdout.write(
            f"read SQL: avg_queries={sum(metrics.queries) / max(1, len(metrics.queries)):.2f} "
            f"max_queries={max(metrics.queries, default=0)} "
            f"version_changes={metrics.version_changes}"
        )
        self.stdout.write(
            f"command: count={command_count} "
            f"p50={_percentile(command_latencies, 0.50):.1f}ms "
            f"p95={_percentile(command_latencies, 0.95):.1f}ms "
            f"p99={_percentile(command_latencies, 0.99):.1f}ms"
        )
        read_error_counts = {item: metrics.errors.count(item) for item in set(metrics.errors)}
        command_error_counts = {item: command_errors.count(item) for item in set(command_errors)}
        self.stdout.write(
            f"errors: read={len(metrics.errors)} command={len(command_errors)} "
            f"read_types={read_error_counts} command_types={command_error_counts}"
        )
        self.stdout.write(
            f"db lock waiters: samples={len(lock_wait_samples)} "
            f"max={max(lock_wait_samples, default=0)} "
            f"nonzero={sum(1 for value in lock_wait_samples if value)}"
        )
        cpu_delta = (cpu_end.ru_utime + cpu_end.ru_stime) - (
            cpu_start.ru_utime + cpu_start.ru_stime
        )
        with Path("/proc/self/status").open(encoding="utf-8") as status_file:
            rss = next(
                (
                    line.split(":", 1)[1].strip()
                    for line in status_file
                    if line.startswith("VmRSS:")
                ),
                "unknown",
            )
        self.stdout.write(
            f"resource: process_cpu_s={cpu_delta:.2f} rss={rss} wall_s={elapsed:.2f} "
            f"game_id={game_id}"
        )
