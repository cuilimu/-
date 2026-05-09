"""
ui/theme.py — Single source of truth for all colors, fonts, spacing.
Two-zone system: Sidebar (Tsinghua Purple) + Main (white).
NO hardcoded colors anywhere else in the codebase.
"""

# ── Sidebar / Control zone ─────────────────────────────────────────────────────
SIDEBAR_BG           = "#660874"
SIDEBAR_BG_DARK      = "#4a0554"
SIDEBAR_INPUT_BG     = "#3a0442"
SIDEBAR_BORDER       = "#c084d4"
SIDEBAR_BTN_BG       = "#8a0a9e"
SIDEBAR_BTN_HOVER    = "#660874"
SIDEBAR_ACTIVE       = "#c084d4"
SIDEBAR_TEXT         = "#FFFFFF"

# ── ARIMAX terminal-style tab tokens ──────────────────────────────────────────
ARX_CONFIG_BG        = "#f7f5f9"   # left config-pane background (purple-tinted)
ARX_DARK_CHROME      = "#1a0220"   # key-bar / command-pane terminal chrome
ARX_TERMINAL_BORDER  = "#4a0556"   # output-pane + key-bar border
ARX_ACCENT_TEXT      = "#c9a4d4"   # dim-purple terminal key labels

# ── ARIMAX STATA report card (kind="stata_summary") ───────────────────────────
ARX_STATA_BG             = "#fafaf7"   # off-white parchment for report card body
ARX_STATA_RULE           = "#c8b8d0"   # 1px section divider rule (faint purple-grey)
ARX_STATA_SIG_STRONG     = "#1a1a1a"   # P<0.01 — full weight, primary text
ARX_STATA_SIG_MED        = "#3a3a3a"   # P<0.05 — near-black, slightly lighter
ARX_STATA_SIG_WEAK       = "#666666"   # P<0.10 — secondary grey
ARX_STATA_INSIG          = "#999999"   # P>=0.10 — clearly dimmed
ARX_STATA_SIG_MARKER     = "#660874"   # left-rule accent on sig-strong rows
ARX_STATA_SIG_MED_MARKER = "#9b30b0"   # left-rule accent on sig-med rows

# ── Main / Display zone ────────────────────────────────────────────────────────
MAIN_BG              = "#FFFFFF"
MAIN_TEXT            = "#1a1a1a"
MAIN_TEXT_SECONDARY  = "#666666"
CARD_BG              = "#f8f8f8"
CARD_BG_PURPLE       = "#f8f4fa"
CARD_BORDER          = "#e0e0e0"
SECTION_HEADER       = "#660874"

# ── P&L color convention (US market standard) ──────────────────────────────────
COLOR_GAIN           = "#00b050"
COLOR_LOSS           = "#e03030"
COLOR_NEUTRAL        = "#666666"

# ── Chart zone (stays dark) ───────────────────────────────────────────────────
CHART_BG             = "#111111"
CHART_GRID           = "#222222"
CHART_DIVIDER        = "#383838"   # Solid quadrant divider lines (brighter than grid)
CHART_TEXT           = "#FAFAFA"
CHART_AXIS_LABEL     = "#888888"   # Axis title text (dimmer than tick labels)
CHART_PORTFOLIO      = "#42A5F5"
CHART_BENCHMARK      = "#90A4AE"
CHART_SERIES_PALETTE = [
    "#42A5F5", "#26A69A", "#FFA726", "#AB47BC",
    "#EF5350", "#66BB6A", "#FF7043", "#26C6DA",
]

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_FAMILY          = "Inter, sans-serif"
FONT_SIZE_BASE       = 11

# ── Spacing ────────────────────────────────────────────────────────────────────
SPACING_SM           = 2
SPACING_MD           = 4
SPACING_LG           = 6

# ── Spacing scale (8px grid — preferred over SPACING_SM/MD/LG) ────────────────
SPACE_1              = 4    # dense table rows only
SPACE_2              = 8    # base unit
SPACE_3              = 16   # related groups
SPACE_4              = 24   # sections
SPACE_5              = 32   # page-level breathing room

