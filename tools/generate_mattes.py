#!/usr/bin/env python3
"""Generate grayscale transition masks for OBS Stinger (Track Matte → Mask).

Pure Python (no Pillow / numpy). Writes raw grayscale frames piped to ffmpeg.

A mask is grayscale video:
  * black  (0)   → show scene A
  * white  (255) → show scene B
  * gray   (mid) → blend A / B

OBS mixes the *live rendered pixels* of both scenes per this map — no alpha
codecs, no Playwright, no heavy dependencies. Output is small H.264 MP4.

Usage:
    python tools/generate_mattes.py --effect doom-melt \
        --out src/transitions/doom-melt.mp4 --duration-ms 800
    python tools/generate_mattes.py --all
"""

from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
from pathlib import Path

WIDTH = 1920
HEIGHT = 1080
FPS = 60


def header(w: int, h: int) -> bytes:
    """PGM P5 header for rawvideo pipe (not actually used — rawvideo needs no header)."""
    return f"P5\n{w} {h}\n255\n".encode("ascii")


def black(w: int, h: int) -> bytes:
    return bytes(w * h)


def white(w: int, h: int) -> bytes:
    return bytes([255] * (w * h))


def doom_melt_frame(t: float, duration_ms: int, width: int = WIDTH, height: int = HEIGHT, seed: int = 0xDEAD) -> bytes:
    """Doom (1993) level-load melt: columns drip down revealing scene B.

    160 columns of 12px each; each column finishes at its own time between
    45% and 98% of duration. One "quirk" column lags to ~98% — the classic
    Doom melt bug, reproduced on purpose.
    """
    progress = t / (duration_ms / 1000.0)
    progress = max(0.0, min(1.0, progress))

    cols = 160
    col_w = width // cols  # 12 px

    rng = random.Random(seed)
    finish_times = [0.45 + rng.random() * 0.53 for _ in range(cols)]
    quirk_col = rng.randint(0, cols - 1)
    finish_times[quirk_col] = 0.98  # the classic straggler column

    buf = bytearray(width * height)  # all black = scene A

    for c in range(cols):
        ft = finish_times[c]
        if progress >= ft:
            reveal_h = height
        else:
            reveal_h = int(height * progress / max(ft, 0.001))
            reveal_h = min(reveal_h, height)

        x_start = c * col_w
        x_end = min((c + 1) * col_w, width)
        for y in range(0, reveal_h):
            base = y * width + x_start
            for x in range(x_start, x_end):
                buf[base + (x - x_start)] = 255

    return bytes(buf)


def datamosh_frame(t: float, duration_ms: int, width: int = WIDTH, height: int = HEIGHT, seed: int = 0xC0DE) -> bytes:
    """Datamosh-style block corruption: 40x40px blocks flip A→B in random order.

    ~15% of blocks "glitch" — toggle back to A briefly near the end.
    Occasional horizontal tear lines mimic a broken codec.
    """
    progress = t / (duration_ms / 1000.0)
    progress = max(0.0, min(1.0, progress))

    bw, bh = 40, 40
    cols = width // bw   # 48
    rows = height // bh  # 27

    rng = random.Random(seed)
    switch_times = [[rng.random() for _ in range(cols)] for _ in range(rows)]

    glitch_blocks = set()
    for _ in range(int(cols * rows * 0.15)):
        glitch_blocks.add((rng.randint(0, rows - 1), rng.randint(0, cols - 1)))

    buf = bytearray(width * height)

    for r in range(rows):
        for c in range(cols):
            st = switch_times[r][c]
            revealed = progress >= st

            if (r, c) in glitch_blocks and revealed:
                if progress > 0.70 and (int(progress * FPS) % 4) < 2:
                    revealed = False

            if revealed:
                y0 = r * bh
                y1 = min((r + 1) * bh, height)
                x0 = c * bw
                x1 = min((c + 1) * bw, width)
                for y in range(y0, y1):
                    base = y * width + x0
                    for x in range(x0, x1):
                        buf[base + (x - x0)] = 255

    # Horizontal tear lines mid-transition
    if 0.30 < progress < 0.70:
        tear_row = int(height * (0.40 + 0.20 * math.sin(progress * 12.0)))
        if 0 <= tear_row < height:
            base = tear_row * width
            for x in range(width):
                buf[base + x] = 255 if ((tear_row + x) // 8) % 2 == 0 else 0

    return bytes(buf)


def scanline_frame(t: float, duration_ms: int, width: int = WIDTH, height: int = HEIGHT, seed: int = 0) -> bytes:
    """Clean horizontal scanline wipe top→bottom with a 4px leading edge."""
    progress = t / (duration_ms / 1000.0)
    progress = max(0.0, min(1.0, progress))

    fill_h = int(height * progress)
    edge_h = 4

    buf = bytearray(width * height)

    for y in range(0, fill_h):
        base = y * width
        for x in range(width):
            buf[base + x] = 255

    # Leading edge — slightly lighter than black, darker than white
    edge_start = max(0, fill_h - edge_h)
    for y in range(edge_start, fill_h):
        base = y * width
        for x in range(width):
            buf[base + x] = 192

    return bytes(buf)


EFFECTS = {
    "doom-melt": doom_melt_frame,
    "datamosh": datamosh_frame,
    "scanline": scanline_frame,
}


def generate_video(frame_func, out_path: Path, duration_ms: int, fps: int = FPS,
                   width: int = WIDTH, height: int = HEIGHT, seed: int = 0) -> None:
    num_frames = max(1, (duration_ms * fps) // 1000)
    frame_duration = 1.0 / fps

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-preset", "slow",
        "-an",
        str(out_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        for i in range(num_frames):
            t = i * frame_duration
            frame = frame_func(t, duration_ms, width, height, seed=seed)
            proc.stdin.write(frame)
    finally:
        proc.stdin.close()

    returncode = proc.wait()
    if returncode != 0:
        stderr = proc.stderr.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg exited {returncode}: {stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OBS transition masks")
    parser.add_argument("--effect", choices=list(EFFECTS) + ["all"], default="all",
                        help="Effect to generate (default: all)")
    parser.add_argument("--out", type=Path, help="Output MP4 path (required for single effect)")
    parser.add_argument("--duration-ms", type=int, default=600, help="Duration in milliseconds")
    parser.add_argument("--fps", type=int, default=FPS, help="Frame rate")
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (0 = deterministic per effect)")
    args = parser.parse_args()

    effects = list(EFFECTS) if args.effect == "all" else [args.effect]

    default_seeds = {"doom-melt": 0xDEAD, "datamosh": 0xC0DE, "scanline": 0}
    for name in effects:
        seed = args.seed if args.seed else default_seeds[name]
        if args.effect != "all" and not args.out:
            print("error: --out required for single effect", file=sys.stderr)
            return 2

        out_path = args.out or Path(f"src/transitions/{name}.mp4")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[generate] {name} → {out_path} ({args.duration_ms} ms @ {args.fps} fps)")
        generate_video(EFFECTS[name], out_path, args.duration_ms, args.fps, args.width, args.height, seed=seed)

    print("[OK] masks generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
