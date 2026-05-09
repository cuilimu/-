"""
Comprehensive diagnostic — run from stock_engine directory:
    python diagnose.py
"""
import sys, pathlib, importlib, traceback

ROOT = pathlib.Path(__file__).parent
print("=" * 60)
print(f"Python:      {sys.version}")
print(f"Executable:  {sys.executable}")
print(f"Script dir:  {ROOT}")
print("=" * 60)

# ── 1. Check sys.path ─────────────────────────────────────────
print("\n[1] sys.path (first 6 entries):")
for p in sys.path[:6]:
    print(f"    {p}")

# ── 2. Locate stock_engine package ────────────────────────────
print("\n[2] Where does Python find stock_engine?")
try:
    import stock_engine
    print(f"    FOUND: {stock_engine.__file__}")
    print(f"    Path:  {stock_engine.__path__}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── 3. Check actual models.py on disk ─────────────────────────
print("\n[3] portfolio/models.py on disk:")
models_path = ROOT / "portfolio" / "models.py"
print(f"    Path exists: {models_path.exists()}")
if models_path.exists():
    text = models_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    print(f"    Line count: {len(lines)}")
    classes = [l.strip() for l in lines if l.strip().startswith("class ")]
    print(f"    Classes found: {classes}")
    has_rs = "class ResearchSession" in text
    print(f"    ResearchSession present: {has_rs}")
    if not has_rs:
        print("    *** MISSING — last 10 lines of file: ***")
        for l in lines[-10:]:
            print(f"        {l}")

# ── 4. Check which models.py Python actually imports ──────────
print("\n[4] Which models.py does Python actually load?")
try:
    import stock_engine.portfolio.models as m
    print(f"    File: {m.__file__}")
    print(f"    Has ResearchSession: {hasattr(m, 'ResearchSession')}")
    print(f"    Has FactorBucket:    {hasattr(m, 'FactorBucket')}")
    print(f"    All names: {[x for x in dir(m) if not x.startswith('_')]}")
except Exception as e:
    print(f"    ERROR importing: {e}")
    traceback.print_exc()

# ── 5. Check if there's an installed stock_engine in site-packages ──
print("\n[5] stock_engine in site-packages?")
import site
for sp in site.getsitepackages():
    candidate = pathlib.Path(sp) / "stock_engine"
    if candidate.exists():
        print(f"    *** FOUND installed copy: {candidate} ***")
        m2 = candidate / "portfolio" / "models.py"
        if m2.exists():
            t2 = m2.read_text(encoding="utf-8", errors="replace")
            print(f"    Installed models.py has ResearchSession: {'class ResearchSession' in t2}")
    else:
        print(f"    Not in: {sp}")

# ── 6. Check for egg-link / editable installs ─────────────────
print("\n[6] Editable installs (.pth / egg-link)?")
for sp in site.getsitepackages() + [site.getusersitepackages()]:
    spd = pathlib.Path(sp)
    for f in spd.glob("stock*"):
        print(f"    Found: {f}")
    for f in spd.glob("*.pth"):
        txt = f.read_text(errors="replace")
        if "stock" in txt.lower():
            print(f"    PTH points to stock_engine: {f} -> {txt.strip()}")

print("\n" + "=" * 60)
print("Diagnostic complete.")
