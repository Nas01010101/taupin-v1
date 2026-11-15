"""Build docs/assets/demo.gif from the PNG frames written by scripts/capture.mjs --frames.

    node scripts/capture.mjs "http://127.0.0.1:8780/?demo=1&pause=1" --frames ~/scratch/frames --fps 10
    python scripts/make_gif.py ~/scratch/frames --fps 10

Needs Pillow (`uv run --with pillow python scripts/make_gif.py ...`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "demo.gif"


def make_gif(frames_dir: Path, out: Path = OUT, fps: float = 10, width: int = 960, hold: float = 2.0) -> int:
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"no PNG frames in {frames_dir}")
    frames = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        # One adaptive palette per frame: the field photo and the amber risk cells both need colours.
        frames.append(im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    ms = round(1000 / fps)
    durations = [ms] * (len(frames) - 1) + [ms + round(hold * 1000)]   # hold the last frame before the loop
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    return len(frames)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("frames", type=Path, help="directory of f0000.png, f0001.png, ...")
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--fps", type=float, default=10)
    p.add_argument("--width", type=int, default=960, help="downscale wider frames to this width")
    p.add_argument("--hold", type=float, default=2.0, help="seconds to hold the last frame")
    a = p.parse_args()
    n = make_gif(a.frames, a.out, a.fps, a.width, a.hold)
    print(f"{n} frames -> {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
