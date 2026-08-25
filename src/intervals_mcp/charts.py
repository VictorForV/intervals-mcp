"""Render training-load history as a PNG line chart.

A coaching conversation benefits from seeing the CTL/ATL/TSB curve, not just
reading the numbers off a table -- a shape ("ATL spiked, CTL kept climbing")
often makes the point a table of numbers takes several sentences to make.
Pillow draws directly onto a pixel canvas here; there is no numpy or
matplotlib dependency to keep the image lean.
"""

import io
from collections.abc import Sequence

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

WIDTH, HEIGHT = 900, 420
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 60, 20, 30, 40

BACKGROUND = (255, 255, 255)
AXIS = (120, 120, 120)
GRID = (230, 230, 230)
TEXT = (60, 60, 60)
SERIES_COLORS = {
    "ctl": (66, 133, 244),  # fitness
    "atl": (219, 68, 55),  # fatigue
    "tsb": (15, 157, 88),  # form
}
Y_GRIDLINES = 5


def _scale(value: float, lo: float, hi: float, top: float, bottom: float) -> float:
    if hi == lo:
        return bottom
    fraction = (value - lo) / (hi - lo)
    return bottom - fraction * (bottom - top)


def render_pmc_chart(days: Sequence[dict], title: str = "Training load (CTL / ATL / TSB)") -> bytes:
    """Render CTL, ATL and derived TSB over time as a PNG.

    ``days`` must carry ``id`` (a date string), ``ctl`` and ``atl``; days
    missing either number are skipped. Raises ``ValueError`` if nothing is
    left to plot.
    """
    points = [d for d in days if d.get("ctl") is not None and d.get("atl") is not None]
    if not points:
        raise ValueError("No days with both ctl and atl to chart.")

    series = {
        "ctl": [d["ctl"] for d in points],
        "atl": [d["atl"] for d in points],
        "tsb": [d["ctl"] - d["atl"] for d in points],
    }
    all_values = [v for values in series.values() for v in values]
    lo, hi = min(all_values), max(all_values)
    pad = (hi - lo) * 0.1 or 1.0
    lo, hi = lo - pad, hi + pad

    image = PILImage.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    plot_left, plot_right = MARGIN_LEFT, WIDTH - MARGIN_RIGHT
    plot_top, plot_bottom = MARGIN_TOP, HEIGHT - MARGIN_BOTTOM

    draw.text((MARGIN_LEFT, 8), title, fill=TEXT, font=font)

    for i in range(Y_GRIDLINES):
        fraction = i / (Y_GRIDLINES - 1)
        y = plot_bottom - fraction * (plot_bottom - plot_top)
        value = lo + fraction * (hi - lo)
        draw.line([(plot_left, y), (plot_right, y)], fill=GRID)
        draw.text((4, y - 6), f"{value:.0f}", fill=TEXT, font=font)

    draw.line([(plot_left, plot_top), (plot_left, plot_bottom)], fill=AXIS)
    draw.line([(plot_left, plot_bottom), (plot_right, plot_bottom)], fill=AXIS)

    point_count = len(points)

    def x_at(index: int) -> float:
        if point_count == 1:
            return (plot_left + plot_right) / 2
        return plot_left + index * (plot_right - plot_left) / (point_count - 1)

    for name, values in series.items():
        color = SERIES_COLORS[name]
        coords = [(x_at(i), _scale(v, lo, hi, plot_top, plot_bottom)) for i, v in enumerate(values)]
        if len(coords) > 1:
            draw.line(coords, fill=color, width=2)
        else:
            x, y = coords[0]
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=color)

    for index in sorted({0, point_count // 2, point_count - 1}):
        date = str(points[index].get("id", ""))
        draw.text((x_at(index) - 20, plot_bottom + 6), date, fill=TEXT, font=font)

    legend_x = plot_right - 150
    for row, (name, color) in enumerate(SERIES_COLORS.items()):
        y = MARGIN_TOP + row * 14
        draw.line([(legend_x, y + 5), (legend_x + 16, y + 5)], fill=color, width=3)
        draw.text((legend_x + 22, y), name.upper(), fill=TEXT, font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