# ── Bloomberg navigation & axis tokens ───────────────────────────────────────
BBG_HEADER_BG        = "#1a0220"   # Navigation context bar bg (dark terminal chrome)
CHART_AXIS           = "#aaaaaa"   # Axis tick labels on dark chart bg

# ── Sidebar nav step tokens ───────────────────────────────────────────────────
NAV_STEP_ACTIVE_BG   = "#ffffff"   # Active step pill bg (white on purple sidebar)
NAV_STEP_ACTIVE_FG   = "#660874"   # Active step text

# ── Factor bucket palette — light variants visible on dark chart bg ───────────
FACTOR_GROWTH        = "#4ade80"   # Growth — light green
FACTOR_FIN_COND      = "#378add"   # Financial conditions — blue
FACTOR_INFLATION     = "#fb923c"   # Inflation — orange
FACTOR_DIVERSIFIER   = "#c084fc"   # Diversifier — light purple
FACTOR_UNASSIGNED    = "#94a3b8"   # Unassigned — slate

# ── Terminal ticker list ──────────────────────────────────────────────────────
TERMINAL_BG          = "#0d0b18"   # Dark terminal panel background
TERMINAL_ROW_SEP     = "#1e1528"   # Row separator in terminal panel
TERMINAL_TEXT        = "#e0d8f0"   # Ticker symbol text (light lavender on dark)
TERMINAL_HOVER       = "#170f28"   # Row + delete button hover background
TERMINAL_DIM         = "#4a3868"   # Row number, dimmed UI text
TERMINAL_BORDER      = "#2a1f38"   # Outer border of terminal panel
TERMINAL_INPUT_BG    = "#140e22"   # Selectbox background inside ticker list
TERMINAL_INPUT_BORDER= "#2d2045"   # Selectbox border inside ticker list
TERMINAL_NAME_DIM    = "#7070a0"   # Name column — readable purple-grey on dark bg

# ── Divergent colorscale: navy (−1) → near-white (0) → Tsinghua purple (+1) ──
CORR_COLORSCALE = [
    [0.00, "#1e3a8a"],
    [0.25, "#7c8bbd"],
    [0.50, "#ede9f2"],
    [0.75, "#a073b3"],
    [1.00, "#660874"],
]

# ── Factor Investing tab — semantic tokens ────────────────────────────────────
FI_AMBER                   = "#b45309"   # significance chip ** text (amber)
FI_AMBER_BG                = "#fef3c7"  # significance chip ** background

# ── Home page — semantic tokens ───────────────────────────────────────────────
HOME_PAGE_LABEL_COLOR      = "#888888"
HOME_FOCAL_CARD_BG         = CARD_BG_PURPLE
HOME_FOCAL_CARD_BORDER     = SECTION_HEADER       # purple
HOME_SEGMENT_BG            = "#f5f0f8"
HOME_SEGMENT_ACTIVE_BG     = SECTION_HEADER       # purple
HOME_SEGMENT_ACTIVE_TEXT   = "#FFFFFF"
HOME_SEGMENT_INACTIVE_TEXT = "#666666"
HOME_DIVIDER_HAIRLINE      = "#eee5f0"

# ── Streamlit injected CSS — Bloomberg Terminal compact design ─────────────────
CUSTOM_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════════════
   BLOOMBERG-COMPACT DESIGN — Purple / White / Black-charts
   Font scale : labels 9-10px · values 11-12px · headers 11px
   Spacing    : 2 / 4 / 6 px (vs Streamlit default 8 / 16 / 24)
   ═══════════════════════════════════════════════════════════════════ */

/* ── CSS variable layer ───────────────────────────────────────────────
   Single source of truth for the 10 highest-frequency colours. Per-page
   CSS in ui/styles/*.css references these via var(--...). Change the
   value here → propagates everywhere. Hand-tuned background tints
   (#f5eefb, #fafafc, #c9a4d4, #1a0220, etc.) stay as literal hex in
   their owning .css file because they're page-local accents, not
   theme-level decisions. */
