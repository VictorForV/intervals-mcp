"""Render training-load history and best-effort curves as PNG line charts.

A coaching conversation benefits from seeing a shape, not just reading the
numbers off a table -- a shape ("ATL spiked, CTL kept climbing", "the power
curve fell off past 20 minutes") often makes the point a table of numbers
takes several sentences to make. Pillow draws directly onto a pixel canvas
here; there is no numpy or matplotlib dependency to keep the image lean.
"""

import io
import math
from collections.abc import Callable, Sequence

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from .compact import CURVE_DISTANCES, CURVE_DURATIONS, format_duration

WIDTH, HEIGHT = 900, 420
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 60, 20, 30, 40

BACKGROUND = (255, 255, 255)
AXIS = (120, 120, 120)
GRID = (230, 230, 230)
TEXT = (60, 60, 60)
PALETTE = [
    (66, 133, 244),
    (219, 68, 55),
    (15, 157, 88),
    (244, 160, 0),
]
Y_GRIDLINES = 5


def _scale(value: float, lo: float, hi: float, near: float, far: float) -> float:
    """Map ``value`` from the data range [lo, hi] to the pixel range [near, far]."""
    if hi == lo:
        return (near + far) / 2
    return near + (value - lo) / (hi - lo) * (far - near)


def _padded_range(values: Sequence[float]) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or (abs(hi) * 0.1 or 1.0)
    return lo - pad, hi + pad


def _nice_step(raw_step: float) -> float:
    """Round a raw axis step up to 1, 2 or 5 times a power of ten.

    That is what makes gridlines land on numbers a human reads cleanly (2:00,
    2:30, 3:00) instead of whatever a straight linear split happens to produce.
    """
    if raw_step <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    nice = 1 if residual <= 1 else 2 if residual <= 2 else 5 if residual <= 5 else 10
    return nice * magnitude


def _nice_ticks(lo: float, hi: float, target_count: int, floor: float | None = None) -> list[float]:
    """Gridline values on a round step, spanning at least [lo, hi].

    ``floor`` clamps the lowest tick (e.g. 0 for a quantity that cannot
    legitimately go negative, such as a duration or a heart rate) rather than
    letting axis padding push it below a value that would be nonsensical.
    """
    if hi <= lo:
        return [lo]
    step = _nice_step((hi - lo) / max(target_count - 1, 1))
    start = math.floor(lo / step) * step
    if floor is not None:
        start = max(start, floor)
    ticks = [start]
    while ticks[-1] < hi - step * 1e-9:
        ticks.append(ticks[-1] + step)
        if len(ticks) > target_count * 3:  # safety valve against a pathological step
            break
    return ticks


