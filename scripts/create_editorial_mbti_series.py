from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mbti_tiktok_bot.catalog import MBTI_POST_ORDER, TYPE_DATA  # noqa: E402
from mbti_tiktok_bot.config import load_config  # noqa: E402
from mbti_tiktok_bot.fonts import load_font as shared_load_font  # noqa: E402


WIDTH = 1080
HEIGHT = 1920
TARGET_DATE = date(2026, 7, 3)
SERIES_NAME = "が本命だけに見せる距離の縮め方"
SERIES_TITLE = "本命だけに見せる距離の縮め方"
THEME = "恋愛"
ASSET_DIR = ROOT / "assets" / "editorial_people"
SERIES_DIR = ROOT / "out" / SERIES_NAME
LOCAL_PHONE_DIR = load_config(ROOT).phone_export_dir / SERIES_NAME
STATE_PATH = ROOT / "state" / "series_state.json"
STATE_BACKUP_PATH = ROOT / "state" / "series_state.before_editorial_reset_20260703.json"
SERIES_TOTAL_POSTS = 16
IMAGE_SEQUENCE = [
    "rooftop_couple.png",
    "night_bar_man.png",
    "hotel_woman.png",
    "dining_group.png",
    "hotel_woman.png",
    "night_bar_man.png",
    "rooftop_couple.png",
]
NO_LINE_START = set("、。！？!?）」』】》〉")


@dataclass(frozen=True)
class SlideCopy:
    image_name: str
    eyebrow: str
    title: str
    body: str
    footer: str
    align: str = "left"


@dataclass(frozen=True)
class PostBuild:
    mbti_type: str
    output_dir: Path
    slides: list[Path]
    thumbnail: Path
    package: dict[str, Any]


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return shared_load_font(size, bold=bold)


def fit_cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_width, target_height = size
    source_ratio = source.width / source.height
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        new_height = target_height
        new_width = round(new_height * source_ratio)
    else:
        new_width = target_width
        new_height = round(new_width / source_ratio)
    resized = source.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))


def add_vertical_gradient(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        alpha = int(40 + 205 * max(0, (ratio - 0.18) / 0.82) ** 1.55)
        draw.line((0, y, WIDTH, y), fill=(0, 0, 0, min(alpha, 230)))
    image.alpha_composite(overlay)
    return image


def add_side_vignette(image: Image.Image, align: str) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if align == "right":
        for x in range(WIDTH):
            alpha = int(130 * max(0, 1 - x / WIDTH) ** 1.8)
            draw.line((x, 0, x, HEIGHT), fill=(0, 0, 0, alpha))
    else:
        for x in range(WIDTH):
            alpha = int(118 * max(0, x / WIDTH) ** 1.8)
            draw.line((x, 0, x, HEIGHT), fill=(0, 0, 0, alpha))
    image.alpha_composite(overlay)
    return image


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: int = 8) -> tuple[int, int]:
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        current = ""
        for char in raw_line:
            trial = current + char
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
                continue
            if current and char in NO_LINE_START:
                current += char
                continue
            if current:
                lines.append(current)
            current = char
        if current:
            lines.append(current)
    return "\n".join(lines)


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
    *,
    bold: bool = False,
    min_size: int = 28,
    spacing: int = 10,
) -> tuple[str, ImageFont.ImageFont, int]:
    for size in range(start_size, min_size - 1, -2):
        font = load_font(size, bold=bold)
        wrapped = wrap_text(draw, text, font, max_width)
        _, height = text_bbox(draw, wrapped, font, spacing=spacing)
        if height <= max_height:
            return wrapped, font, spacing
    font = load_font(min_size, bold=bold)
    return wrap_text(draw, text, font, max_width), font, spacing


def draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    spacing: int = 8,
    stroke_width: int = 0,
    anchor: str | None = None,
) -> None:
    x, y = xy
    draw.multiline_text(
        (x + 4, y + 6),
        text,
        font=font,
        fill=(0, 0, 0, 150),
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 120),
        anchor=anchor,
    )
    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=fill,
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 120),
        anchor=anchor,
    )


def draw_pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
) -> None:
    x, y = xy
    pad_x = 24
    pad_y = 13
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0] + pad_x * 2
    height = box[3] - box[1] + pad_y * 2
    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=height // 2,
        fill=(14, 18, 22, 178),
        outline=(229, 202, 150, 210),
        width=2,
    )
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=(245, 230, 196, 255))


def draw_glass_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=32, fill=(8, 10, 13, 168), outline=(255, 255, 255, 46), width=2)
    draw.rounded_rectangle((box[0], box[1], box[2], box[1] + 6), radius=3, fill=(226, 196, 134, 210))