:root {
    --theme-purple:       #660874;
    --theme-purple-dark:  #4a0556;
    --theme-purple-light: #c084d4;
    --text:               #1a1a1a;
    --text-secondary:     #666666;
    --text-mute:          #888888;
    --bg:                 #ffffff;
    --border:             #e0e0e0;
    --gain:               #00b050;
    --loss:               #e03030;
    --bbg-header-bg:      #1a0220;
    --chart-axis:         #aaaaaa;
    --terminal-bg:        #0d0b18;
    --terminal-sep:       #1e1528;
    --terminal-text:      #e0d8f0;
    --terminal-hover:     #170f28;
    --terminal-dim:       #4a3868;
    --terminal-border:    #2a1f38;
    --terminal-input-bg:  #140e22;
    --terminal-input-border: #2d2045;
    --terminal-name-dim:  #7070a0;
    --chart-axis-label:   #888888;
    --chart-divider:      #383838;
    --sb-subitem-indent:  16px;
    --factor-growth:      #4ade80;
    --factor-fin-cond:    #378add;
    --factor-inflation:   #fb923c;
    --factor-diversifier: #c084fc;
    --factor-unassigned:  #94a3b8;
    --fi-amber:           #b45309;
    --fi-amber-bg:        #fef3c7;
}

/* ── 1. GLOBAL ────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    font-family: Inter, sans-serif;
    background-color: #FFFFFF;
    color: #1a1a1a;
    font-size: 11px;
}

/* ── 2. MAIN CONTAINER — kill Streamlit's giant default padding ───── */
.block-container {
    padding-top: 0.4rem !important;
    padding-bottom: 0.5rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
    max-width: 100% !important;
}
[data-testid="stVerticalBlock"] {
    gap: 0.25rem !important;
}
[data-testid="element-container"] {
    margin-bottom: 0 !important;
}

/* ── 3. SIDEBAR ───────────────────────────────────────────────────── */
/* Keep the sidebar pinned to the viewport via position:sticky so the main
   page scrolls independently of the purple bar. position:sticky preserves
   Streamlit's flex layout (sidebar + main side-by-side, no left gap),
   unlike position:fixed which forced us to add a margin offset and broke
   the layout. */
