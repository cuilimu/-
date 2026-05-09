# stock_engine — engineering rules

## UI layering (functional code vs. visual style)

The codebase is split into three layers. Changes stay in the layer they belong to.

| Layer | Path | Owns |
|---|---|---|
| Tokens | `ui/theme.py` | The 10 `:root` CSS variables + the global `CUSTOM_CSS` |
| Style  | `ui/styles/*.css` | Per-page/per-component CSS, plain `.css` files |
| Code   | `ui/components/**/*.py`, `ui/app.py` | Streamlit logic, data flow, layout structure |

Per-page CSS is loaded with `inject(name)` from `stock_engine.ui.styles`:

```python
from stock_engine.ui.styles import inject as _inject_css

def render_xyz_tab() -> None:
    _inject_css("xyz")        # loads ui/styles/xyz.css
    ...
```

## Hard rules — DO NOT violate

These rules apply to every file under `ui/components/**/*.py` and `ui/app.py`:

1. **No `<style>` blocks.** No inline `st.markdown("<style>…</style>")`. CSS lives in `ui/styles/<name>.css` and is injected via `_inject_css("<name>")`.
2. **No 6-digit hex colour literals** (`#[0-9a-fA-F]{6}` or 3-digit shorthand `#[0-9a-fA-F]{3}` outside hex words like `#fff` in URLs/SVGs). If you genuinely need a colour in Python (e.g. passed to a Plotly trace, or an inline `style="color:..."` attribute), import it from `stock_engine.ui.theme`:
   ```python
   from stock_engine.ui.theme import SECTION_HEADER, COLOR_GAIN, COLOR_LOSS
   ```
3. **No new local colour tokens** like `_PURPLE = "#660874"`. They drift from `theme.py` and get baked into CSS strings — exactly the bug we just fixed.

The only files allowed to contain raw hex are `ui/theme.py` (the master `CUSTOM_CSS` + `:root` variables and Python token constants) and `ui/styles/*.css` (where literal hex is fine for page-local accents that aren't in the `:root` set).

## Pre-commit / pre-PR self-check

Before declaring any UI change done, run these two commands and confirm both return **no matches**:

```bash
# 1. No <style> blocks in .py UI code
rg -l '<style>' ui/components ui/app.py

# 2. No 6-char hex literals in .py UI code
rg -n '#[0-9a-fA-F]{6}' ui/components ui/app.py
```

If either returns results, fix them before reporting the task complete. The fix is always one of:
- Move the CSS to a `ui/styles/<name>.css` file and call `_inject_css("<name>")`.
- Replace the hex with an import from `stock_engine.ui.theme`.
- Add a new variable to `:root` in `ui/theme.py` if the colour is high-frequency (≥10 occurrences across the codebase).

## Why these rules exist

We did a refactor on 2026-05-07 that pulled ~84 KB of CSS and 2507 lines of dead/duplicated styling out of Python files. Before the refactor, changing the brand purple required editing ~62 hardcoded `#660874` strings across 17 component files; after, it's one line in `ui/theme.py:`. Re-introducing inline `<style>` or hex literals in `.py` undoes that work.

## Adding a new page or component

1. Create the Python file in `ui/components/...` with **only logic, no CSS strings**.
2. If it needs custom styling, create `ui/styles/<basename>.css` with the actual styles. Reference theme tokens via `var(--theme-purple)`, `var(--text)`, etc.
3. In the render function, call `_inject_css("<basename>")` once at the top.
4. Run the two `rg` checks above before committing.
