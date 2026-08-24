from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.daemon import DEFAULT_DAEMON_TIMES, DaemonState, load_daemon_state, normalize_times, run_daemon, save_daemon_state
from mbti_tiktok_bot.phone_export import export_daily_results_to_phone
from mbti_tiktok_bot.pipeline import build_daily_bundle, build_daily_bundles, load_daily_results, load_existing_visual_results, refresh_existing_visuals
from mbti_tiktok_bot.planner import advance_series_state, resolve_target_date


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MBTI image asset generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("run-daily", help="Generate a day's image assets")
    daily.add_argument("--date", help="Target date in YYYY-MM-DD")
    daily.add_argument("--mbti", help="Override MBTI type, e.g. ENFP")
    daily.add_argument("--format", help="Override post format")
    daily.add_argument("--dry-run", action="store_true", help="Build assets without any extra side effects")
    daily.add_argument("--export-phone", action="store_true", help="Export this run's assets to a phone sync folder")

    slot = subparsers.add_parser("run-slot", help="Generate one scheduled image asset set")
    slot.add_argument("--date", help="Target date in YYYY-MM-DD")
    slot.add_argument("--dry-run", action="store_true", help="Build assets without writing exports or advancing state")
    slot.add_argument("--export-phone", action="store_true", help="Export this run's asset set to a phone sync folder")

    daemon = subparsers.add_parser("run-daemon", help="Keep running and execute slot exports at configured times")
    daemon.add_argument("--times", nargs="+", default=list(DEFAULT_DAEMON_TIMES), help="Daily run times in HH:MM format")
    daemon.add_argument("--poll-seconds", type=int, default=30, help="Seconds between schedule checks")
    daemon.add_argument("--dry-run", action="store_true", help="Build assets without writing exports or advancing state")
    daemon.add_argument("--run-once", action="store_true", help="Evaluate due slots once and exit")

    plan = subparsers.add_parser("plan", help="Generate today's packages")
    plan.add_argument("--date", help="Target date in YYYY-MM-DD")
    plan.add_argument("--mbti", help="Override MBTI type")
    plan.add_argument("--format", help="Override post format")

    refresh = subparsers.add_parser("refresh-visuals", help="Re-render illustrations for existing packages")
    refresh.add_argument("--topic", help="Only refresh one existing topic folder")
    refresh.add_argument("--export-phone", action="store_true", help="Also replace the matching phone exports")
    refresh.add_argument("--export-only", action="store_true", help="Export completed visuals without rendering them again")

    return parser


def _build_results(args: argparse.Namespace, config, target_date):
    if args.mbti:
        return [
            build_daily_bundle(
                target_date=target_date,
                config=config,
                explicit_mbti=args.mbti,
                explicit_format=args.format,
            )
        ]
    return build_daily_bundles(
        target_date=target_date,
        config=config,
        explicit_format=args.format,
    )


def _print_build_results(results, reused_existing: bool = False) -> None:
    package_label = "Using package" if reused_existing else "Created package"
    image_label = "Using image set" if reused_existing else "Created image set"
    for result in results:
        print(f"{package_label}: {result.package_path}")
        print(f"{image_label}: {len(result.media_paths)} images in {result.output_dir / 'slides'}")


def _should_reuse_existing_outputs(args: argparse.Namespace) -> bool:
    return not args.mbti and not args.format


def _should_export_to_phone(args: argparse.Namespace, config) -> bool:
    if args.dry_run:
        return False
    if args.export_phone:
        return True
    return config.phone_export_auto and _should_reuse_existing_outputs(args)


def _should_advance_series(args: argparse.Namespace, reused_existing: bool) -> bool:
    return not reused_existing and not args.dry_run and _should_reuse_existing_outputs(args)


def _build_slot_results(config, target_date):
    return build_daily_bundles(
        target_date=target_date,
        config=config,
        count=1,
        append_summary=True,
    )


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _due_slot_times_for_date(target_date: date, scheduled_times: list[str], now: datetime) -> list[str]:
    target_date_str = target_date.isoformat()
    due_slots: list[str] = []
    for scheduled_time in scheduled_times:
        scheduled_at = datetime.strptime(f"{target_date_str} {scheduled_time}", "%Y-%m-%d %H:%M")
        if now >= scheduled_at:
            due_slots.append(scheduled_time)
    return due_slots


