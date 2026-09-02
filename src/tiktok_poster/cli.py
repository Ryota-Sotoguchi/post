from __future__ import annotations

import argparse
from pathlib import Path

from tiktok_poster import media, oauth, pages, tiktok
from tiktok_poster.catalog import Post, scan
from tiktok_poster.config import Config, load_config
from tiktok_poster.state import load_state, save_state


def _pending(config: Config) -> list[Post]:
    posted = load_state(config.state_path).posted_keys
    return [post for post in scan(config.source_dir) if post.key not in posted]


def _run_status(_args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    all_posts = scan(config.source_dir)
    state = load_state(config.state_path)
    pending = [post for post in all_posts if post.key not in state.posted_keys]

    print(f"Source        : {config.source_dir}")
    print(f"Themes        : {len({post.theme for post in all_posts})}")
    print(f"Carousels     : {len(all_posts)}")
    print(f"Sent          : {len(state.records)}")
    print(f"Pending       : {len(pending)}")
    if config.posts_per_day:
        print(f"Days of stock : {len(pending) // config.posts_per_day} at {config.posts_per_day}/day")
    print(f"Authorized    : {'yes' if tiktok.load_tokens(config) or config.is_authorized else 'no'}")
    print(f"Pages base URL: {config.pages_base_url or '(unset)'}")

    if pending:
        print("\nNext up:")
        for post in pending[: config.posts_per_day]:
            print(f"  {post.title}   {post.description}")
    for record in state.records[-3:]:
        print(f"\nLast sent: {record.posted_at}  {record.title}  [{record.status}]")
    return 0


def _run_authorize(args: argparse.Namespace) -> int:
    config = load_config(Path.cwd())
    if args.code:
        tokens = oauth.exchange_code(config, args.code, args.redirect_uri)
        print(f"Authorized. Tokens stored in {tiktok.tokens_path(config)}")
        print(f"Refresh token valid until roughly {tokens.expires_at} for the access token; refresh token lasts a year.")
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
    pending = _pending(config)
    if not pending:
        print("Nothing pending.")
        return 0

    batch = pending[: args.count or config.posts_per_day]
    print(f"Preparing {len(batch)} carousel(s):")
    for post in batch:
        print(f"  {post.title}  ({len(post.slides)} slides)")

    for post in batch:
        media.publish_post(config, post)

    state = load_state(config.state_path)
    # Keep the batch plus a little history reachable; TikTok pulls the images
    # asynchronously, so a URL cannot be dropped the moment it is sent.
    keep = {post.key for post in batch}
    keep.update(record.key for record in state.records[-config.keep_published_posts :])
    removed = media.prune(config, keep)
    if removed:
        print(f"Pruned {len(removed)} published carousel(s)")

    urls_by_key = {post.key: media.public_urls(config, post) for post in batch}

    if args.dry_run:
        print("\nDry run. Would send:")
        for post in batch:
            print(f"\n  title      : {post.title}")
            print(f"  description: {post.description}")
            for url in urls_by_key[post.key]:
                print(f"    {url}")
        return 0

    try:
        if pages.push(config, f"media: publish {len(batch)} carousel(s)"):
            print("Pushed media to GitHub Pages")
        for post in batch:
            pages.wait_until_live(urls_by_key[post.key])
    except pages.PagesError as error:
        # Nothing is recorded, so the next run retries this same batch.
        print(f"Could not publish the images: {error}")
        print("TikTok can only pull from a live URL, so no drafts were sent.")
        return 1
    print("Pages is serving the images")

    failures = 0
    for post in batch:
        try:
            publish_id = tiktok.send_to_drafts(config, post.title, post.description, urls_by_key[post.key])
        except tiktok.TikTokError as error:
            failures += 1
            print(f"FAILED {post.title}: {error}")
            continue
        state.add(post.key, post.title, publish_id)
        save_state(config.state_path, state)
        print(f"Sent to drafts: {post.title}  ({publish_id})")

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

    sub.add_parser("status", help="Show inventory and what is queued next")

    authorize = sub.add_parser("authorize", help="Run the one-time OAuth consent")
    authorize.add_argument("--redirect-uri", required=True, help="Must match the app's registered redirect URI")
    authorize.add_argument("--code", help="Authorization code pasted back from the redirect")

    post = sub.add_parser("post", help="Publish the next carousels and send them to drafts")
    post.add_argument("--count", type=int, help="How many to send (default POSTS_PER_DAY)")
    post.add_argument("--dry-run", action="store_true", help="Convert and print, without pushing or calling TikTok")

    check = sub.add_parser("check", help="Poll TikTok for the status of sent carousels")
    check.add_argument("--limit", type=int, default=10)

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    handlers = {
        "status": _run_status,
        "authorize": _run_authorize,
        "post": _run_post,
        "check": _run_check,
    }
    raise SystemExit(handlers[args.command](args))


if __name__ == "__main__":
    main()
