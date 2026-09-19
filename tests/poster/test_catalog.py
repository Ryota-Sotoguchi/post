from __future__ import annotations

from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import Upload, ready_themes, scan, scan_fresh, send_order


def test_scan_finds_every_complete_carousel(source_tree: Path) -> None:
    posts = scan(source_tree)
    assert len(posts) == 4
    assert all(len(post.slides) == 7 for post in posts)


def test_scan_ignores_directories_that_are_not_posts(source_tree: Path) -> None:
    # A notes/ folder and a stray spreadsheet sit alongside the carousels.
    assert all(post.source_dir.name.startswith("post_") for post in scan(source_tree))


def test_posts_are_ordered_by_theme_then_slot(source_tree: Path) -> None:
    posts = scan(source_tree)
    assert [(post.theme, post.order) for post in posts] == [
        ("がしんどい時に出るサイン", 1),
        ("がしんどい時に出るサイン", 2),
        ("が本命だけに見せる距離の縮め方", 1),
        ("が本命だけに見せる距離の縮め方", 2),
    ]


def test_title_reads_as_type_then_theme(source_tree: Path) -> None:
    post = next(p for p in scan(source_tree) if p.mbti == "INTJ" and "本命" in p.theme)
    assert post.title == "INTJが本命だけに見せる距離の縮め方"


def test_hashtags_carry_the_type(source_tree: Path) -> None:
    post = scan(source_tree)[0]
    assert post.description == f"#恋愛 #MBTI #{post.mbti}"


def test_key_is_ascii_so_it_can_sit_in_a_url(source_tree: Path) -> None:
    # Theme names are Japanese; PULL_FROM_URL wants a plain fetchable URL.
    for post in scan(source_tree):
        assert post.key.isascii(), post.key


def test_slides_are_ordered_numerically(tmp_path: Path) -> None:
    post_dir = tmp_path / "theme" / "post_01_INTJ"
    post_dir.mkdir(parents=True)
    for index in (10, 2, 1):
        Image.new("RGB", (8, 8)).save(post_dir / f"slide_{index:02d}.png")
    slides = scan(tmp_path)[0].slides
    assert [path.name for path in slides] == ["slide_01.png", "slide_02.png", "slide_10.png"]


def _upload(theme_slug: str, slot: int, mbti: str = "INTJ") -> Upload:
    return Upload(
        key=f"{theme_slug}/post_{slot:02d}_{mbti}",
        theme=f"theme-{theme_slug}",
        title=f"{mbti}theme-{theme_slug}",
        description="#恋愛 #MBTI",
        images=("https://example.test/a.jpg",),
    )


def _theme(theme_slug: str, slots: range | list[int]) -> list[Upload]:
    return [_upload(theme_slug, slot) for slot in slots]


def test_ready_themes_holds_back_a_theme_that_is_barely_drawn(source_tree: Path) -> None:
    posts = scan(source_tree)
    ready, held = ready_themes(posts, minimum=2)
    assert not held
    assert len(ready) == 4

    ready, held = ready_themes(posts, minimum=3)
    # Neither fixture theme reaches three, so nothing may be published yet.
    assert held == {"がしんどい時に出るサイン": 2, "が本命だけに見せる距離の縮め方": 2}
    assert ready == []


def test_ready_themes_keeps_the_themes_that_are_far_enough_along(tmp_path: Path) -> None:
    source = tmp_path / "source"
    for theme, slots in (("厚いテーマ", range(1, 9)), ("薄いテーマ", range(1, 2))):
        for slot in slots:
            post_dir = source / theme / f"post_{slot:02d}_INTJ"
            post_dir.mkdir(parents=True)
            Image.new("RGB", (8, 8)).save(post_dir / "slide_01.png")

    ready, held = ready_themes(scan(source), minimum=8)
    assert held == {"薄いテーマ": 1}
    assert {post.theme for post in ready} == {"厚いテーマ"}


def test_send_order_waits_at_a_slot_that_is_not_published_yet() -> None:
    """The gap that started all this: eight sent, the ninth not drawn.

    Moving on to post_10, or to another theme, is what put four carousels of one
    theme in the drafts and then jumped ahead, so the whole queue stops here.
    """
    uploads = _theme("aaa", [1, 2, 3, 4, 5, 6, 7, 8, 10]) + _theme("bbb", range(1, 17))
    posted = [f"aaa/post_{slot:02d}_INTJ" for slot in range(1, 9)]

    queue, waiting = send_order(uploads, posted)

    assert waiting == ("aaa", 9)
    assert queue == []


def test_send_order_resumes_a_theme_at_the_slot_after_the_last_one_sent() -> None:
    uploads = _theme("aaa", range(1, 17))
    posted = [f"aaa/post_{slot:02d}_INTJ" for slot in range(1, 5)]

    queue, waiting = send_order(uploads, posted)

    assert waiting is None
    assert [upload.slot for upload in queue] == list(range(5, 17))


