"""Draw the background texture library. Run once; the daily pipeline never calls an image API.

The files are textures, not pictures. The renderer maps their luminance onto
the post's palette, so what comes back matters for its structure - light, grain,
depth, shape - and not for its colours. That is also why the prompts ask for a
calm middle: a character stands there, and copy sits under it.

    scripts/generate-backgrounds.py --count 1            # one per look, to look at
    scripts/generate-backgrounds.py --count 12           # the library
    scripts/generate-backgrounds.py --look neon --count 6

Existing files are kept; each run adds the next numbers.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import time
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbti_tiktok_bot.config import load_config  # noqa: E402

MODEL = "gpt-image-2.5-flare"
SIZE = "1024x1536"
QUALITY = "medium"
TIMEOUT = 300
QUALITY_SUFFIX = (
    " Abstract background texture only: no text, no letters, no numbers, no logos, "
    "no people, no faces, no hands, no recognisable objects. "
    "Keep the middle of the frame calm and uncluttered; put the detail towards the edges. "
    "Vertical 2:3 composition, even lighting, no vignette, no border, no frame."
)

PROMPTS = {
    "neon": [
        "A dark iridescent gradient mesh, deep indigo and violet, with soft volumetric glows bleeding "
        "through like light behind frosted glass, fine film grain.",
        "Night-time bokeh haze over a near-black field, long soft streaks of light, subtle chromatic "
        "aberration, cinematic and moody.",
        "A dark liquid-metal surface catching coloured rim light, slow smooth waves, high gloss, "
        "deep shadows.",
        "Fine diagonal rays of light cutting through dark fog, deep blue-violet, volumetric and still.",
        "Dark rippled silk with an iridescent sheen, soft folds, deep shadow, product-photography lighting.",
        "A scatter of tiny soft light points on near-black with shallow depth of field, cold and quiet.",
    ],
    "bubble": [
        "A soft pastel sky of rounded clouds and translucent bubbles, matte 3D clay render, gentle "
        "top light, airy and cute.",
        "Pastel gradient with scattered soft gel spheres and tiny sparkles, glossy jelly material, "
        "very light and bright.",
        "A pale pink and mint cotton-candy haze with blurred round shapes, dreamy, soft focus.",
        "Matte clay hills and rounded arches in pastel pink and cream, gentle studio light, minimal 3D.",
        "A pale mint and lemon gradient with soft blurred polka dots, fine paper grain, calm and cheerful.",
        "Translucent jelly ribbons drifting across a pale lilac field, glossy, soft shadows.",
    ],
    "editorial": [
        "Off-white laid paper, subtle fibre texture and a faint deckled edge, raking daylight from one "
        "side, fine print grain, minimal.",
        "Risograph-style paper texture in warm neutral tones, faint ink mottling and misregistration "
        "grain, flat and quiet.",
        "A plain plaster wall in soft natural light, very subtle shadow gradient, matte and fine grained.",
        "Cold-press watercolour paper, coarse tooth, soft daylight, faint warm cast.",
        "A worn linen book cover, fine weave, even light, muted ivory.",
        "Marbled endpaper in muted stone tones, very low contrast, fine detail.",
    ],
    "brutal": [
        "Bold flat geometric shapes - thick bars, circles and diagonals - arranged like a swiss poster, "
        "heavy halftone dot texture, high contrast, screen-printed.",
        "A coarse halftone gradient over a flat field, visible dot rosette and paper roughness, "
        "photocopied look, very high contrast.",
        "Heavy isometric blocks casting hard shadows on a flat ground, stark single light, "
        "poster-like and graphic.",
        "Thick black grid lines and a few solid rectangles on a bare off-white ground, offset misregistration, stark.",
        "A steep gradient of enormous halftone dots, dense to sparse, single ink on rough paper.",
        "Overlapping transparent geometric planes in one strong ink, silkscreen, hard edges.",
    ],
}


def generate(config, model: str, prompt: str) -> Image.Image:
    payload = {"model": model, "prompt": prompt + QUALITY_SUFFIX, "size": SIZE, "n": 1, "quality": QUALITY}
    url = f"{config.openai_base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"}
    for attempt in range(3):
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        # Not every image model takes a quality tier; drop it rather than fail.
        if response.status_code == 400 and "quality" in payload:
            payload.pop("quality")
            continue
        if response.status_code >= 500 and attempt < 2:
            time.sleep(5)
            continue
        response.raise_for_status()
        data = response.json()["data"][0]
        return Image.open(io.BytesIO(base64.b64decode(data["b64_json"]))).convert("RGB")
    raise RuntimeError("image generation failed")


def next_index(folder: Path) -> int:
    existing = [int(path.stem) for path in folder.glob("*.jpg") if path.stem.isdigit()]
    return max(existing, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--look", action="append", choices=sorted(PROMPTS), help="Only this look (repeatable)")
    parser.add_argument("--count", type=int, default=1, help="Images per look")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--out", default="assets/backgrounds")
    parser.add_argument("--dry-run", action="store_true", help="Print the prompts and stop")
    args = parser.parse_args()

    config = load_config(Path.cwd())
    if not config.openai_api_key and not args.dry_run:
        print("OPENAI_API_KEY is not set")
        return 1

    looks = args.look or sorted(PROMPTS)
    root = Path(args.out)
    for look in looks:
        folder = root / look
        folder.mkdir(parents=True, exist_ok=True)
        index = next_index(folder)
        for offset in range(args.count):
            prompt = PROMPTS[look][(index - 1 + offset) % len(PROMPTS[look])]
            destination = folder / f"{index + offset:02d}.jpg"
            if args.dry_run:
                print(f"{destination}: {prompt}")
                continue
            started = time.perf_counter()
            image = generate(config, args.model, prompt)
            # JPEG, not PNG: a background needs no alpha, and the repo already
            # carries hundreds of megabytes of published media.
            image.save(destination, format="JPEG", quality=88, optimize=True, progressive=True)
            print(f"{destination}  {image.width}x{image.height}  "
                  f"{destination.stat().st_size / 1e3:.0f}KB  {time.perf_counter() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
