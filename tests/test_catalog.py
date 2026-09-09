from __future__ import annotations

from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import Upload, ready_themes, scan, send_order


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
