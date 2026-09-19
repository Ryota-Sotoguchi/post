"""Image treatments, all in device pixels.

Styles lay things out in logical 1080x1920 coordinates and convert with
ScaledDraw.px() before calling these. Everything here is Pillow only and
deterministic: grain comes from Image.effect_noise, which is seeded per call
from the arguments rather than from a global generator.
"""

from __future__ import annotations

import random

from PIL import Image, ImageChops, ImageFilter, ImageOps

RGBA = tuple[int, int, int, int]


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def rgba(value: str, alpha: int = 255) -> RGBA:
    return (*hex_rgb(value), alpha)


def mix(a: str, b: str, amount: float) -> str:
    """a moved towards b by amount (0..1), as hex."""
    ra, rb = hex_rgb(a), hex_rgb(b)
    mixed = tuple(round(x + (y - x) * amount) for x, y in zip(ra, rb))
    return "#%02x%02x%02x" % mixed


def solid(size: tuple[int, int], color: RGBA) -> Image.Image:
    return Image.new("RGBA", size, color)


def linear(size: tuple[int, int], start: RGBA, end: RGBA, angle: float = 90.0) -> Image.Image:
    """A two-colour gradient. angle 90 runs top to bottom, 0 left to right."""
    width, height = size
    span = int((width**2 + height**2) ** 0.5) + 2
    ramp = Image.linear_gradient("L").resize((span, span), Image.Resampling.BILINEAR)
    ramp = ramp.rotate(90 - angle, resample=Image.Resampling.BILINEAR, expand=False)
    left = (span - width) // 2
    top = (span - height) // 2
    mask = ramp.crop((left, top, left + width, top + height))
    return Image.composite(solid(size, end), solid(size, start), mask)


