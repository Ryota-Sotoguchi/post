from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote

from tiktok_poster import media, oauth, pages, retention, tiktok
from tiktok_poster.catalog import (
    Upload,
    load_manifest,
    manifest_generated_at,
    manifest_path,
    scan_fresh,
    send_order,
    write_manifest,
)
from tiktok_poster.config import Config, load_config
from tiktok_poster.state import State, load_state, save_state


def _manifest(config: Config) -> list[Upload]:
    return load_manifest(manifest_path(config.publish_dir))


def _queue(config: Config) -> list[Upload]:
    """The posts that may go out now, in the order they will be sent."""
    # Send order, not just membership: the records are in the order they went
    # out, so a post that was skipped stays at the head of the queue.
    posted = [record.key for record in load_state(config.state_path).records]
    return send_order(_manifest(config), posted)


def _run_sync(args: argparse.Namespace) -> int:
    """Convert every carousel and record it in the manifest.

    Runs where the source images are. That used to mean a OneDrive folder
    shared between two machines; now the generator writes into this repo and
    SOURCE_DIR points at it. Everything the posting step needs is left behind
    in the manifest, because the Actions runner never sees the source images.
    """
    config = load_config(Path.cwd())
    posts = scan_fresh(config.source_dir)
    sent = {record.key for record in load_state(config.state_path).records}
    written = [post for post in posts if not post.filler]
    filler = [post for post in posts if post.filler]

    # Filler only has to be reachable when it is actually next in the queue, so
    # the tail of it stays on this PC until the queue gets that far.
    unsent_filler = [post for post in filler if post.key not in sent]
    keep_filler = set(post.key for post in unsent_filler[: config.publish_filler])
    keep_filler.update(post.key for post in filler if post.key in sent)
    posts = written + [post for post in filler if post.key in keep_filler]
    print(f"Found {len(written)} written post(s) and {len(filler)} filler; "
          f"publishing {len(posts)}")

    uploads: list[Upload] = []
    for index, post in enumerate(posts, start=1):
        media.publish_post(config, post)
        uploads.append(
            Upload(
                key=post.key,
                theme=post.theme,
                title=post.title,
                description=post.description,
                images=tuple(media.public_urls(config, post)),
                filler=post.filler,
            )
        )
        if index % 20 == 0 or index == len(posts):
            print(f"  converted {index}/{len(posts)}")

    path = write_manifest(manifest_path(config.publish_dir), uploads, config.pages_base_url)
    print(f"Wrote {path}")

    # TikTok pulls the images once, at send time, so a carousel it has already
    # taken does not need to stay reachable. Keeping every one of them is what
    # grew docs/media to 298MB. Hold the unsent queue plus a margin of recently
    # sent ones, in case a send has to be retried or its status re-checked.
    sent_keys = [record.key for record in load_state(config.state_path).records]
    keep = {upload.key for upload in uploads} - set(sent_keys)
    keep.update(sent_keys[-config.keep_published_posts :])
    removed = media.prune(config, keep)
    if removed:
        print(f"Pruned {len(removed)} published carousel(s) TikTok no longer needs")

    if args.dry_run:
        print("Dry run. Nothing pushed.")
        return 0

    # The generator runs on this PC too, and its progress - which topic comes
    # next, which slots are done - lives in state/. Nothing else ever commits
    # it, so a fresh clone would restart the series and redraw topics that have
    # already gone out. Actions owns state/posted.json, so that file is not
    # named here.
    generator_state = [
        path
        for path in (
            config.project_root / "state" / "series_state.json",
            config.project_root / "state" / "phone_export_daemon_state.json",
            config.project_root / "state" / "format_state.json",
            # Which L number each converted carousel was given. Losing it would
            # renumber the filler series and orphan what has already been sent.
            config.project_root / "state" / "legacy_converted.json",
        )
        if path.exists()
    ]
    try:
        if pages.push(config, f"media: sync {len(uploads)} carousel(s)", config.publish_dir, *generator_state):
            print("Pushed media and manifest")
        else:
            print("Already up to date")
    except pages.PagesError as error:
        print(f"Could not push: {error}")
        return 1
    return 0


