"""
create_shortcut.py — TAA Sandbox launcher installer.

Run once from the Python environment that has streamlit installed
(e.g. inside Anaconda Prompt with your env active):

    python stock_engine/sandbox/taa_module/create_shortcut.py

Generates / updates:
  1. `taa_sandbox.ico`   efficient-frontier glyph (purple + gold)
  2. `python_path.txt`   the Python interpreter that has streamlit —
                          launch.vbs reads this on every double-click,
                          so the shortcut works without Anaconda Prompt.
  3. Desktop shortcut "TAA Sandbox.lnk" → silently launches launch.vbs
                          on port 8502 and opens http://localhost:8502.
"""

import os
import sys
import math
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent.resolve()


# ── 1. Generate icon ──────────────────────────────────────────────────────────

def _make_icon():
    """Stylised efficient-frontier glyph: purple square, white frontier
    curve, gold Max-Sharpe dot, MC scatter cloud (only at sizes ≥ 32)."""
    ico_path = HERE / "taa_sandbox.ico"
    if ico_path.exists():
        return ico_path

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  Pillow not found — installing …")
        os.system(f'"{sys.executable}" -m pip install pillow -q')
        from PIL import Image, ImageDraw

    sizes = [256, 64, 32, 16]
    frames = []

    for sz in sizes:
        img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)

        # Purple rounded background (same brand purple as main app)
        d.rounded_rectangle(
            [0, 0, sz - 1, sz - 1],
            radius=int(sz * 0.12),
            fill="#660874",
        )

        # ── Frontier curve (parametric sqrt) ────────────────────────────
        x0, y0 = 0.18 * sz, 0.74 * sz       # bottom-left start
        x1, y1 = 0.86 * sz, 0.22 * sz       # upper-right end
        n_pts  = 30
        pts    = []
        for i in range(n_pts + 1):
            t = i / n_pts
            x = x0 + (x1 - x0) * t
            y = y0 - (y0 - y1) * math.sqrt(t)
            pts.append((x, y))

        lw = max(1, sz // 36)
        d.line(pts, fill="white", width=lw, joint="curve")

        # ── MC scatter cloud (skip on tiny icons; pure noise at 16px) ──
        if sz >= 32:
            scatter_t = [0.16, 0.28, 0.44, 0.58, 0.74, 0.88]
            r = max(1, sz // 36)
            for st in scatter_t:
                # Place each dot below the frontier by random-ish offset
                cx = x0 + (x1 - x0) * st
                cy = (y0 - (y0 - y1) * math.sqrt(st)) + 0.10 * sz * (0.5 + (st * 7) % 1)
                d.ellipse(
                    [cx - r, cy - r, cx + r, cy + r],
                    fill=(255, 255, 255, 180),
                )

        # ── Max-Sharpe star (gold dot on frontier) ─────────────────────
        t_ms = 0.55
        ms_x = x0 + (x1 - x0) * t_ms
        ms_y = y0 - (y0 - y1) * math.sqrt(t_ms)
        rg = max(2, sz // 16)
        d.ellipse(
            [ms_x - rg, ms_y - rg, ms_x + rg, ms_y + rg],
            fill="#f4c542",
            outline="white",
            width=max(1, sz // 64),
        )

        frames.append(img)

    frames[0].save(
        ico_path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"  Icon created: {ico_path}")
    return ico_path


# ── 2. Resolve a Python interpreter that has streamlit ───────────────────────

def _python_has_streamlit(py_exe: str) -> bool:
    try:
        r = subprocess.run(
            [py_exe, "-c", "import streamlit"],
            capture_output=True, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def _resolve_python_with_streamlit() -> str | None:
    """Return absolute path to a python.exe that can `import streamlit`.

    Probe order:
      1. The interpreter running this installer (covers the
         `Anaconda Prompt → python create_shortcut.py` case).
      2. Common Anaconda / Miniconda installation directories (base env).
      3. Each `envs/<name>/python.exe` under those installations.
    """
    if _python_has_streamlit(sys.executable):
        return sys.executable

    user = pathlib.Path(os.path.expanduser("~"))
    bases: list[pathlib.Path] = [
        user / "anaconda3",
        user / "Anaconda3",
        user / "miniconda3",
        user / "AppData" / "Local" / "anaconda3",
        user / "AppData" / "Local" / "Continuum" / "anaconda3",
        pathlib.Path(r"C:\ProgramData\anaconda3"),
        pathlib.Path(r"C:\ProgramData\Anaconda3"),
    ]

    candidates: list[pathlib.Path] = []
    for b in bases:
        py = b / "python.exe"
        if py.exists():
            candidates.append(py)
        envs_dir = b / "envs"
        if envs_dir.is_dir():
            for env in envs_dir.iterdir():
                env_py = env / "python.exe"
                if env_py.exists():
                    candidates.append(env_py)

    for c in candidates:
        if _python_has_streamlit(str(c)):
            return str(c)
    return None


def _write_python_path(py_exe: str) -> pathlib.Path:
    cfg = HERE / "python_path.txt"
    cfg.write_text(py_exe + "\n", encoding="utf-8")
    return cfg


# ── 3. Create desktop shortcut ────────────────────────────────────────────────

def _desktop():
    return pathlib.Path(os.path.expanduser("~")) / "Desktop"


def _short_path(long_path: pathlib.Path) -> str:
    """Windows 8.3 short path (ASCII) — required because the project root
    contains Chinese characters and wscript chokes on those in .lnk Arguments."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(str(long_path), buf, 512)
    return buf.value or str(long_path)


def _create_shortcut(ico_path: pathlib.Path):
    """Desktop .lnk → launch.bat (visible cmd window, mirrors the
    Anaconda-Prompt experience: streamlit logs + auto-open browser)."""
    lnk = _desktop() / "TAA Sandbox.lnk"
    bat = HERE / "launch.bat"

    bat_short  = _short_path(bat)
    ico_short  = _short_path(ico_path)
    here_short = _short_path(HERE)

    import subprocess, tempfile

    ps_script = (
        '$ws  = New-Object -ComObject WScript.Shell\n'
        f'$lnk = $ws.CreateShortcut("{lnk}")\n'
        f'$lnk.TargetPath       = "{bat_short}"\n'
        f'$lnk.WorkingDirectory = "{here_short}"\n'
        f'$lnk.IconLocation     = "{ico_short}"\n'
        '$lnk.Description      = "TAA Sandbox — independent prototype"\n'
        '$lnk.WindowStyle      = 1\n'
        '$lnk.Save()\n'
    )

    tmp = pathlib.Path(tempfile.mktemp(suffix=".ps1"))
    tmp.write_bytes(b"\xef\xbb\xbf" + ps_script.encode("utf-8"))

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp)],
        capture_output=True, text=True,
    )
    tmp.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  PowerShell error: {result.stderr.strip()}")
        sys.exit(1)

    print(f"  Shortcut created: {lnk}")
    print(f"  → target: {bat_short}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script is for Windows only.")
        sys.exit(1)

    print("Setting up TAA Sandbox launcher …")

    # 1. Icon
    ico = _make_icon()

    # 2. Resolve & cache the Python interpreter that has streamlit
    py = _resolve_python_with_streamlit()
    if py is None:
        print("\n[!] No Python with streamlit found.  Re-run this script")
        print("    from Anaconda Prompt with your env active:")
        print("        conda activate <env-name>")
        print("        python", __file__)
        sys.exit(1)
    cfg = _write_python_path(py)
    print(f"  Python  detected : {py}")
    print(f"  Cached at        : {cfg}")

    # 3. Desktop shortcut
    _create_shortcut(ico)

    print("\nDone!  Double-click 'TAA Sandbox' on your desktop "
          "to launch the prototype.")