def _render_line_chart(
    series: dict[str, list[tuple[float, float]]],
    x_ticks: Sequence[tuple[float, str]],
    title: str,
    y_format: Callable[[float], str] = lambda v: f"{v:.0f}",
    y_floor: float | None = None,
) -> bytes:
    """Draw one or more (x, y) series onto a common canvas and return PNG bytes.

    ``x`` values are already in plot space -- callers decide whether that is
    a day index, a raw duration, or a log-scaled one. ``x_ticks`` places the
    bottom-axis labels independently of the series data, since a curve chart
    wants ticks at conventional durations (5s, 1m, 1h) rather than at every
    sampled point.
    """
    all_points = [point for points in series.values() for point in points]
    if not all_points:
        raise ValueError("Nothing to plot.")

    xs = [x for x, _ in all_points]
    ys = [y for _, y in all_points]
    x_lo, x_hi = min(xs), max(xs)
    if x_hi == x_lo:
        x_lo, x_hi = x_lo - 1, x_hi + 1
    padded_lo, padded_hi = _padded_range(ys)
    y_ticks = _nice_ticks(padded_lo, padded_hi, Y_GRIDLINES, floor=y_floor)
    y_lo, y_hi = y_ticks[0], y_ticks[-1]

    image = PILImage.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    plot_left, plot_right = MARGIN_LEFT, WIDTH - MARGIN_RIGHT
    plot_top, plot_bottom = MARGIN_TOP, HEIGHT - MARGIN_BOTTOM

    draw.text((MARGIN_LEFT, 8), title, fill=TEXT, font=font)

    for value in y_ticks:
        y = _scale(value, y_lo, y_hi, plot_bottom, plot_top)
        draw.line([(plot_left, y), (plot_right, y)], fill=GRID)
        draw.text((4, y - 6), y_format(value), fill=TEXT, font=font)

    draw.line([(plot_left, plot_top), (plot_left, plot_bottom)], fill=AXIS)
    draw.line([(plot_left, plot_bottom), (plot_right, plot_bottom)], fill=AXIS)

    def point_px(x: float, y: float) -> tuple[float, float]:
        return (
            _scale(x, x_lo, x_hi, plot_left, plot_right),
            _scale(y, y_lo, y_hi, plot_bottom, plot_top),
        )

    for (_name, points), color in zip(series.items(), PALETTE, strict=False):
        pixels = [point_px(x, y) for x, y in points]
        if len(pixels) > 1:
            draw.line(pixels, fill=color, width=2)
        else:
            px, py = pixels[0]
            draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)

    for x_value, label in x_ticks:
        if not (x_lo <= x_value <= x_hi):
            continue
        px, _ = point_px(x_value, y_lo)
        draw.text((px - len(label) * 3, plot_bottom + 6), label, fill=TEXT, font=font)

    legend_x = plot_right - 150
    for row, ((name, _points), color) in enumerate(zip(series.items(), PALETTE, strict=False)):
        y = MARGIN_TOP + row * 14
        draw.line([(legend_x, y + 5), (legend_x + 16, y + 5)], fill=color, width=3)
        draw.text((legend_x + 22, y), name.upper(), fill=TEXT, font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_pmc_chart(days: Sequence[dict], title: str = "Training load (CTL / ATL / TSB)") -> bytes:
    """Render CTL, ATL and derived TSB over time as a PNG.

    ``days`` must carry ``id`` (a date string), ``ctl`` and ``atl``; days
    missing either number are skipped. Raises ``ValueError`` if nothing is
    left to plot.
    """
    points = [d for d in days if d.get("ctl") is not None and d.get("atl") is not None]
    if not points:
        raise ValueError("No days with both ctl and atl to chart.")

    indexed = list(enumerate(points))
    series = {
        "ctl": [(i, d["ctl"]) for i, d in indexed],
        "atl": [(i, d["atl"]) for i, d in indexed],
        "tsb": [(i, d["ctl"] - d["atl"]) for i, d in indexed],
    }

    last = len(points) - 1
    tick_positions = sorted({0, last // 2, last})
    x_ticks = [(i, str(points[i].get("id", ""))) for i in tick_positions]

    return _render_line_chart(series, x_ticks, title)


def _to_pace_seconds_per_km(pairs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convert (distance_m, elapsed_s) points to (distance_m, seconds_per_km).

    The API's pace curve stores elapsed time for each distance, not a pace.
    Plotting elapsed time directly and labelling the axis "pace" is the
    wrong quantity under the right name -- this is the actual conversion.
    """
    return [(x, v * 1000 / x) for x, v in pairs]


def render_curve_chart(curve: dict, kind: str, title: str | None = None) -> bytes:
    """Render one best-effort curve (HR, power or pace) as a PNG.

    ``curve`` is one entry from a curve payload's ``list``: it carries either
    ``secs`` (duration curves -- HR, power) or ``distance`` (pace curves)
    alongside parallel ``values``. The x-axis is log-scaled, since a best-
    effort curve spans three or four orders of magnitude (1 second to 90
    minutes) and a linear axis would crush the short end into a sliver.
    """
    xs_raw = curve.get("secs") or curve.get("distance")
    if not xs_raw:
        raise ValueError("Curve has neither 'secs' nor 'distance' to plot.")
    by_duration = bool(curve.get("secs"))

    values = curve.get("values") or []
    pairs = sorted(
        (x, v) for x, v in zip(xs_raw, values, strict=False) if x and v is not None
    )
    if not pairs:
        raise ValueError("Curve has no plottable points.")

    series_values = _to_pace_seconds_per_km(pairs) if kind == "pace" else pairs
    series = {kind: [(math.log10(x), v) for x, v in series_values]}

    reference = CURVE_DURATIONS if by_duration else CURVE_DISTANCES
    x_min, x_max = pairs[0][0], pairs[-1][0]
    x_ticks = [
        (math.log10(value), label)
        for value, label in reference
        if x_min <= value <= x_max
    ]

    if title is None:
        if kind == "pace":
            title = f"{curve.get('label', 'pace')} pace curve (min/km) by distance"
        else:
            unit = "duration" if by_duration else "distance"
            title = f"{curve.get('label', kind)} {kind} curve by {unit}"

    # y is now genuinely min:sec/km for pace, not raw elapsed seconds -- a
    # coach reads m:ss either way, so the same formatter still applies.
    y_format = format_duration if kind == "pace" else (lambda v: f"{v:.0f}")

    # HR, power and pace are never negative; axis padding must not invent a
    # negative gridline (and, for pace, a nonsense "-1:45:46" label).
    return _render_line_chart(series, x_ticks, title, y_format=y_format, y_floor=0)
