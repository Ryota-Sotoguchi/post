"""Render a fixed set of packages and hash the slides.

Used as a byte-identity gate: any step that claims "no visual change" must
leave every hash untouched.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.pipeline import _build_render_package, _load_package
from mbti_tiktok_bot.visuals import generate_scene_assets

# Chosen to span all four palette groups and every motif branch, including
# pulse (which bypasses the scene styles) and an opaque-JPEG character.
FIXTURES = [
    "の攻略で効く接し方/post_01_INTJ",        # grid,   分析家, PNG
    "のLINEが急に変わる瞬間/post_08_ENFP",     # chat,   外交官, PNG
    "がしんどい時に出るサイン/post_06_INFP",    # pulse,  外交官, JPEG
    "が本気で心を許したサイン/post_09_ISTJ",    # orbit,  番人,   PNG
    "の回復が早い休み方/post_15_ESTP",         # ribbon, 探検家, JPEG
]


def main() -> int:
    config = load_config(Path.cwd())
    out = Path(tempfile.mkdtemp(prefix="fixture-render-"))
    digests: dict[str, str] = {}
    for fixture in FIXTURES:
        package_path = config.output_dir / fixture / "package.json"
        if not package_path.exists():
            print(f"MISSING {fixture}", file=sys.stderr)
            return 2
        package = _load_package(package_path)
        if package is None:
            print(f"UNREADABLE {fixture}", file=sys.stderr)
            return 2
        slides = out / fixture / "slides"
        generate_scene_assets(_build_render_package(package), config, slides)
        for slide in sorted(slides.glob("slide_*.png")):
            digests[f"{fixture}/{slide.name}"] = hashlib.sha256(slide.read_bytes()).hexdigest()
    shutil.rmtree(out, ignore_errors=True)
    print(json.dumps(digests, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
