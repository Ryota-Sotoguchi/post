from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import Upload, scan_fresh, send_order

from .conftest import write_post


def test_scan_reads_the_title_and_caption_the_generator_wrote(source_tree: Path) -> None:
    posts = scan_fresh(source_tree)

    assert [post.key for post in posts] == [
        "posts/00001-gallery",
        "posts/00002-manual",
        "posts/L0001-manual",
        "posts/L0002-manual",
    ]
    assert posts[0].title == "既読スルーされた時の16タイプ"
    assert posts[0].description.startswith("既読スルーされた時の16タイプのフック")
    assert len(posts[0].slides) == 7


def test_scan_marks_the_back_catalogue_as_filler(source_tree: Path) -> None:
    posts = {post.key: post.filler for post in scan_fresh(source_tree)}

    assert posts["posts/00001-gallery"] is False
    assert posts["posts/L0001-manual"] is True


def test_scan_skips_a_post_still_being_written(source_tree: Path) -> None:
    # post.json is written last, so a folder without it is mid-export.
    assert "posts/00003-ranking" not in [post.key for post in scan_fresh(source_tree)]


def test_scan_of_a_missing_handoff_folder_is_empty(tmp_path: Path) -> None:
    assert scan_fresh(tmp_path) == []


def test_slides_are_ordered_numerically(tmp_path: Path) -> None:
    folder = write_post(tmp_path, "00009-manual", "manual", "T", False, slides=0)
    for index in (10, 2, 1):
        Image.new("RGB", (8, 8)).save(folder / f"slide_{index:02d}.png")

    assert [path.name for path in scan_fresh(tmp_path)[0].slides] == [
        "slide_01.png", "slide_02.png", "slide_10.png",
    ]


def test_key_is_ascii_so_it_can_sit_in_a_url(source_tree: Path) -> None:
    # A PULL_FROM_URL target must be a plain URL TikTok can fetch.
    for post in scan_fresh(source_tree):
        assert post.key.isascii(), post.key


def _upload(key: str, filler: bool = False) -> Upload:
    return Upload(key=f"posts/{key}", theme="manual", title=key, description="#MBTI",
                  images=("https://example.test/a.jpg",), filler=filler)


def test_send_order_is_the_order_the_posts_were_made() -> None:
    uploads = [_upload("00002-manual"), _upload("00001-gallery"), _upload("00003-ranking")]

    assert [upload.key for upload in send_order(uploads, [])] == [
        "posts/00001-gallery", "posts/00002-manual", "posts/00003-ranking",
    ]


def test_filler_comes_after_everything_written() -> None:
    uploads = [_upload("L0001-manual", filler=True), _upload("00002-manual"),
               _upload("L0002-manual", filler=True), _upload("00001-gallery")]

    assert [upload.key for upload in send_order(uploads, [])] == [
        "posts/00001-gallery", "posts/00002-manual", "posts/L0001-manual", "posts/L0002-manual",
    ]


def test_what_went_out_is_not_offered_again() -> None:
    uploads = [_upload("00001-gallery"), _upload("00002-manual"), _upload("L0001-manual", filler=True)]

    queue = send_order(uploads, ["posts/00001-gallery"])

    assert [upload.key for upload in queue] == ["posts/00002-manual", "posts/L0001-manual"]


def test_rewriting_an_unchanged_manifest_leaves_the_file_alone(tmp_path) -> None:
    # sync runs several times a day and usually finds nothing new; a fresh
    # timestamp every time made each run a one-line commit and a Pages build.
    from datetime import datetime, timezone
    from unittest.mock import patch

    from tiktok_poster.catalog import write_manifest

    path = tmp_path / "manifest.json"
    uploads = [_upload("00001-gallery")]
    more = uploads + [_upload("00002-manual")]

    def at(hour):
        # Different hours, so an unconditional rewrite would change the stamp.
        clock = patch("tiktok_poster.catalog.datetime")
        mocked = clock.start()
        mocked.now.return_value = datetime(2026, 9, 16, hour, tzinfo=timezone.utc)
        return clock

    clock = at(8)
    write_manifest(path, uploads, "https://x")
    clock.stop()
    first = path.read_text(encoding="utf-8")

    clock = at(12)
    write_manifest(path, uploads, "https://x")
    clock.stop()
    assert path.read_text(encoding="utf-8") == first

    clock = at(16)
    write_manifest(path, more, "https://x")
    clock.stop()
    assert '"2026-09-16T16:00:00+00:00"' in path.read_text(encoding="utf-8")


def test_the_manifest_carries_the_filler_flag(tmp_path) -> None:
    # The Actions runner never sees the source folders, so the flag that
    # decides send order has to survive in the manifest.
    from tiktok_poster.catalog import load_manifest, write_manifest

    path = tmp_path / "manifest.json"
    write_manifest(path, [_upload("00001-gallery"), _upload("L0001-manual", filler=True)], "https://x")

    assert [upload.filler for upload in load_manifest(path)] == [False, True]
    assert json.loads(path.read_text(encoding="utf-8"))["posts"][1]["filler"] is True
