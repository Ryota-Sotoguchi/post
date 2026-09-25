"""Colour pairs the eye can actually read, measured rather than guessed.

The rule the slides go by is WCAG's contrast ratio: 4.5:1 for body copy, 3:1
for large type, and 7:1 where it can be had. What it rules out is the mistake
the brutal look was making - a saturated mid-lightness field. At that lightness
black lands near 4:1 and white near 4:1, so neither ink works and the
characters, mapped between the two, come out as grey mush.

So a field is never left in the middle: it is pushed to one end (deep or pale)
and the ink is then whichever of the look's two inks reads better on it. The
hue is kept, which is what makes the pair still belong to the palette.
"""

from __future__ import annotations

import colorsys

from mbti_tiktok_bot.design.effects import hex_rgb, mix

# Where a field may sit, as relative luminance. Between these two an ink of
# either polarity is a compromise.
DEEP = 0.09
# A pale field is nearly paper: the characters keep their own colours, and a
# field with much hue left in it swallowed the ones that shared its hue - a
# gold ESFP on pale gold.
PALE = 0.82
# What the copy has to clear.
BODY = 4.5
LARGE = 3.0


def _linear(value: int) -> float:
    channel = value / 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    """Relative luminance, as WCAG defines it."""
    red, green, blue = (_linear(channel) for channel in hex_rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def ratio(one: str, other: str) -> float:
    first, second = luminance(one), luminance(other)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def readable(background: str, *inks: str) -> str:
    """Whichever ink reads best on this background."""
    return max(inks, key=lambda ink: ratio(background, ink))


def _to_luminance(color: str, target: float, towards: str) -> str:
    """Move a colour towards black or white until it is dark or light enough."""
    if (towards == "#000000") == (luminance(color) <= target):
        return color
    low, high = 0.0, 1.0
    for _ in range(12):
        middle = (low + high) / 2
        candidate = mix(color, towards, middle)
        if (luminance(candidate) <= target) == (towards == "#000000"):
            high = middle
        else:
            low = middle
    return mix(color, towards, high)


def deepen(color: str, target: float = DEEP) -> str:
    """The same hue as a deep ground: saturation kept up, lightness taken down."""
    red, green, blue = (channel / 255 for channel in hex_rgb(color))
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    saturated = colorsys.hsv_to_rgb(hue, min(1.0, saturation * 1.15), value)
    return _to_luminance("#%02x%02x%02x" % tuple(round(channel * 255) for channel in saturated),
                         target, "#000000")


def paled(color: str, target: float = PALE) -> str:
    """The same hue as a pale ground."""
    return _to_luminance(color, target, "#ffffff")


def against(color: str, background: str, minimum: float = BODY) -> str:
    """The same colour, moved just far enough to be readable on this background.

    It moves towards white on a dark ground and towards black on a light one,
    by the smallest step that clears the ratio, so the hue survives: a neon
    indigo on near-black brightens instead of turning into another colour.
    """
    if ratio(color, background) >= minimum:
        return color
    towards = "#ffffff" if luminance(background) < 0.5 else "#000000"
    low, high = 0.0, 1.0
    for _ in range(12):
        middle = (low + high) / 2
        if ratio(mix(color, towards, middle), background) >= minimum:
            high = middle
        else:
            low = middle
    return mix(color, towards, high)


def ground(color: str, dark: bool) -> str:
    """A field at one end of the range or the other, keeping the hue."""
    return deepen(color) if dark else paled(color)