def render_thumbnail(slide: SlideCopy, output_dir: Path, mbti_type: str) -> Path:
    source_path = ASSET_DIR / slide.image_name
    with Image.open(source_path) as opened:
        base = fit_cover(opened.convert("RGB"), (WIDTH, HEIGHT)).convert("RGBA")

    base = add_vertical_gradient(base)
    base = add_side_vignette(base, slide.align)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for y in range(HEIGHT):
        top_alpha = int(160 * max(0, 1 - y / 620) ** 1.35)
        bottom_alpha = int(210 * max(0, (y - 840) / (HEIGHT - 840)) ** 1.28)
        overlay_draw.line((0, y, WIDTH, y), fill=(0, 0, 0, min(top_alpha + bottom_alpha, 235)))
    overlay_draw.rounded_rectangle((54, 92, 760, 548), radius=38, fill=(5, 8, 11, 116))
    overlay_draw.rounded_rectangle((54, 1032, WIDTH - 54, 1518), radius=40, fill=(5, 8, 11, 150))
    base.alpha_composite(overlay)

    draw = ImageDraw.Draw(base)
    margin_x = 72
    draw_pill(draw, (margin_x, 112), "MBTI LOVE", font=load_font(34, bold=True))

    type_font = load_font(216, bold=True)
    draw_shadow_text(
        draw,
        (margin_x, 206),
        mbti_type,
        font=type_font,
        fill=(255, 251, 242, 255),
        spacing=0,
        stroke_width=3,
    )

    type_label = str(type_details(mbti_type)["archetype"])
    draw_pill(draw, (margin_x, 460), type_label, font=load_font(36, bold=True))

    wrapped_title, title_font, title_spacing = fit_text(
        draw,
        slide.title,
        WIDTH - margin_x * 2,
        330,
        106,
        bold=True,
        min_size=70,
        spacing=12,
    )
    draw_shadow_text(
        draw,
        (margin_x, 1092),
        wrapped_title,
        font=title_font,
        fill=(255, 251, 242, 255),
        spacing=title_spacing,
        stroke_width=2,
    )

    title_height = text_bbox(draw, wrapped_title, title_font, title_spacing)[1]
    hook_top = 1092 + title_height + 36
    wrapped_hook, hook_font, hook_spacing = fit_text(
        draw,
        slide.body,
        WIDTH - margin_x * 2,
        190,
        44,
        min_size=32,
        spacing=10,
    )
    draw.multiline_text(
        (margin_x, hook_top),
        wrapped_hook,
        font=hook_font,
        fill=(247, 242, 231, 245),
        spacing=hook_spacing,
    )

    thumbnail_path = output_dir / "slides" / "slide_01.png"
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(thumbnail_path, format="PNG", optimize=False, compress_level=3)
    return thumbnail_path