def radial(size: tuple[int, int], center: tuple[float, float], radius: float, color: RGBA, softness: float = 1.0) -> Image.Image:
    """A soft disc of colour fading to transparent at radius."""
    width, height = size
    disc = Image.radial_gradient("L")  # 256x256, 0 at centre, 255 at the edge
    diameter = max(int(radius * 2), 2)
    disc = disc.resize((diameter, diameter), Image.Resampling.BILINEAR)
    alpha = ImageOps.invert(disc)
    if softness != 1.0:
        alpha = alpha.point(lambda value: int(255 * (value / 255) ** softness))
    alpha = alpha.point(lambda value: value * color[3] // 255)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    tint = Image.new("RGBA", (diameter, diameter), (*color[:3], 255))
    tint.putalpha(alpha)
    layer.alpha_composite(tint, (int(center[0] - radius), int(center[1] - radius)))
    return layer


def aurora(size: tuple[int, int], base: RGBA, orbs: list[tuple[tuple[float, float], float, RGBA]], blur: float = 0) -> Image.Image:
    """A base colour with large overlapping glows - the mesh-gradient look."""
    image = solid(size, base)
    for center, radius, color in orbs:
        image.alpha_composite(radial(size, center, radius, color, softness=1.6))
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return image


def noise(size: tuple[int, int], seed: int) -> Image.Image:
    """Uniform greyscale noise from a seeded generator.

    Image.effect_noise draws from an unseeded source, so the same slide would
    come out with different grain on every render.
    """
    width, height = size
    data = random.Random(seed).randbytes(width * height)
    return Image.frombytes("L", size, data)


def grain(image: Image.Image, amount: float = 0.06, seed: int = 0) -> Image.Image:
    """Film grain in luminance only, so the hue is left alone."""
    speckle = noise(image.size, seed).filter(ImageFilter.GaussianBlur(0.6))
    grey = Image.merge("RGB", (speckle, speckle, speckle))
    rgb = image.convert("RGB")
    grained = ImageChops.add(rgb, grey, scale=1.0, offset=-128)
    blended = Image.blend(rgb, grained, amount * 4)
    result = blended.convert("RGBA")
    result.putalpha(image.getchannel("A"))
    return result


def trim(image: Image.Image) -> Image.Image:
    box = image.getchannel("A").getbbox()
    return image.crop(box) if box else image


def fit_height(image: Image.Image, height: int) -> Image.Image:
    ratio = height / image.height
    return image.resize((max(1, round(image.width * ratio)), height), Image.Resampling.LANCZOS)


def fit_width(image: Image.Image, width: int) -> Image.Image:
    ratio = width / image.width
    return image.resize((width, max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)


def silhouette(image: Image.Image, color: RGBA) -> Image.Image:
    shape = Image.new("RGBA", image.size, color[:3] + (255,))
    alpha = image.getchannel("A")
    if color[3] != 255:
        alpha = alpha.point(lambda value: value * color[3] // 255)
    shape.putalpha(alpha)
    return shape


def pad(image: Image.Image, margin: int) -> Image.Image:
    padded = Image.new("RGBA", (image.width + margin * 2, image.height + margin * 2), (0, 0, 0, 0))
    padded.alpha_composite(image, (margin, margin))
    return padded


def outline(image: Image.Image, thickness: int, color: RGBA) -> Image.Image:
    """A rounded sticker border around the shape, returned under the shape.

    Growing the alpha by blurring and thresholding gives round corners, where a
    max filter would give square ones. The image is padded first so the border
    has room.
    """
    padded = pad(image, thickness + 4)
    grown = padded.getchannel("A").filter(ImageFilter.GaussianBlur(thickness * 0.6))
    grown = grown.point(lambda value: 255 if value > 10 else 0).filter(ImageFilter.GaussianBlur(1.2))
    border = Image.new("RGBA", padded.size, color[:3] + (255,))
    border.putalpha(grown.point(lambda value: value * color[3] // 255))
    border.alpha_composite(padded)
    return border


def glow(image: Image.Image, radius: float, color: RGBA, strength: int = 1) -> Image.Image:
    """A blurred coloured halo behind the shape, returned with the shape on top."""
    margin = int(radius * 2.5)
    padded = pad(image, margin)
    halo = silhouette(padded, color).filter(ImageFilter.GaussianBlur(radius))
    result = Image.new("RGBA", padded.size, (0, 0, 0, 0))
    for _ in range(strength):
        result.alpha_composite(halo)
    result.alpha_composite(padded)
    return result


def rim(image: Image.Image, color: RGBA, offset: tuple[int, int], blur: float) -> Image.Image:
    """A coloured edge light: a shifted, softened silhouette peeking out behind."""
    margin = max(abs(offset[0]), abs(offset[1])) + int(blur * 3)
    padded = pad(image, margin)
    light = silhouette(padded, color).filter(ImageFilter.GaussianBlur(blur))
    result = Image.new("RGBA", padded.size, (0, 0, 0, 0))
    result.alpha_composite(ImageChops.offset(light, offset[0], offset[1]))
    result.alpha_composite(padded)
    return result


def shadow(image: Image.Image, offset: tuple[int, int], blur: float, color: RGBA) -> Image.Image:
    margin = max(abs(offset[0]), abs(offset[1])) + int(blur * 3)
    padded = pad(image, margin)
    dark = silhouette(padded, color).filter(ImageFilter.GaussianBlur(blur))
    result = Image.new("RGBA", padded.size, (0, 0, 0, 0))
    result.alpha_composite(ImageChops.offset(dark, offset[0], offset[1]))
    result.alpha_composite(padded)
    return result


def duotone(image: Image.Image, dark: str, light: str, mid: str | None = None) -> Image.Image:
    """Map luminance onto two (or three) colours, keeping the alpha."""
    grey = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    kwargs = {"mid": hex_rgb(mid)} if mid else {}
    toned = ImageOps.colorize(grey, black=hex_rgb(dark), white=hex_rgb(light), **kwargs).convert("RGBA")
    toned.putalpha(image.getchannel("A"))
    return toned


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    from PIL import ImageDraw

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def frosted(background: Image.Image, box: tuple[int, int, int, int], radius: int, blur: float, tint: RGBA) -> Image.Image:
    """A glass panel: the background under box, blurred and tinted, clipped to a rounded rect."""
    region = background.crop(box).filter(ImageFilter.GaussianBlur(blur))
    region.alpha_composite(solid(region.size, tint))
    mask = rounded_mask(region.size, radius)
    panel = Image.new("RGBA", background.size, (0, 0, 0, 0))
    region.putalpha(mask)
    panel.alpha_composite(region, (box[0], box[1]))
    return panel


def cover(image: Image.Image, size: tuple[int, int], centering: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=centering)


def tint_luminance(image: Image.Image, dark: str, light: str) -> Image.Image:
    """Recolour a greyscale texture into a palette, for the AI background library."""
    return duotone(image.convert("RGBA"), dark, light)
