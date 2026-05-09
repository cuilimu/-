"""
viz/theme.py — VizTheme reads from ui/theme to stay in sync.
Chart zone stays dark (exception to white-main rule).
"""

from dataclasses import dataclass
from stock_engine.ui.theme import (
    CHART_BG, CHART_GRID, CHART_TEXT, CHART_AXIS,
    CHART_PORTFOLIO, CHART_BENCHMARK, CHART_SERIES_PALETTE,
    COLOR_GAIN, COLOR_LOSS, COLOR_NEUTRAL,
    FONT_FAMILY, FONT_SIZE_BASE,
)


@dataclass(frozen=True)
class VizTheme:
    color_gain: str       = COLOR_GAIN
    color_loss: str       = COLOR_LOSS
    color_neutral: str    = CHART_BENCHMARK
    color_portfolio: str  = CHART_PORTFOLIO
    color_cash: str       = "#FFA726"

    bg_paper: str         = CHART_BG
    bg_plot: str          = CHART_BG
    grid_color: str       = CHART_GRID

    font_family: str      = FONT_FAMILY
    font_size_base: int   = FONT_SIZE_BASE
    font_color: str       = CHART_TEXT

    margin: dict          = None

    def __post_init__(self):
        object.__setattr__(self, "margin", dict(l=40, r=20, t=40, b=40))


DEFAULT_THEME = VizTheme()

# Light variant for panels that have a white/near-white background
# (e.g. the ARIMAX arx_window at #fdf8ff).  Using the dark CHART_BG
# inside a light panel creates a jarring contrast — this theme keeps
# the same data colours but switches the canvas to match.
ARX_LIGHT_THEME = VizTheme(
    bg_paper      = "rgba(0,0,0,0)",   # transparent → shows panel background
    bg_plot       = "#f5f0f8",         # very light lavender, matches arx_window tint
    grid_color    = "#e4dced",         # soft lavender grid lines
    font_color    = "#1a1a1a",         # dark text on light canvas
    color_portfolio = "#660874",       # brand purple for main series
    color_gain    = "#00883a",         # slightly darker green for contrast on light bg
    color_loss    = "#c42b2b",         # slightly darker red for contrast on light bg
    color_neutral = "#666666",
)


def chart_theme(height: int | None = None) -> dict:
    """Shared Plotly layout kwargs. Apply via fig.update_layout(**chart_theme())."""
    t = DEFAULT_THEME
    layout = dict(
        paper_bgcolor=t.bg_paper,
        plot_bgcolor=t.bg_plot,
        font=dict(family=t.font_family, size=t.font_size_base, color=t.font_color),
        margin=dict(l=40, r=16, t=28, b=36),
        hovermode="x unified",
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=t.font_color, size=10),
            orientation="h",
            y=1.02,
            x=0,
        ),
        xaxis=dict(
            gridcolor=t.grid_color,
            zeroline=False,
            showgrid=True,
            tickfont=dict(color=CHART_AXIS, size=10),
        ),
        yaxis=dict(
            gridcolor=t.grid_color,
            zeroline=False,
            showgrid=True,
            tickfont=dict(color=CHART_AXIS, size=10),
        ),
    )
    if height is not None:
        layout["height"] = height
    return layout

