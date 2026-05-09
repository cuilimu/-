"""python diagnose2.py"""
import sys, pathlib, site

# ── Find the editable finder module ───────────────────────────────────────────
print("=" * 60)
sp = pathlib.Path(site.getsitepackages()[0])  # anaconda site-packages

finder_py = sp / "__editable___stock_engine_0_1_0_finder.py"
pth_file   = sp / "__editable__.stock_engine-0.1.0.pth"

print(f"[A] .pth file exists: {pth_file.exists()}")
if pth_file.exists():
    print(f"    Content: {pth_file.read_text().strip()}")

print(f"\n[B] Finder module exists: {finder_py.exists()}")
if finder_py.exists():
    print("    Content:")
    print(finder_py.read_text())

# ── Also check setup.py / pyproject.toml location ─────────────────────────────
root = pathlib.Path(__file__).parent
print(f"\n[C] Project files in {root}:")
for f in ["setup.py", "setup.cfg", "pyproject.toml"]:
    p = root / f
    print(f"    {f}: {'EXISTS' if p.exists() else 'not found'}")
    if p.exists():
        print(f"    --- content ---")
        print(p.read_text()[:400])

parent = root.parent
print(f"\n[D] Project files in parent ({parent}):")
for f in ["setup.py", "setup.cfg", "pyproject.toml"]:
    p = parent / f
    print(f"    {f}: {'EXISTS' if p.exists() else 'not found'}")
    if p.exists():
        print(p.read_text()[:400])

print("=" * 60)
