from __future__ import annotations

from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import scan
from tiktok_poster.config import Config
from tiktok_poster.media import post_publish_dir, prune, public_urls, publish_post


def test_slides_are_written_as_jpeg(config: Config) -> None:
    # TikTok rejects PNG for photo posts; the renderer only produces PNG.
    post = scan(config.source_dir)[0]
    written = publish_post(config, post)

    assert [path.name for path in written] == [f"{i:02d}.jpg" for i in range(1, 8)]
    with Image.open(written[0]) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"


def test_oversized_slides_are_capped_at_1080(config: Config, tmp_path: Path) -> None:
    post_dir = config.source_dir / "がしんどい時に出るサイン" / "post_01_INTJ"
    Image.new("RGB", (2160, 3840), (10, 10, 10)).save(post_dir / "slide_01.png")

    post = next(p for p in scan(config.source_dir) if p.source_dir == post_dir)
    written = publish_post(config, post)
    with Image.open(written[0]) as image:
        assert image.width == 1080


def test_transparency_is_flattened_onto_white(config: Config) -> None:
    post_dir = config.source_dir / "がしんどい時に出るサイン" / "post_01_INTJ"
    transparent = Image.new("RGBA", (64, 64), (255, 0, 0, 0))
    transparent.save(post_dir / "slide_01.png")

    post = next(p for p in scan(config.source_dir) if p.source_dir == post_dir)
    written = publish_post(config, post)
    with Image.open(written[0]) as image:
        # Dropping alpha instead of flattening would render this black.
        assert image.convert("RGB").getpixel((10, 10)) == (255, 255, 255)


def test_republishing_replaces_the_previous_files(config: Config) -> None:
    post = scan(config.source_dir)[0]
    publish_post(config, post)
    stale = post_publish_dir(config, post) / "99.jpg"
    stale.write_bytes(b"stale")

    publish_post(config, post)
    assert not stale.exists()


def test_public_urls_follow_the_verified_prefix(config: Config) -> None:
    post = scan(config.source_dir)[0]
    publish_post(config, post)
    urls = public_urls(config, post)

    assert len(urls) == 7
    assert all(url.startswith(f"{config.pages_base_url}/{post.theme_slug}/") for url in urls)
    assert urls[0].endswith("/01.jpg")


def test_prune_keeps_only_the_named_carousels(config: Config) -> None:
    posts = scan(config.source_dir)[:3]
    for post in posts:
        publish_post(config, post)

    removed = prune(config, {posts[0].key})

    assert len(removed) == 2
    assert post_publish_dir(config, posts[0]).exists()
    assert not post_publish_dir(config, posts[1]).exists()


def test_prune_clears_theme_folders_it_empties(config: Config) -> None:
    post = scan(config.source_dir)[0]
    publish_post(config, post)

    prune(config, set())

    assert not (config.publish_dir / post.theme_slug).exists()
