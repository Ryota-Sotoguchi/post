from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mbti_tiktok_bot.fonts import load_font as shared_load_font  # noqa: E402
WIDTH = 1080
HEIGHT = 1920
MBTI_TYPE = "ISTJ"
ASSET_DIR = ROOT / "assets" / "editorial_people"
OUT_DIR = ROOT / "out" / "editorial_ikemen_bijo_20260703"
SLIDES_DIR = OUT_DIR / "slides"


@dataclass(frozen=True)
class SlideCopy:
    image_name: str
    eyebrow: str
    title: str
    body: str
    footer: str
    align: str = "left"


SLIDES: list[SlideCopy] = [
    SlideCopy(
        image_name="rooftop_couple.png",
        eyebrow=f"MBTI LOVE / {MBTI_TYPE}",
        title="本命だけに見せる\n距離の縮め方",
        body="近づき方は静か。でも本気の相手には、ちゃんと特別扱いが出る。",
        footer="01 / 07",
    ),
    SlideCopy(
        image_name="night_bar_man.png",
        eyebrow=f"{MBTI_TYPE} / SIGN 01",
        title="返信の温度が\n安定する",
        body="急に甘くはならない。でも毎回、雑にしない。そこに本命感が出る。",
        footer="02 / 07",
    ),
    SlideCopy(
        image_name="hotel_woman.png",
        eyebrow=f"{MBTI_TYPE} / SIGN 02",
        title="予定を先に\n確保する",
        body="会える日を曖昧にしない。忙しくても、あなたのための枠を作る。",
        footer="03 / 07",
    ),
    SlideCopy(
        image_name="dining_group.png",
        eyebrow=f"{MBTI_TYPE} / SIGN 03",
        title="小さな約束を\n覚えている",
        body="好きなもの、苦手なこと。何気ない一言も、次にちゃんと活かしてくる。",
        footer="04 / 07",
    ),
    SlideCopy(
        image_name="hotel_woman.png",
        eyebrow=f"{MBTI_TYPE} / SIGN 04",
        title="心配が\n具体的になる",
        body="「大丈夫？」だけで終わらない。どうしたら楽になるかまで考えてくれる。",
        footer="05 / 07",
    ),
    SlideCopy(
        image_name="night_bar_man.png",
        eyebrow=f"{MBTI_TYPE} / SIGN 05",
        title="距離はゆっくり\nでも確実",
        body="本気ほど軽く踏み込まない。信頼できるまで、丁寧に近づいてくる。",
        footer="06 / 07",
    ),
    SlideCopy(
        image_name="rooftop_couple.png",
        eyebrow=f"{MBTI_TYPE} / SAVE",
        title="当てはまったら\n保存",
        body="友だちにもシェアして答え合わせ。あなたのタイプもコメントで教えて。",
        footer="07 / 07",
    ),
]


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
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=(14, 18, 22, 178), outline=(229, 202, 150, 210), width=2)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=(245, 230, 196, 255))


def draw_glass_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=32, fill=(8, 10, 13, 168), outline=(255, 255, 255, 46), width=2)
    draw.rounded_rectangle((box[0], box[1], box[2], box[1] + 6), radius=3, fill=(226, 196, 134, 210))


def render_thumbnail(slide: SlideCopy) -> Path:
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
        MBTI_TYPE,
        font=type_font,
        fill=(255, 251, 242, 255),
        spacing=0,
        stroke_width=3,
    )
    draw_pill(draw, (margin_x, 460), "LOVE SIGN", font=load_font(36, bold=True))

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

    thumbnail_path = SLIDES_DIR / "slide_01.png"
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(thumbnail_path, quality=95)
    return thumbnail_path


def render_slide(slide: SlideCopy, index: int) -> Path:
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
    body_font = load_font(48)

    margin_x = 72
    content_width = 936
    draw_pill(draw, (margin_x, 92), slide.eyebrow, font=eyebrow_font)

    title_max_height = 360
    wrapped_title, title_font, title_spacing = fit_text(
        draw,
        slide.title,
        content_width,
        title_max_height,
        104,
        bold=True,
        min_size=72,
        spacing=12,
    )
    title_y = 1158 if index == 0 else 1118
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

    wrapped_body, resolved_body_font, body_spacing = fit_text(
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
        font=resolved_body_font if resolved_body_font else body_font,
        fill=(247, 242, 231, 245),
        spacing=body_spacing,
    )

    draw.line((margin_x, HEIGHT - 94, WIDTH - margin_x - 140, HEIGHT - 94), fill=(226, 196, 134, 180), width=3)
    draw.text((WIDTH - margin_x, HEIGHT - 118), slide.footer, font=footer_font, fill=(245, 230, 196, 230), anchor="ra")

    destination = SLIDES_DIR / f"slide_{index + 1:02d}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(destination, quality=95)
    return destination


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)

    thumbnail_path = render_thumbnail(SLIDES[0])
    rendered = [thumbnail_path] + [render_slide(slide, index) for index, slide in enumerate(SLIDES[1:], start=1)]

    caption = (
        "ISTJが本命だけに見せる距離の縮め方。\n"
        "静かな優しさ、安定した返信、具体的な心配が出ていたら本気度高め。\n\n"
        "#MBTI #ISTJ #恋愛 #本命サイン #性格診断 #大人の恋愛"
    )
    (OUT_DIR / "caption.txt").write_text(caption, encoding="utf-8")
    (OUT_DIR / "package.json").write_text(
        json.dumps(
            {
                "title": "ISTJが本命だけに見せる距離の縮め方",
                "style": "editorial fashion photo with Japanese text overlay",
                "dimensions": {"width": WIDTH, "height": HEIGHT},
                "source_assets": [str(ASSET_DIR / slide.image_name) for slide in SLIDES],
                "thumbnail": str(thumbnail_path),
                "slides": [str(path) for path in rendered],
                "copy": [asdict(slide) for slide in SLIDES],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Created {len(rendered)} slides in {SLIDES_DIR}")


if __name__ == "__main__":
    main()