def _reconcile_daemon_outputs(config, scheduled_times: list[str], dry_run: bool) -> int:
    if dry_run:
        return 0

    normalized_times = normalize_times(scheduled_times)
    now = datetime.now()
    today = now.date()
    state = load_daemon_state(config)
    start_date = today
    if state.current_date:
        try:
            parsed_state_date = datetime.strptime(state.current_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_state_date = today
        if parsed_state_date <= today:
            start_date = parsed_state_date

    today_results = load_daily_results(today, config)
    for target_date in _date_range(start_date, today):
        results = load_daily_results(target_date, config)
        if results:
            export_daily_results_to_phone(
                config=config,
                target_date=target_date,
                results=results,
                reset_export_dir=False,
            )

        due_slots = _due_slot_times_for_date(target_date, normalized_times, now)
        while len(results) < len(due_slots):
            exit_code = _run_slot_command(config, target_date, False, True)
            if exit_code != 0:
                return exit_code
            results = load_daily_results(target_date, config)

        if target_date == today:
            today_results = results

    save_daemon_state(
        config,
        DaemonState(
            current_date=today.isoformat(),
            completed_slots=normalized_times[: min(len(today_results), len(normalized_times))],
        ),
    )
    return 0


def _run_plan(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    target_date = resolve_target_date(args.date)
    results = _build_results(args, config, target_date)
    _print_build_results(results)
    return 0


def _run_refresh_visuals(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    results = (
        load_existing_visual_results(config, topic=args.topic)
        if args.export_only
        else refresh_existing_visuals(config, topic=args.topic)
    )
    if not results:
        print("No existing packages found to refresh")
        return 0

    topics = sorted({result.output_dir.parent.name for result in results})
    action = "Loaded completed visuals" if args.export_only else "Refreshed visuals"
    print(f"{action}: {len(results)} packages across {len(topics)} topics")
    for topic in topics:
        print(f"Updated topic: {topic}")

    if args.export_phone or args.export_only:
        export_result = export_daily_results_to_phone(
            config=config,
            target_date=date.today(),
            results=results,
        )
        print(f"Phone exports refreshed: {export_result.export_dir}")
    return 0


def _run_slot_command(config, target_date, dry_run: bool, export_phone: bool) -> int:
    results = _build_slot_results(config, target_date)

    _print_build_results(results)
    if dry_run:
        for result in results:
            print(f"Dry run complete: {result.output_dir}")
        return 0

    if export_phone:
        export_result = export_daily_results_to_phone(
            config=config,
            target_date=target_date,
            results=results,
            reset_export_dir=False,
        )
        print(f"Phone export ready: {export_result.export_dir}")

    next_post_index = advance_series_state(config, len(results))
    print(f"Series advanced: next post index {next_post_index}")
    for result in results:
        print(f"Build complete: {result.output_dir}")
    return 0


def _run_daily(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    target_date = resolve_target_date(args.date)
    reused_existing = False
    results = []

    if _should_reuse_existing_outputs(args):
        results = load_daily_results(target_date, config)
        reused_existing = bool(results)

    if not results:
        results = _build_results(args, config, target_date)

    _print_build_results(results, reused_existing=reused_existing)
    if args.dry_run:
        for result in results:
            print(f"Dry run complete: {result.output_dir}")
        return 0

    if _should_export_to_phone(args, config):
        export_result = export_daily_results_to_phone(
            config=config,
            target_date=target_date,
            results=results,
        )
        print(f"Phone export ready: {export_result.export_dir}")

    if _should_advance_series(args, reused_existing):
        next_post_index = advance_series_state(config, len(results))
        print(f"Series advanced: next post index {next_post_index}")

    for result in results:
        print(f"Build complete: {result.output_dir}")
    return 0


def _run_slot(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    target_date = resolve_target_date(args.date)
    return _run_slot_command(config, target_date, args.dry_run, _should_export_to_phone(args, config))


def _run_daemon(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    if args.poll_seconds < 1:
        raise ValueError("--poll-seconds must be at least 1")

    reconcile_exit_code = _reconcile_daemon_outputs(config, args.times, args.dry_run)
    if reconcile_exit_code != 0:
        return reconcile_exit_code

    print(f"Starting daemon for times: {', '.join(args.times)}")
    print("Stop with Ctrl+C")

    def _slot_runner(target_date: str) -> int:
        return _run_slot_command(
            config,
            resolve_target_date(target_date),
            args.dry_run,
            not args.dry_run,
        )

    try:
        return run_daemon(
            config=config,
            scheduled_times=args.times,
            poll_seconds=args.poll_seconds,
            slot_runner=_slot_runner,
            run_once=args.run_once,
        )
    except KeyboardInterrupt:
        print("Daemon stopped")
        return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run-daily":
        raise SystemExit(_run_daily(args))
    if args.command == "run-slot":
        raise SystemExit(_run_slot(args))
    if args.command == "run-daemon":
        raise SystemExit(_run_daemon(args))
    if args.command == "plan":
        raise SystemExit(_run_plan(args))
    if args.command == "refresh-visuals":
        raise SystemExit(_run_refresh_visuals(args))

    raise SystemExit(1)


if __name__ == "__main__":
    main()