[data-testid="stAppViewContainer"] {
    overflow: visible !important;
}
section[data-testid="stSidebar"] {
    background-color: #660874 !important;
    min-width: 200px !important;
    max-width: 220px !important;
    position: sticky !important;
    top: 0 !important;
    height: 100vh !important;
    align-self: flex-start !important;
    overflow-y: auto !important;
}
section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    background-color: #660874 !important;
    height: 100% !important;
}
section[data-testid="stSidebar"] .block-container {
    padding: 0.4rem 0.6rem !important;
    min-height: 100vh !important;
}
section[data-testid="stSidebar"] * {
    color: #FFFFFF !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] label {
    font-size: 10px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.4px !important;
    color: #d4a0e0 !important;
    margin-bottom: 1px !important;
}
section[data-testid="stSidebar"] p {
    color: #FFFFFF !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #FFFFFF !important;
    margin: 6px 0 4px 0 !important;
}
section[data-testid="stSidebar"] input {
    background-color: #3a0442 !important;
    color: #FFFFFF !important;
    border: 1px solid #8a3a9a !important;
    font-size: 11px !important;
    padding: 2px 5px !important;
    height: 24px !important;
}
section[data-testid="stSidebar"] textarea {
    background-color: #3a0442 !important;
    color: #FFFFFF !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background-color: #3a0442 !important;
    color: #FFFFFF !important;
    border: 1px solid #8a3a9a !important;
    min-height: 26px !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] .stSelectbox svg {
    fill: #FFFFFF !important;
}
section[data-testid="stSidebar"] .stRadio label {
    color: #FFFFFF !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] .stButton button {
    background-color: #8a0a9e !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 600 !important;
    font-size: 11px !important;
    padding: 3px 10px !important;
    height: 26px !important;
    border-radius: 2px !important;
    line-height: 1 !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    background-color: #4a0554 !important;
}
section[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid #8a0a9e !important;
    margin: 4px 0 !important;
}
/* Number input */
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] > div {
    background-color: #3a0442 !important;
    border: 1px solid #8a3a9a !important;
    border-radius: 2px !important;
    height: 26px !important;
}
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] input {
    color: #FFFFFF !important;
    background-color: #3a0442 !important;
    height: 24px !important;
    font-size: 11px !important;
}
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] button {
    color: #FFFFFF !important;
    background-color: #4a0554 !important;
    border: none !important;
    height: 24px !important;
    width: 20px !important;
}
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] button:hover {
    background-color: #660874 !important;
}
/* Date input */
section[data-testid="stSidebar"] div[data-testid="stDateInput"] > div {
    background-color: #3a0442 !important;
    border: 1px solid #8a3a9a !important;
    height: 26px !important;
}
section[data-testid="stSidebar"] div[data-testid="stDateInput"] input {
    color: #FFFFFF !important;
    background-color: #3a0442 !important;
    height: 24px !important;
    font-size: 11px !important;
}
/* Segmented control */
section[data-testid="stSidebar"] div[data-testid="stSegmentedControl"] {
    background-color: #4a0554 !important;
    min-height: unset !important;
    height: 26px !important;
}
section[data-testid="stSidebar"] div[data-testid="stSegmentedControl"] button {
    color: #FFFFFF !important;
    font-size: 10px !important;
    padding: 2px 6px !important;
    height: 22px !important;
}
section[data-testid="stSidebar"] div[data-testid="stToggle"] * {
    color: #FFFFFF !important;
    font-size: 11px !important;
}

/* ── 3b. FAKE-SIDEBAR ROW LAYOUT (home, simulation, simple_aa) ─────────
   These pages hide the real Streamlit sidebar and build their layout from
   an st.columns() block. Treat the column row like the root flex layout
   the user specified:
     row    : height:100vh, overflow:hidden  (no page-level scroll)
     sidebar: sticky + 100vh + own scroll, flex-shrink:0
     main   : flex:1 + 100vh + own scroll
   Selectors rely on three sentinel marker spans the pages emit
   (.home-sidebar-marker / .sim-sb-marker / .aa-sb-marker). Each sentinel
   is unique to its page, and :has() resolves to the outer st.columns
   block where the sidebar is the first column — so this never bubbles
   into ordinary horizontal blocks elsewhere on the page. */

/* Outer row — fixed to viewport, no page scroll, NO wrap.
   `flex-wrap: nowrap` is critical: Streamlit's stHorizontalBlock defaults
   to flex-wrap:wrap so columns stack on narrow screens. With our fixed
   sidebar width + main content that may have wide intrinsic width (cards,
   ticker bar, charts), flex-wrap would push main onto a second row,
   producing a vertical stack instead of a sidebar/main split. */
div[data-testid="stHorizontalBlock"]:has(.home-sidebar-marker),
div[data-testid="stHorizontalBlock"]:has(.sim-sb-marker),
div[data-testid="stHorizontalBlock"]:has(.aa-sb-marker) {
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    height: 100vh !important;
    overflow: hidden !important;
}

/* Sidebar column (first child) — fixed 260px, sticky, own scroll.
   `flex: 0 0 260px` overrides Streamlit's weight-based flex so the
   sidebar can't grow or shrink — exact viewport pixel width. */
div[data-testid="stHorizontalBlock"]:has(.home-sidebar-marker) > div:first-child,
div[data-testid="stHorizontalBlock"]:has(.sim-sb-marker)        > div:first-child,
div[data-testid="stHorizontalBlock"]:has(.aa-sb-marker)         > div:first-child {
    flex: 0 0 260px !important;
    width: 260px !important;
    position: sticky !important;
    top: 0 !important;
    height: 100vh !important;
    overflow-y: auto !important;
}