def render_slide(slide: SlideCopy, output_dir: Path, index: int) -> Path:
    source_path = ASSET_DIR / slide.image_name
    with Image.open(source_path) as opened:
        base = fit_cover(opened.convert("RGB"), (WIDTH, HEIGHT)).convert("RGBA")

    base = add_vertical_gradient(base)
    base = add_side_vignette(base, slide.align)

    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-200, 1310, 430, 2060), fill=(29, 150, 142, 54))
    glow_draw.ellipse((710, 220, 1260, 850), fill=(226, 196, 134, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(42))
    base.alpha_composite(glow)

    draw = ImageDraw.Draw(base)
    eyebrow_font = load_font(30, bold=True)
    footer_font = load_font(28, bold=True)

    margin_x = 72
    content_width = 936
    draw_pill(draw, (margin_x, 92), slide.eyebrow, font=eyebrow_font)

    wrapped_title, title_font, title_spacing = fit_text(
        draw,
        slide.title,
        content_width,
        360,
        100,
        bold=True,
        min_size=68,
        spacing=12,
    )
    title_y = 1148 if index == 0 else 1118
    draw_shadow_text(
        draw,
        (margin_x, title_y),
        wrapped_title,
        font=title_font,
        fill=(255, 251, 242, 255),
        spacing=title_spacing,
        stroke_width=1,
    )

    panel_top = title_y + text_bbox(draw, wrapped_title, title_font, title_spacing)[1] + 38
    panel = (margin_x, panel_top, WIDTH - margin_x, min(panel_top + 258, HEIGHT - 142))
    draw_glass_panel(draw, panel)

    wrapped_body, body_font, body_spacing = fit_text(
        draw,
        slide.body,
        panel[2] - panel[0] - 56,
        panel[3] - panel[1] - 58,
        48,
        min_size=34,
        spacing=10,
    )
    draw.multiline_text(
        (panel[0] + 28, panel[1] + 34),
        wrapped_body,
        font=body_font,
        fill=(247, 242, 231, 245),
        spacing=body_spacing,
    )

    draw.line((margin_x, HEIGHT - 94, WIDTH - margin_x - 140, HEIGHT - 94), fill=(226, 196, 134, 180), width=3)
    draw.text((WIDTH - margin_x, HEIGHT - 118), slide.footer, font=footer_font, fill=(245, 230, 196, 230), anchor="ra")

    destination = output_dir / "slides" / f"slide_{index + 1:02d}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(destination, format="PNG", optimize=False, compress_level=3)
    return destination


def topic_key(topic_name: str) -> str:
    return "generated_" + hashlib.sha1(topic_name.encode("utf-8")).hexdigest()[:12]


def type_details(mbti_type: str) -> dict[str, Any]:
    return dict(TYPE_DATA[mbti_type])


def build_slides(mbti_type: str) -> list[SlideCopy]:
    details = type_details(mbti_type)
    archetype = str(details["archetype"])
    traits = [str(item) for item in details["traits"]]
    love = str(details["love"])
    line_style = str(details["line"])
    strategy = str(details["攻略"])
    friend = str(details["friend"])
    trait_summary = " / ".join(traits[:2])

    bodies = [
        f"{archetype}タイプは、{love}。距離の詰め方に本気度がかなり出る。",
        f"{line_style}。早さよりも、あなたへの返し方がいつもより丁寧になる。",
        f"{love}。忙しくても、会う理由や次の予定を少しずつ作ろうとする。",
        f"{friend}。無理に踏み込むより、続く距離感を確認しながら近づく。",
        f"{trait_summary}。小さな変化に気づくと、その人に合う支え方を選ぶ。",
        f"{strategy}。派手な駆け引きより、「この人は合う」と思える安心感が効く。",
        f"{mbti_type}の本命サインは派手さより積み重ね。あとで見返して答え合わせして。",
    ]
    titles = [
        "本命だけに見せる\n距離の縮め方",
        "返信の温度が\n変わる",
        "予定の中に\nあなたが入る",
        "安心できる距離を\n探ってくる",
        "心配の仕方が\n具体的になる",
        "刺さる距離感を\n外さない",
        "当てはまったら\n保存",
    ]
    eyebrows = [
        f"MBTI LOVE / {mbti_type}",
        f"{mbti_type} / SIGN 01",
        f"{mbti_type} / SIGN 02",
        f"{mbti_type} / SIGN 03",
        f"{mbti_type} / SIGN 04",
        f"{mbti_type} / SIGN 05",
        f"{mbti_type} / SAVE",
    ]
    aligns = ["left", "left", "right", "left", "right", "left", "left"]
    return [
        SlideCopy(
            image_name=IMAGE_SEQUENCE[index],
            eyebrow=eyebrows[index],
            title=titles[index],
            body=bodies[index],
            footer=f"{index + 1:02d} / 07",
            align=aligns[index],
        )
        for index in range(7)
    ]


def build_caption(mbti_type: str, slides: list[SlideCopy]) -> str:
    hook = slides[0].body
    highlights = " / ".join(slide.title.replace("\n", "") for slide in slides[1:4])
    hashtags = " ".join(build_hashtags(mbti_type))
    return "\n".join(
        [
            f"{mbti_type}{SERIES_NAME}",
            hook,
            f"見るポイントは、{highlights}。",
            "当てはまったら保存して、あとで答え合わせしてみて。",
            hashtags,
        ]
    )


def build_hashtags(mbti_type: str) -> list[str]:
    return ["#MBTI", "#mbti診断", "#16personalities", "#恋愛", "#本命サイン", f"#{mbti_type}"]


def build_package(
    mbti_type: str,
    post_index: int,
    slides: list[SlideCopy],
    output_dir: Path,
    rendered: list[Path],
    thumbnail: Path,
) -> dict[str, Any]:
    details = type_details(mbti_type)
    title = f"{mbti_type}{SERIES_NAME}"
    hook = slides[0].body
    content_slides = slides[1:6]
    caption = build_caption(mbti_type, slides)
    scenes = [
        {
            "title": slide.title.replace("\n", ""),
            "body": slide.body,
            "duration_seconds": 4.0,
        }
        for slide in content_slides
    ]
    return {
        "post_date": TARGET_DATE.isoformat(),
        "mbti_type": mbti_type,
        "archetype_name": str(details["archetype"]),
        "group_name": str(details["group"]),
        "title": title,
        "series_name": SERIES_NAME,
        "format_name": SERIES_NAME,
        "theme": THEME,
        "hook": hook,
        "narration": "\n".join([title, hook] + [f"{scene['title']}。{scene['body']}" for scene in scenes]),
        "caption": caption,
        "hashtags": build_hashtags(mbti_type),
        "global_post_index": post_index,
        "daily_slot": post_index + 1,
        "series_post_number": post_index + 1,
        "series_total_posts": SERIES_TOTAL_POSTS,
        "style": "editorial fashion photo with Japanese text overlay",
        "dimensions": {"width": WIDTH, "height": HEIGHT},
        "source_assets": [str((ASSET_DIR / slide.image_name).resolve()) for slide in slides],
        "thumbnail": str(thumbnail.resolve()),
        "slides": [str(path.resolve()) for path in rendered],
        "copy": [asdict(slide) for slide in slides],
        "scenes": scenes,
        "output_dir": str(output_dir.resolve()),
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_post_files(mbti_type: str, post_index: int) -> PostBuild:
    output_dir = SERIES_DIR / f"post_{post_index + 1:02d}_{mbti_type}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    slides = build_slides(mbti_type)
    thumbnail_path = render_thumbnail(slides[0], output_dir, mbti_type)
    rendered = [thumbnail_path] + [render_slide(slide, output_dir, index) for index, slide in enumerate(slides[1:], start=1)]
    package = build_package(mbti_type, post_index, slides, output_dir, rendered, thumbnail_path)

    write_json(output_dir / "package.json", package)
    (output_dir / "caption.txt").write_text(package["caption"], encoding="utf-8")
    (output_dir / "caption_template.txt").write_text(
        package["caption"].replace(f"#{mbti_type}", "#MBTI_TYPE"),
        encoding="utf-8",
    )
    return PostBuild(mbti_type=mbti_type, output_dir=output_dir, slides=rendered, thumbnail=thumbnail_path, package=package)


def write_series_plan(posts: list[PostBuild]) -> None:
    items = [
        {
            "post_date": TARGET_DATE.isoformat(),
            "title": post.package["title"],
            "series_name": SERIES_NAME,
            "format_name": SERIES_NAME,
            "theme": THEME,
            "mbti_type": post.mbti_type,
            "daily_slot": index + 1,
            "series_post_number": index + 1,
            "global_post_index": index,
            "output_dir": str(post.output_dir.resolve()),
            "thumbnail": str(post.thumbnail.resolve()),
        }
        for index, post in enumerate(posts)
    ]
    write_json(SERIES_DIR / "series_plan.json", items)


def write_local_phone_export(posts: list[PostBuild]) -> None:
    LOCAL_PHONE_DIR.mkdir(parents=True, exist_ok=True)
    for post in posts:
        destination = LOCAL_PHONE_DIR / post.output_dir.name
        destination.mkdir(parents=True, exist_ok=True)
        stale_thumbnail = destination / "thumbnail.png"
        if stale_thumbnail.exists():
            stale_thumbnail.unlink()
        for slide in post.slides:
            shutil.copy2(slide, destination / slide.name)


def reset_series_state() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STATE_PATH.exists() and not STATE_BACKUP_PATH.exists():
        shutil.copy2(STATE_PATH, STATE_BACKUP_PATH)
    write_json(
        STATE_PATH,
        {
            "next_post_index": SERIES_TOTAL_POSTS,
            "topic_history": [
                {
                    "key": topic_key(SERIES_NAME),
                    "name": SERIES_NAME,
                    "theme": THEME,
                    "blueprint": "like_attitude",
                    "source": "procedural",
                }
            ],
        },
    )


def main() -> None:
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    posts = [write_post_files(mbti_type, index) for index, mbti_type in enumerate(MBTI_POST_ORDER)]
    write_series_plan(posts)
    reset_series_state()
    phone_export_message = f"Local phone export: {LOCAL_PHONE_DIR}"
    try:
        write_local_phone_export(posts)
    except PermissionError as exc:
        phone_export_message = f"Local phone export skipped: {exc}"
    print(f"Created {len(posts)} posts / {len(posts) * 7} slides")
    print(f"Output: {SERIES_DIR}")
    print(phone_export_message)
    print(f"Series state reset: next_post_index={SERIES_TOTAL_POSTS}")


if __name__ == "__main__":
    main()
