"""Unit tests for tools/generate_mattes.py (pure logic, no ffmpeg in CI)."""

from __future__ import annotations

from tools.generate_mattes import (
    HEIGHT,
    WIDTH,
    datamosh_frame,
    doom_melt_frame,
    scanline_frame,
)

BLACK = 0
WHITE = 255


def _pixel(buf: bytes, x: int, y: int, width: int = WIDTH) -> int:
    return buf[y * width + x]


def test_doommelt_start_all_black() -> None:
    """t=0 → everything black (scene A visible)."""
    buf = doom_melt_frame(0.0, 800)
    assert _pixel(buf, 100, 100) == BLACK
    assert _pixel(buf, 1900, 900) == BLACK


def test_doommelt_end_all_white() -> None:
    """t=duration → everything white (scene B visible)."""
    buf = doom_melt_frame(0.8, 800)
    assert _pixel(buf, 100, 100) == WHITE
    assert _pixel(buf, 1900, 900) == WHITE


def test_doommelt_deterministic_seed() -> None:
    """Same seed → identical frames."""
    a = doom_melt_frame(0.4, 800, seed=42)
    b = doom_melt_frame(0.4, 800, seed=42)
    assert a == b


def test_doommelt_different_seed_different() -> None:
    """Different seeds → likely different frames (not strictly guaranteed, but very likely)."""
    a = doom_melt_frame(0.4, 800, seed=1)
    b = doom_melt_frame(0.4, 800, seed=2)
    # At least one pixel differs — high probability with 160 columns
    diffs = sum(1 for i in range(len(a)) if a[i] != b[i])
    assert diffs > 0


def test_datamosh_start_all_black() -> None:
    buf = datamosh_frame(0.0, 600)
    assert _pixel(buf, 500, 500) == BLACK


def test_datamosh_end_all_white() -> None:
    buf = datamosh_frame(0.6, 600)
    assert _pixel(buf, 500, 500) == WHITE


def test_datamosh_deterministic_seed() -> None:
    a = datamosh_frame(0.3, 600, seed=7)
    b = datamosh_frame(0.3, 600, seed=7)
    assert a == b


def test_scanline_linear_progress() -> None:
    """Scanline fill height grows linearly with progress."""
    buf_start = scanline_frame(0.0, 400)
    buf_mid = scanline_frame(0.2, 400)  # 50% progress
    buf_end = scanline_frame(0.4, 400)  # 100% progress

    # Top row should be black at start, white at mid and end
    assert _pixel(buf_start, 100, 0) == BLACK
    assert _pixel(buf_mid, 100, 0) == WHITE
    assert _pixel(buf_end, 100, 0) == WHITE
    # Bottom row should stay black until the very end (above the 4px edge)
    assert _pixel(buf_mid, 100, HEIGHT - 1) == BLACK
    assert _pixel(buf_end, 100, HEIGHT - 5) == WHITE  # above leading edge


def test_scanline_mid_approx_half() -> None:
    """At 50% progress roughly half the rows are white."""
    buf = scanline_frame(0.2, 400)
    white_rows = 0
    for y in range(HEIGHT):
        if _pixel(buf, 100, y) == WHITE:
            white_rows += 1
    assert 450 < white_rows < 600  # ~540 ± tolerance

