"""Run this once from the stock_engine directory to clear all stale .pyc caches."""
import shutil, pathlib, sys

root = pathlib.Path(__file__).parent
count = 0
for p in root.rglob("__pycache__"):
    try:
        shutil.rmtree(p)
        print(f"Removed: {p}")
        count += 1
    except Exception as e:
        print(f"Skip {p}: {e}")

print(f"\nDone — {count} __pycache__ folders removed.")
print("Restart Streamlit now.")