/* Main column (second child) — fills remaining space, independent scroll.
   `flex: 1 1 0` (basis 0) prevents content-driven intrinsic width from
   pushing the main column to wrap. `min-width: 0` lets flex shrink it
   below its content's natural min-width so wide tables/charts don't
   push the row past the viewport. */
div[data-testid="stHorizontalBlock"]:has(.home-sidebar-marker) > div:nth-child(2),
div[data-testid="stHorizontalBlock"]:has(.sim-sb-marker)        > div:nth-child(2),
div[data-testid="stHorizontalBlock"]:has(.aa-sb-marker)         > div:nth-child(2) {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    height: 100vh !important;
    overflow-y: auto !important;
}

/* ── Home-shortcut button icon ─────────────────────────────────────────
   Two top-of-sidebar buttons (aa_sb_home, sim_sb_home_top) carry the
   "🏠" emoji as a text fallback. When CSS loads we hide that glyph and
   render an SVG home icon via mask-image instead. The icon's color
   comes from `background-color` on the ::before, which we set per
   context:
     * inside the purple sidebars (.aa-sb-marker / .sim-sb-marker
       ancestors) → white
     * everywhere else                                  → Tsinghua purple
   Add the same `.st-key-<key>` to any future home button to inherit
   this styling without further CSS work. */
.st-key-aa_sb_home button,
.st-key-sim_sb_home_top button {
    font-size: 0 !important;            /* hide the emoji text fallback */
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    min-height: 30px !important;
    height: 30px !important;
    width: 100% !important;
    cursor: pointer !important;
    transition: opacity 0.12s ease !important;
}
.st-key-aa_sb_home button::before,
.st-key-sim_sb_home_top button::before {
    content: "";
    display: block;
    width: 100%;
    height: 100%;
    /* Default tint: Tsinghua purple — used on white/light backgrounds. */
    background-color: #660874;
    -webkit-mask: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 9.5L12 3l9 6.5'/%3E%3Cpath d='M5 9v11h14V9'/%3E%3Cpath d='M10 20v-5h4v5'/%3E%3C/svg%3E") center / 20px 20px no-repeat;
            mask: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 9.5L12 3l9 6.5'/%3E%3Cpath d='M5 9v11h14V9'/%3E%3Cpath d='M10 20v-5h4v5'/%3E%3C/svg%3E") center / 20px 20px no-repeat;
    transition: background-color 0.12s ease;
}
/* Override: when the button sits inside one of the purple fake-sidebars,
   tint the icon white so it reads against the Tsinghua-purple panel. */
div[data-testid="stHorizontalBlock"]:has(.aa-sb-marker)  .st-key-aa_sb_home button::before,
div[data-testid="stHorizontalBlock"]:has(.sim-sb-marker) .st-key-sim_sb_home_top button::before {
    background-color: #ffffff;
}
.st-key-aa_sb_home button:hover,
.st-key-sim_sb_home_top button:hover {
    opacity: 0.75 !important;
}

/* ── 4. MAIN ZONE ─────────────────────────────────────────────────── */
[data-testid="stMain"] {
    background-color: #FFFFFF;
    color: #1a1a1a;
}

