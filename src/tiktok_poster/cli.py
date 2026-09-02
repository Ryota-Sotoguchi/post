from __future__ import annotations

import argparse
from pathlib import Path

from tiktok_poster import media, oauth, pages, tiktok
from tiktok_poster.catalog import Upload, load_manifest, manifest_path, scan, write_manifest
from tiktok_poster.config import Config, load_config
from tiktok_poster.state import load_state, save_state


def _manifest(config: Config) -> list[Upload]:
    return load_manifest(manifest_path(config.publish_dir))


def _pending(config: Config) -> list[Upload]:
    posted = load_state(config.state_path).posted_keys
    return [upload for upload in _manifest(config) if upload.key not in posted]


def _run_sync(args: argparse.Namespace) -> int:
    """Convert every carousel and record it in the manifest.

    Runs only where the source images are: it is the one step that needs the
    OneDrive folder, and it leaves behind everything the posting step needs.
    """
    config = load_config(Path.cwd())
    posts = scan(config.source_dir)
    print(f"Found {len(posts)} carousel(s) across {len({post.theme for post in posts})} theme(s)")

    uploads: list[Upload] = []
    for index, post in enumerate(posts, start=1):
        media.publish_post(config, post)
        uploads.append(
            Upload(
                key=post.key,
                title=post.title,
                description=post.description,
                images=tuple(media.public_urls(config, post)),
            )
        )
        if index % 20 == 0 or index == len(posts):
            print(f"  converted {index}/{len(posts)}")

    path = write_manifest(manifest_path(config.publish_dir), uploads, config.pages_base_url)
    print(f"Wrote {path}")

    if args.dry_run:
        print("Dry run. Nothing pushed.")
        return 0

    try:
        if pages.push(config, f"media: sync {len(uploads)} carousel(s)"):
            print("Pushed media and manifest")
        else:
            print("Already up to date")
    except pages.PagesError as error:
        print(f"Could not push: {error}")
        return 1
    return 0


def _run_status(_args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    state = load_state(config.state_path)
    try:
        uploads = _manifest(config)
    except FileNotFoundError as error:
        print(error)
        return 1
    pending = [upload for upload in uploads if upload.key not in state.posted_keys]

    print(f"Carousels     : {len(uploads)}")
    print(f"Sent          : {len(state.records)}")
    print(f"Pending       : {len(pending)}")
    if config.posts_per_day:
        print(f"Days of stock : {len(pending) // config.posts_per_day} at {config.posts_per_day}/day")
    print(f"Authorized    : {'yes' if tiktok.load_tokens(config) or config.is_authorized else 'no'}")
    print(f"Pages base URL: {config.pages_base_url or '(unset)'}")

    if pending:
        print("\nNext up:")
        for upload in pending[: config.posts_per_day]:
            print(f"  {upload.title}   {upload.description}")
    for record in state.records[-3:]:
        print(f"\nLast sent: {record.posted_at}  {record.title}  [{record.status}]")
    return 0


def _run_authorize(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    if args.code:
        tokens = oauth.exchange_code(config, args.code, args.redirect_uri)
        print(f"Authorized. Tokens stored in {tiktok.tokens_path(config)}")
        print(f"Access token expires {tokens.expires_at}; the refresh token lasts a year.")
        return 0

    url, state = oauth.authorize_url(config, args.redirect_uri)
    print("1. Open this URL and approve:\n")
    print(f"   {url}\n")
    print(f"2. You will be redirected to {args.redirect_uri}?code=...&state={state}")
    print("3. Copy the code value and run:\n")
    print(f"   python -m tiktok_poster authorize --redirect-uri {args.redirect_uri} --code <CODE>")
    return 0


def _run_post(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    try:
        pending = _pending(config)
    except FileNotFoundError as error:
        print(error)
        return 1
    if not pending:
        print("Nothing pending.")
        return 0

    batch = pending[: args.count or config.posts_per_day]
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

    state = load_state(config.state_path)
    failures = 0
    for upload in batch:
        try:
            # The images were published by `sync`, but a freshly synced batch
            # can still be mid-deploy, and TikTok rejects a URL it cannot fetch.
            pages.wait_until_live(list(upload.images))
            publish_id = tiktok.send_to_drafts(config, upload.title, upload.description, list(upload.images))
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiktok-poster", description="Send MBTI carousels to TikTok drafts")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Convert every carousel and publish it (needs the source images)")
    sync.add_argument("--dry-run", action="store_true", help="Convert and write the manifest without pushing")

    sub.add_parser("status", help="Show inventory and what is queued next")

    authorize = sub.add_parser("authorize", help="Run the one-time OAuth consent")
    authorize.add_argument("--redirect-uri", required=True, help="Must match the app's registered redirect URI")
    authorize.add_argument("--code", help="Authorization code pasted back from the redirect")

    post = sub.add_parser("post", help="Send the next carousels to drafts")
    post.add_argument("--count", type=int, help="How many to send (default POSTS_PER_DAY)")
    post.add_argument("--dry-run", action="store_true", help="Print what would be sent, without calling TikTok")
    post.add_argument("--no-push", action="store_true", help="Do not commit the state file")

    check = sub.add_parser("check", help="Poll TikTok for the status of sent carousels")
    check.add_argument("--limit", type=int, default=10)

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    handlers = {
        "sync": _run_sync,
        "status": _run_status,
        "authorize": _run_authorize,
        "post": _run_post,
        "check": _run_check,
    }
    raise SystemExit(handlers[args.command](args))


if __name__ == "__main__":
    main()
