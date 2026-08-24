from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from mbti_tiktok_bot.config import AppConfig

DEFAULT_DAEMON_TIMES = ("08:00", "12:00", "18:00")
MAX_BACKLOG_DAYS = 1


@dataclass(slots=True)
class DaemonState:
    current_date: str
    completed_slots: list[str]


def _parse_state_date(raw_value: str) -> date | None:
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_times(raw_times: list[str] | tuple[str, ...]) -> list[str]:
    normalized: set[str] = set()
    for raw_time in raw_times:
        try:
            parsed = datetime.strptime(raw_time, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"Invalid time '{raw_time}'. Use HH:MM format.") from exc
        normalized.add(parsed.strftime("%H:%M"))
    return sorted(normalized)


def daemon_state_path(config: AppConfig) -> Path:
    return config.state_dir / "phone_export_daemon_state.json"


def load_daemon_state(config: AppConfig) -> DaemonState:
    path = daemon_state_path(config)
    if not path.exists():
        return DaemonState(current_date="", completed_slots=[])

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DaemonState(current_date="", completed_slots=[])

    current_date = str(payload.get("current_date") or "")
    completed_slots = [str(item) for item in payload.get("completed_slots", [])]
    return DaemonState(current_date=current_date, completed_slots=completed_slots)


def save_daemon_state(config: AppConfig, state: DaemonState) -> Path:
    path = daemon_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "current_date": state.current_date,
                "completed_slots": state.completed_slots,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def due_slots(now: datetime, scheduled_times: list[str], state: DaemonState) -> list[str]:
    today = now.strftime("%Y-%m-%d")
    return [slot_time for target_date, slot_time in pending_slot_runs(now, scheduled_times, state) if target_date == today]


def pending_slot_runs(
    now: datetime,
    scheduled_times: list[str],
    state: DaemonState,
    max_backlog_days: int = MAX_BACKLOG_DAYS,
) -> list[tuple[str, str]]:
    today = now.strftime("%Y-%m-%d")
    today_date = now.date()
    state_date = _parse_state_date(state.current_date)
    state_completed = set(state.completed_slots)
    if state_date is None or state_date > today_date:
        state_date = today_date
        state_completed = set()

    # Stale state would otherwise fan out into one run per slot per missed day.
    # After a long outage the old posts are worthless anyway, so cap the catch-up
    # instead of emitting months of backlog in a single run.
    earliest_date = today_date - timedelta(days=max(max_backlog_days, 0))
    if state_date < earliest_date:
        state_date = earliest_date
        state_completed = set()

    pending: list[tuple[str, str]] = []
    current_date = state_date
    while current_date <= today_date:
        target_date = current_date.isoformat()
        completed = state_completed if current_date == state_date else set()
        for scheduled_time in scheduled_times:
            if scheduled_time in completed:
                continue
            scheduled_at = datetime.strptime(f"{target_date} {scheduled_time}", "%Y-%m-%d %H:%M")
            if now >= scheduled_at:
                pending.append((target_date, scheduled_time))
        current_date += timedelta(days=1)
    return pending


def append_daemon_log(config: AppConfig, message: str) -> Path:
    log_dir = config.project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "phone_export_daemon.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
    return log_path


def run_daemon(
    config: AppConfig,
    scheduled_times: list[str],
    poll_seconds: int,
    slot_runner: Callable[[str], int],
    run_once: bool = False,
) -> int:
    normalized_times = normalize_times(scheduled_times)
    append_daemon_log(config, f"START times={','.join(normalized_times)} poll_seconds={poll_seconds}")

    while True:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        state = load_daemon_state(config)
        pending_runs = pending_slot_runs(now, normalized_times, state)
        for target_date, scheduled_time in pending_runs:
            if target_date != today:
                append_daemon_log(config, f"RECOVER date={target_date} slot={scheduled_time}")
            append_daemon_log(config, f"RUN date={target_date} slot={scheduled_time}")
            exit_code = slot_runner(target_date)
            if exit_code == 0:
                if state.current_date != target_date:
                    state = DaemonState(current_date=target_date, completed_slots=[])
                state.completed_slots.append(scheduled_time)
                state.completed_slots = sorted(set(state.completed_slots))
                save_daemon_state(config, state)
                append_daemon_log(config, f"SUCCESS date={target_date} slot={scheduled_time}")
            else:
                append_daemon_log(config, f"FAIL date={target_date} slot={scheduled_time} exit_code={exit_code}")

        if run_once:
            append_daemon_log(config, "STOP run_once=true")
            return 0

        time.sleep(poll_seconds)