/* ── 5. METRIC WIDGETS — Bloomberg KPI card style ─────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #e0d0e8;
    border-top: 2px solid #660874;
    border-radius: 2px !important;
    padding: 4px 8px 5px !important;
}
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] p {
    font-size: 9px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    color: #888888 !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.4 !important;
}
[data-testid="stMetricValue"] > div,
[data-testid="stMetricValue"] p {
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #1a1a1a !important;
    line-height: 1.2 !important;
    margin: 0 !important;
    font-variant-numeric: tabular-nums !important;
}
[data-testid="stMetricDelta"] {
    font-size: 10px !important;
    margin-top: 1px !important;
}

/* ── 6. TAB BAR — compact Bloomberg-style ─────────────────────────── */
[data-testid="stTabs"] {
    gap: 0 !important;
}
[data-testid="stTabs"] > div:first-child {
    border-bottom: 1px solid #c8a0d8 !important;
    background: #f5eefb !important;
    padding: 0 2px !important;
    gap: 0 !important;
    min-height: 30px !important;
    align-items: flex-end !important;
}
button[role="tab"] {
    font-size: 10px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
    padding: 4px 12px !important;
    margin: 0 !important;
    height: 28px !important;
    min-height: 28px !important;
    border-radius: 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    color: #888888 !important;
    background: transparent !important;
    transition: color 0.1s, border-bottom-color 0.1s !important;
}
button[role="tab"][aria-selected="true"] {
    color: #660874 !important;
    border-bottom: 2px solid #660874 !important;
    background: #FFFFFF !important;
    font-weight: 600 !important;
}
button[role="tab"]:hover:not([aria-selected="true"]) {
    color: #8a0a9e !important;
    background: rgba(102,8,116,0.05) !important;
}
[data-testid="stTabs"] > div:last-child {
    padding-top: 6px !important;
}

/* ── 7. DATAFRAME — denser rows ────────────────────────────────────── */
[data-testid="stDataFrame"] {
    font-size: 11px !important;
}
[data-testid="stDataFrame"] iframe {
    border: 1px solid #e0d0e8 !important;
    border-radius: 2px !important;
}

/* ── 8. DIVIDERS ───────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid #e8ddf0 !important;
    margin: 4px 0 !important;
}

/* ── 9. ALERTS / INFO / WARNING banners ────────────────────────────── */
[data-testid="stAlert"] {
    padding: 5px 10px !important;
    font-size: 11px !important;
    border-radius: 2px !important;
}
[data-testid="stAlert"] p {
    font-size: 11px !important;
    margin: 0 !important;
}

/* ── 10. BUTTONS (main area) ────────────────────────────────────────── */
/* descendant (not >) because Streamlit 1.36+ wraps <button> in
   <div data-testid="stBaseButton"> — the direct-child selector breaks. */
[data-testid="stMain"] .stButton button {
    font-size: 11px !important;
    padding: 3px 14px !important;
    height: 28px !important;
    border-radius: 2px !important;
    line-height: 1 !important;
}
[data-testid="stMain"] .stButton button[kind="primary"],
[data-testid="stMain"] .stButton button[data-testid="baseButton-primary"] {
    background-color: #660874 !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 600 !important;
}
[data-testid="stMain"] .stButton button[kind="primary"]:hover,
[data-testid="stMain"] .stButton button[data-testid="baseButton-primary"]:hover {
    background-color: #8a0a9e !important;
}

/* ── 11. SELECT / MULTISELECT (main area) ───────────────────────────── */
[data-testid="stMain"] .stSelectbox > div > div,
[data-testid="stMain"] .stMultiSelect > div > div {
    min-height: 28px !important;
    font-size: 11px !important;
}
[data-testid="stMain"] .stSelectbox label,
[data-testid="stMain"] .stMultiSelect label,
[data-testid="stMain"] .stTextInput label,
[data-testid="stMain"] .stNumberInput label {
    font-size: 10px !important;
    color: #666666 !important;
    margin-bottom: 2px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.3px !important;
}

/* ── 12. EXPANDER ───────────────────────────────────────────────────── */
[data-testid="stExpander"] summary {
    font-size: 11px !important;
    font-weight: 600 !important;
    padding: 4px 8px !important;
    background: #f5eefb !important;
    border-radius: 2px !important;
    color: #660874 !important;
    min-height: 28px !important;
}
[data-testid="stExpander"] summary:hover {
    background: #ede0f5 !important;
}
[data-testid="stExpander"] > div:last-child {
    padding: 6px 8px !important;
}

/* ── 13. CAPTION / SMALL TEXT ───────────────────────────────────────── */
[data-testid="stCaptionContainer"] p,
.stCaption p {
    font-size: 10px !important;
    color: #888888 !important;
    margin: 0 !important;
}

