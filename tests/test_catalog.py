from __future__ import annotations

from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import scan


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
        ("が本命だけに見せる距離の縮め方", 1),
        ("が本命だけに見せる距離の縮め方", 2),
        ("が本命だけに見せる距離の縮め方", 10),
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