def test_send_order_finishes_a_started_theme_before_one_that_sorts_ahead_of_it() -> None:
    """A theme completed later must not cut into a theme already going out.

    `aaa` sits first in the manifest, but `bbb` was started first, so `bbb` is
    carried to its end before `aaa` begins.
    """
    uploads = _theme("aaa", range(1, 17)) + _theme("bbb", range(1, 17))
    posted = [f"bbb/post_{slot:02d}_INTJ" for slot in range(1, 3)]

    queue, waiting = send_order(uploads, posted)

    assert waiting is None
    assert [upload.key.split("/")[0] for upload in queue] == ["bbb"] * 14 + ["aaa"] * 16


def test_send_order_is_not_held_by_a_slot_that_already_went_out() -> None:
    """A theme whose source images were retired still counts as done."""
    uploads = _theme("bbb", range(1, 17))
    posted = [f"aaa/post_{slot:02d}_INTJ" for slot in range(1, 17)]

    queue, waiting = send_order(uploads, posted)

    assert waiting is None
    assert len(queue) == 16


def test_rewriting_an_unchanged_manifest_leaves_the_file_alone(tmp_path) -> None:
    # sync runs several times a day and usually finds nothing new; a fresh
    # timestamp every time made each run a one-line commit and a Pages build.
    from datetime import datetime, timezone
    from unittest.mock import patch

    from tiktok_poster.catalog import Upload, write_manifest

    path = tmp_path / "manifest.json"
    uploads = [Upload(key="a/post_01_INTJ", theme="t", title="T", description="#t", images=("https://x/1.jpg",))]
    more = uploads + [Upload(key="a/post_02_INTP", theme="t", title="T2", description="#t", images=("https://x/2.jpg",))]

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


def _fresh_post(source: Path, name: str, title: str = "INFJと相性がいいタイプ【恋愛】", meta: bool = True) -> Path:
    import json

    folder = source / "_posts" / name
    folder.mkdir(parents=True, exist_ok=True)
    for index in (1, 2):
        Image.new("RGB", (8, 8)).save(folder / f"slide_{index:02d}.png")
    if meta:
        (folder / "post.json").write_text(
            json.dumps({"key": name, "format": name.split("-")[1], "title": title, "description": "フック\n\n#MBTI"},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    return folder


def test_scan_fresh_reads_the_generators_own_title_and_caption(tmp_path: Path) -> None:
    _fresh_post(tmp_path, "00002-manual", title="ESFPの取扱説明書")
    _fresh_post(tmp_path, "00001-gallery", title="既読スルーされた時の16タイプ")

    posts = scan_fresh(tmp_path)

    assert [post.key for post in posts] == ["posts/00001-gallery", "posts/00002-manual"]
    assert posts[0].title == "既読スルーされた時の16タイプ"
    assert posts[0].description == "フック\n\n#MBTI"
    assert len(posts[0].slides) == 2


def test_scan_fresh_skips_a_post_still_being_written(tmp_path: Path) -> None:
    # post.json is written last, so a folder without it is mid-export.
    _fresh_post(tmp_path, "00001-gallery", meta=False)
    assert scan_fresh(tmp_path) == []


def test_the_themed_scan_does_not_mistake_the_fresh_folder_for_a_theme(tmp_path: Path) -> None:
    _fresh_post(tmp_path, "00001-gallery")
    assert scan(tmp_path) == []


def _fresh_upload(name: str) -> Upload:
    return Upload(key=f"posts/{name}", theme=name.split("-")[1], title=name, description="#MBTI",
                  images=("https://example.test/a.jpg",))


def test_send_order_puts_new_formats_first_and_the_old_themes_after() -> None:
    uploads = _theme("aaa", range(1, 4)) + [_fresh_upload("00002-manual"), _fresh_upload("00001-gallery")]

    queue, waiting = send_order(uploads, [], size=3)

    assert waiting is None
    assert [upload.key for upload in queue] == [
        "posts/00001-gallery",
        "posts/00002-manual",
        "aaa/post_01_INTJ",
        "aaa/post_02_INTJ",
        "aaa/post_03_INTJ",
    ]


def test_send_order_skips_new_posts_already_sent_without_disturbing_a_started_theme() -> None:
    uploads = _theme("aaa", range(1, 17)) + _theme("bbb", range(1, 17)) + [_fresh_upload("00001-gallery"),
                                                                        _fresh_upload("00002-manual")]
    posted = ["posts/00001-gallery", "bbb/post_01_INTJ"]

    queue, _ = send_order(uploads, posted)

    assert queue[0].key == "posts/00002-manual"
    assert [upload.key.split("/")[0] for upload in queue[1:]] == ["bbb"] * 15 + ["aaa"] * 16