/* ── 14. SPINNER / PROGRESS ────────────────────────────────────────── */
[data-testid="stSpinner"] p { font-size: 11px !important; }
[data-testid="stProgressBar"] > div {
    height: 3px !important;
    border-radius: 1px !important;
}
[data-testid="stProgressBar"] > div > div {
    background-color: #660874 !important;
}

/* ══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENT CLASSES
   ══════════════════════════════════════════════════════════════════════ */

/* ── Group cards ── */
.engine-card {
    background: #FFFFFF;
    border: 1px solid #e0d0e8;
    border-radius: 2px;
    box-shadow: none;
    margin-bottom: 4px;
    overflow: hidden;
}
.engine-card-header {
    background: #f5eefb;
    padding: 3px 8px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-radius: 2px 2px 0 0;
    border-bottom: 1px solid #e0d0e8;
}
.engine-card-header:hover { background: #ede0f5; }
.engine-card-title {
    color: #660874;
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
.engine-card-body { padding: 4px 8px; }

/* ── Metric label / value in cards ── */
.metric-label {
    color: #888888;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 1px;
}
.metric-value {
    color: #1a1a1a;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.metric-value-gain {
    color: #00b050;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.metric-value-loss {
    color: #e03030;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* ── Summary bar ── */
.summary-bar {
    background: #f5eefb;
    border: 1px solid #e0d0e8;
    border-left: 3px solid #660874;
    border-radius: 2px;
    padding: 3px 8px;
    margin-bottom: 4px;
    font-size: 11px;
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
}

/* ── Section headers ── */
.section-header {
    color: #660874;
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
    padding: 2px 0;
    border-bottom: 1px solid #e8ddf0;
}

/* ── P&L classes ── */
.gain { color: #00b050; font-weight: 600; }
.loss { color: #e03030; font-weight: 600; }
.flat { color: #666666; }

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 40px 20px;
    color: #888888;
}
.empty-state h3 {
    color: #660874;
    margin-bottom: 6px;
    font-size: 14px;
}

/* ── Ticker search rows ── */
.ticker-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 2px 6px;
    border-bottom: 1px solid #f0e8f5;
    cursor: pointer;
    font-size: 11px;
    background: #FFFFFF;
    transition: background 0.1s;
}
.ticker-row:hover { background: #f7f0fb; }
.ticker-symbol { font-weight: 600; color: #1a1a1a; font-size: 11px; }
.ticker-name   { color: #888888; font-size: 10px; }
.exchange-badge {
    background: #f0e0f8;
    color: #660874;
    font-size: 9px;
    padding: 1px 4px;
    border-radius: 2px;
    font-weight: 600;
}

/* ── Holdings table ── */
.holdings-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.holdings-table th {
    background: #f5eefb;
    color: #888888;
    font-weight: 600;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 3px 6px;
    text-align: left;
    border-bottom: 1px solid #e0d0e8;
}
.holdings-table td {
    padding: 2px 6px;
    border-bottom: 1px solid #f5f0f8;
    vertical-align: middle;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
}
.holdings-table tr:hover td { background: #faf6fc; }
.holdings-ticker { font-weight: 600; font-size: 11px; color: #1a1a1a; }
.holdings-sub    { font-size: 10px; color: #888888; }

/* ── Inline notes / warnings ── */
.inline-warn { color: #e03030; font-size: 11px; }
.inline-note { color: #888888; font-size: 10px; }

/* .bbg-header / .bbg-tag / .bbg-header-sep live in ui/styles/simple_aa.css
   (only used by the Simple Mode page — no global definition needed). */
</style>
"""



def fmt_ratio(value: "float | None") -> "tuple[str, str]":
    """Return (display_text, css_color) for a ratio metric (Calmar, Sharpe, etc.)."""
    import math
    if value is None:
        return "N/A", COLOR_NEUTRAL
    if math.isinf(value):
        return "\u221e", COLOR_NEUTRAL
    if math.isnan(value):
        return "N/A", COLOR_NEUTRAL
    color = COLOR_GAIN if value > 0 else (COLOR_LOSS if value < 0 else COLOR_NEUTRAL)
    return f"{value:.2f}", color
