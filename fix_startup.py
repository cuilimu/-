"""
fix_startup.py — One-shot startup repair.

Run from the stock_engine directory (BEFORE launching the app):
    python fix_startup.py

What it does:
  1. Clears all __pycache__ (removes stale .pyc files)
  2. Verifies portfolio/models.py has ResearchSession
  3. Verifies simple_aa.py is valid UTF-8
  4. Runs a full import chain dry-run to catch any remaining issues
"""
import sys, pathlib, shutil, importlib

ROOT = pathlib.Path(__file__).parent
PARENT = ROOT.parent

print("=" * 60)
print("Stock Engine — Startup Fix")
print("=" * 60)

# ── 1. Clear __pycache__ ───────────────────────────────────────
print("\n[1] Clearing __pycache__ directories...")
removed = 0
failed = 0
for p in ROOT.rglob("__pycache__"):
    try:
        shutil.rmtree(p)
        print(f"    Removed: {p.relative_to(ROOT)}")
        removed += 1
    except Exception as e:
        print(f"    SKIP ({e}): {p.relative_to(ROOT)}")
        failed += 1
print(f"    Done: {removed} removed, {failed} skipped (close Streamlit first if any skipped)")

# ── 2. Check models.py ─────────────────────────────────────────
print("\n[2] Checking portfolio/models.py...")
models_path = ROOT / "portfolio" / "models.py"
if models_path.exists():
    try:
        text = models_path.read_text(encoding="utf-8")
        has_rs = "class ResearchSession" in text
        print(f"    ResearchSession present: {has_rs}")
        if not has_rs:
            print("    *** MISSING — running fix_models.py fix ***")
            exec(open(ROOT / "fix_models.py").read())
    except UnicodeDecodeError as e:
        print(f"    *** ENCODING ERROR: {e}")
        print("    Run fix_models.py manually to rewrite the file.")
else:
    print("    *** NOT FOUND")

# ── 3. Check simple_aa.py ──────────────────────────────────────
print("\n[3] Checking ui/components/simple_mode/simple_aa.py...")
saa_path = ROOT / "ui" / "components" / "simple_mode" / "simple_aa.py"
if saa_path.exists():
    try:
        text = saa_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        has_render = "def render_simple_aa" in text
        print(f"    Lines: {len(lines)}, render_simple_aa present: {has_render}")
        if not has_render:
            print("    *** render_simple_aa MISSING — file may be corrupted")
    except UnicodeDecodeError as e:
        print(f"    *** ENCODING ERROR (file truncated): {e}")
        print("    The file was not fixed correctly. Please re-run the fix.")
else:
    print("    *** NOT FOUND")

# ── 4. Import chain dry-run ────────────────────────────────────
print("\n[4] Import chain test...")
sys.path.insert(0, str(PARENT))

tests = [
    ("stock_engine.portfolio.models", ["ResearchSession", "PortfolioGroup", "Universe"]),
    ("stock_engine.config", ["Config"]),
    ("stock_engine.exceptions", ["PortfolioError"]),
]

all_ok = True
for mod_name, names in tests:
    try:
        mod = importlib.import_module(mod_name)
        missing = [n for n in names if not hasattr(mod, n)]
        if missing:
            print(f"    FAIL  {mod_name}: missing {missing}")
            all_ok = False
        else:
            print(f"    OK    {mod_name}: {names}")
    except Exception as e:
        print(f"    ERROR {mod_name}: {e}")
        all_ok = False

# ── Summary ────────────────────────────────────────────────────
print("\n" + "=" * 60)
if all_ok:
    print("All checks passed. You can now restart the app via launch.vbs")
else:
    print("Some checks FAILED. See errors above.")
print("=" * 60)