# A sync that quietly stopped running is what froze the library for a week, and
# nothing on screen said so. Its age is the one number that would have shown it.
STALE_MANIFEST_DAYS = 2


def _manifest_age(config: Config) -> str:
    stamp = manifest_generated_at(manifest_path(config.publish_dir))
    if not stamp:
        return "never written - run `sync` on the PC with the images"
    try:
        written = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - written).days
    if days >= STALE_MANIFEST_DAYS:
        return f"{stamp} - {days} days old; run `sync` on the PC with the images"
    return stamp


def _run_status(_args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    state = load_state(config.state_path)
    try:
        uploads = _manifest(config)
    except FileNotFoundError as error:
        print(error)
        return 1
    queue = _queue(config)
    written = [upload for upload in queue if not upload.filler]

    print(f"Published     : {len(uploads)}")
    print(f"Sent          : {len(state.records)}")
    print(f"Pending       : {len(queue)}  ({len(written)} written, {len(queue) - len(written)} filler)")
    if config.posts_per_day:
        print(f"Days of stock : {len(queue) // config.posts_per_day} at {config.posts_per_day}/day")
    print(f"Manifest      : {_manifest_age(config)}")
    # The sandbox cannot refresh, so what matters is not whether a token was
    # ever obtained but whether the one on disk is still inside its 24 hours.
    tokens = tiktok.load_tokens(config)
    if tokens and tokens.is_fresh:
        print(f"Token         : usable until {tokens.expires_at}")
    elif tokens:
        print(f"Token         : EXPIRED at {tokens.expires_at} - run `daily` to re-authorize")
    else:
        print("Token         : none - run `daily` to authorize")
    print(f"Pages base URL: {config.pages_base_url or '(unset)'}")

    if queue:
        print("\nNext up:")
        for upload in queue[: config.posts_per_day]:
            print(f"  {upload.title}   {upload.description}")
    for record in state.records[-3:]:
        print(f"\nLast sent: {record.posted_at}  {record.title}  [{record.status}]")
    return 0


def _run_authorize(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    if args.code:
        tokens = oauth.exchange_code(config, _extract_code(args.code), args.redirect_uri)
        print(f"Authorized. Access token expires {tokens.expires_at}.")
        if args.sync_secret:
            return _push_access_token(config)
        return 0

    url, state = oauth.authorize_url(config, args.redirect_uri)
    print("1. Open this URL and approve:\n")
    print(f"   {url}\n")
    print(f"2. You will be redirected to {args.redirect_uri}?code=...&state={state}")
    print("3. Copy the code value and run:\n")
    print(f"   python -m tiktok_poster authorize --redirect-uri {args.redirect_uri} --code <CODE>")
    return 0


def _extract_code(pasted: str) -> str:
    """Pull the code out of whatever the browser left in the address bar.

    The redirect lands on a plain page, so what is at hand is the whole URL,
    and its code is percent-encoded. Pasting that verbatim used to fail with a
    misleading error, so anything recognisable is accepted.
    """
    pasted = pasted.strip()
    if "code=" in pasted:
        codes = parse_qs(pasted.split("?", 1)[-1]).get("code")
        if codes:
            return codes[0]
    return unquote(pasted)


def _run_daily(args: argparse.Namespace) -> int:
    """Authorize and send the day's batch in one sitting.

    A sandbox app cannot refresh its token, so the consent has to be redone
    roughly once a day. Bundling it with the send keeps that to one paste.
    """
    config = load_config(Path.cwd())
    url, state = oauth.authorize_url(config, args.redirect_uri)
    print("1. Open this and approve:\n")
    print(f"   {url}\n")
    print("2. Paste the address you land on (the whole URL is fine):")
    try:
        pasted = input("   > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1
    if not pasted:
        print("Nothing pasted.")
        return 1
    if "code=" in pasted and state not in pasted:
        print("Warning: that redirect is from a different request than the one just printed.")

    try:
        oauth.exchange_code(config, _extract_code(pasted), args.redirect_uri)
    except tiktok.TikTokError as error:
        print(f"Could not authorize: {error}")
        return 1
    print("\nAuthorized.")

    if args.sync_secret:
        if _push_access_token(config) != 0:
            return 1

    if args.no_post:
        return 0
    print()
    return _run_post(argparse.Namespace(count=args.count, dry_run=False, no_push=args.no_push, delay=10.0, daily_limit=args.daily_limit))


def _push_access_token(config: Config) -> int:
    """Hand the fresh access token to Actions.

    The sandbox will not refresh, so the scheduled runs cannot obtain a
    credential on their own; this is what makes one browser approval cover a
    day of unattended sends. The value goes to gh over stdin so it never
    reaches a process listing or the shell history.
    """
    token = tiktok.load_tokens(config)
    if not token or not token.access_token:
        print("No access token to publish.")
        return 1
    try:
        result = subprocess.run(
            ["gh", "secret", "set", "TIKTOK_ACCESS_TOKEN"],
            input=token.access_token,
            text=True,
            capture_output=True,
            cwd=config.project_root,
        )
    except FileNotFoundError:
        print("gh is not installed, so the scheduled runs cannot be given the token.")
        return 1
    if result.returncode != 0:
        print(f"Could not store the token: {result.stderr.strip()}")
        return 1
    # A public marker of when today's token runs out, so the approval page can
    # tell whether it has anything to ask for. It carries no secret.
    marker = config.publish_dir.parent / "authorized.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"expires_at": token.expires_at}, indent=2), encoding="utf-8")

    print(f"Stored for the scheduled runs; they can post until {token.expires_at}.")
    return 0


# Posting is paced against the creator's day, not UTC's. Japan has no DST, so
# a fixed offset is exact and avoids depending on a tz database being present.
JST = timezone(timedelta(hours=9))


def _sent_today(state: State) -> int:
    today = datetime.now(JST).date()
    count = 0
    for record in state.records:
        try:
            stamp = datetime.fromisoformat(record.posted_at)
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(JST).date() == today:
            count += 1
    return count


def _run_post(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    try:
        pending = _queue(config)
    except FileNotFoundError as error:
        print(error)
        return 1
    if not pending:
        print("Nothing pending.")
        return 0
    state = load_state(config.state_path)

    wanted = args.count or config.posts_per_day
    # Slots fire every half hour so a carousel blocked by a full inbox is
    # retried soon rather than at the next of a handful of daily slots. The
    # day's quota is what keeps that frequency from turning into a flood.
    limit = config.posts_per_day if args.daily_limit is None else args.daily_limit
    if limit:
        already = _sent_today(state)
        room = limit - already
        if room <= 0:
            print(f"Already sent {already} today, which is the limit of {limit}.")
            return 0
        wanted = min(wanted, room)

    batch = pending[:wanted]
    print(f"Sending {len(batch)} carousel(s):")
    for upload in batch:
        print(f"  {upload.title}  ({len(upload.images)} slides)")

    if args.dry_run:
        print("\nDry run. Would send:")
        for upload in batch:
            print(f"\n  title      : {upload.title}")
            print(f"  description: {upload.description}")
            for url in upload.images:
                print(f"    {url}")
        return 0

    failures = 0
    for index, upload in enumerate(batch):
        # TikTok throttles the posting endpoint per user, and a long backlog
        # sent flat out looks like exactly what a throttle is there to stop.
        if index and args.delay:
            time.sleep(args.delay)
        try:
            # The images were published by `sync`, but a freshly synced batch
            # can still be mid-deploy, and TikTok rejects a URL it cannot fetch.
            pages.wait_until_live(list(upload.images))
            publish_id = tiktok.send_to_drafts(config, upload.title, upload.description, list(upload.images))
        except tiktok.DraftBacklogFull:
            # Every further send would fail the same way; the only cure is for
            # the account to publish what is already waiting.
            remaining = len(batch) - index
            print(f"\nTikTok is refusing new drafts: the inbox already has too many waiting.")
            print(f"Publish some from the TikTok app, then run this again to send the other {remaining}.")
            break
        except (tiktok.TikTokError, pages.PagesError) as error:
            failures += 1
            print(f"FAILED {upload.title}: {error}")
            continue
        state.add(upload.key, upload.title, publish_id)
        save_state(config.state_path, state)
        print(f"Sent to drafts: {upload.title}  ({publish_id})")

    if not args.no_push:
        try:
            if pages.push(config, f"state: sent {len(batch) - failures} carousel(s)", config.state_path):
                print("Recorded in git")
        except pages.PagesError as error:
            # The drafts already landed; a failed push only risks a repeat.
            print(f"Warning: could not push the state file: {error}")

    return 1 if failures else 0


def _run_check(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    state = load_state(config.state_path)
    targets = [record for record in state.records if record.status not in {"PUBLISH_COMPLETE", "FAILED"}]
    if not targets:
        print("Nothing awaiting confirmation.")
        return 0

    for record in targets[-args.limit :]:
        data = tiktok.fetch_status(config, record.publish_id)
        record.status = str(data.get("status") or record.status)
        print(f"{record.title}: {record.status}")
        if data.get("fail_reason"):
            print(f"  reason: {data['fail_reason']}")
    save_state(config.state_path, state)
    return 0


def _run_cleanup(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    keep_days = args.days if args.days is not None else config.keep_local_days
    state = load_state(config.state_path)
    themes = retention.expired_themes(config.source_dir, config.output_dir, state, keep_days)
    posts = retention.expired_posts(config.source_dir, config.output_dir, state, keep_days)
    if not themes and not posts:
        print(f"Nothing to clean up: nothing was sent more than {keep_days} days ago.")
        return 0
    freed = retention.purge(config.source_dir, config.output_dir, themes, dry_run=args.dry_run)
    freed += retention.purge_posts(config.source_dir, config.output_dir, posts, dry_run=args.dry_run)
    verb = "Would free" if args.dry_run else "Freed"
    for theme in themes:
        print(f"  「{theme.theme}」 {theme.posts} posts, last sent {theme.last_sent:%Y-%m-%d}")
    for post in posts:
        print(f"  {post.name}, sent {post.last_sent:%Y-%m-%d}")
    print(f"{verb} {freed / 1e6:.0f}MB across {len(themes)} theme(s) and {len(posts)} post(s) "
          f"sent more than {keep_days} days ago.")
    return 0


# Posting lives in the Actions workflow, which is where the daily quota, the
# six-draft inbox cap and the committed send state are enforced. Catching up
# from this PC means asking Actions to run now, never sending from here: a
# local send would count against a state file that may not have the morning's
# Actions commits in it yet.
POST_WORKFLOW = "post.yml"
# A run that starts with less than this left on the token fails partway.
APPROVAL_MARGIN = timedelta(minutes=30)


def _authorized_until(config: Config) -> datetime | None:
    """When the token Actions holds runs out, as published in docs/authorized.json.

    state/tokens.json is not evidence: it exists after a local authorize even
    when the token was never handed to Actions.
    """
    marker = config.publish_dir.parent / "authorized.json"
    try:
        stamp = datetime.fromisoformat(json.loads(marker.read_text(encoding="utf-8"))["expires_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _approval_page(config: Config) -> str:
    base = config.pages_base_url.rstrip("/")
    return (base[: -len("/media")] if base.endswith("/media") else base) + "/"


def _prompt_for_approval(config: Config, today: str) -> bool:
    """Open the approval page, at most once a day. Returns whether it opened."""
    marker = config.project_root / "logs" / "approval_prompted"
    try:
        if marker.read_text(encoding="utf-8").strip() == today:
            return False
    except OSError:
        pass
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(today, encoding="utf-8")
    opener = shutil.which("powershell.exe")
    if opener:
        subprocess.run(
            [opener, "-NoProfile", "-Command", f"Start-Process '{_approval_page(config)}'"],
            capture_output=True,
        )
    return True


def _run_catch_up(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    now = datetime.now(timezone.utc)
    already = _sent_today(load_state(config.state_path))
    if already >= config.posts_per_day:
        print(f"Already sent {already} today, which is the limit of {config.posts_per_day}.")
        return 0

    expires = _authorized_until(config)
    if expires is None or expires - now < APPROVAL_MARGIN:
        print(f"Sent {already} of {config.posts_per_day} today, but today's approval is missing.")
        print(f"Approve at {_approval_page(config)} and posting resumes on the next run.")
        if not args.dry_run and _prompt_for_approval(config, datetime.now(JST).date().isoformat()):
            print("Opened the approval page.")
        return 0

    print(f"Sent {already} of {config.posts_per_day} today; starting {POST_WORKFLOW} to send the rest.")
    if args.dry_run:
        return 0
    try:
        result = subprocess.run(
            ["gh", "workflow", "run", POST_WORKFLOW],
            capture_output=True,
            text=True,
            cwd=config.project_root,
        )
    except FileNotFoundError:
        print("gh is not installed, so the posting workflow cannot be started.")
        return 1
    if result.returncode != 0:
        print(f"Could not start {POST_WORKFLOW}: {result.stderr.strip()}")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiktok-poster", description="Send MBTI carousels to TikTok drafts")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Convert every carousel and publish it (needs the source images)")
    sync.add_argument("--dry-run", action="store_true", help="Convert and write the manifest without pushing")

    sub.add_parser("status", help="Show inventory and what is queued next")

    authorize = sub.add_parser("authorize", help="Run the one-time OAuth consent")
    authorize.add_argument("--redirect-uri", required=True, help="Must match the app's registered redirect URI")
    authorize.add_argument("--code", help="The redirect URL, or just its code, pasted back from the browser")
    authorize.add_argument(
        "--sync-secret",
        action="store_true",
        help="Give the fresh access token to GitHub Actions",
    )

    post = sub.add_parser("post", help="Send the next carousels to drafts")
    post.add_argument("--count", type=int, help="How many to send (default POSTS_PER_DAY)")
    post.add_argument("--dry-run", action="store_true", help="Print what would be sent, without calling TikTok")
    post.add_argument("--no-push", action="store_true", help="Do not commit the state file")
    post.add_argument("--delay", type=float, default=10.0, help="Seconds to wait between sends (default 10)")
    post.add_argument(
        "--daily-limit",
        type=int,
        default=None,
        help="Most to send in one JST day (default POSTS_PER_DAY; 0 for no limit)",
    )

    daily = sub.add_parser("daily", help="Re-authorize and send the day's batch in one go")
    daily.add_argument(
        "--redirect-uri",
        default="https://ryota-sotoguchi.github.io/post/",
        help="Must match the app's registered redirect URI",
    )
    daily.add_argument("--count", type=int, help="How many to send (default POSTS_PER_DAY)")
    daily.add_argument("--no-push", action="store_true", help="Do not commit the state file")
    daily.add_argument(
        "--sync-secret",
        action="store_true",
        help="Give the fresh access token to GitHub Actions so the day's scheduled runs can post",
    )
    daily.add_argument("--no-post", action="store_true", help="Only authorize; send nothing now")
    daily.add_argument("--daily-limit", type=int, default=None, help="Most to send in one JST day")

    check = sub.add_parser("check", help="Poll TikTok for the status of sent carousels")
    check.add_argument("--limit", type=int, default=10)

    cleanup = sub.add_parser("cleanup", help="Drop local slide images for themes sent long ago")
    cleanup.add_argument("--days", type=int, default=None, help="Keep window in days (default KEEP_LOCAL_DAYS)")
    cleanup.add_argument("--dry-run", action="store_true", help="Report what would be removed")

    catch_up = sub.add_parser("catch-up", help="If today's drafts have not all gone out, start the posting workflow")
    catch_up.add_argument("--dry-run", action="store_true", help="Report the decision without acting on it")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    handlers = {
        "sync": _run_sync,
        "status": _run_status,
        "authorize": _run_authorize,
        "post": _run_post,
        "daily": _run_daily,
        "check": _run_check,
        "cleanup": _run_cleanup,
        "catch-up": _run_catch_up,
    }
    raise SystemExit(handlers[args.command](args))


if __name__ == "__main__":
    main()
