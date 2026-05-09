"""
create_shortcut.py
Run this ONCE on your Windows machine:
    python create_shortcut.py

It will:
  1. Generate a stock-chart icon  (stock_engine.ico)
  2. Create a desktop shortcut   (Stock Engine.lnk)
     that opens the app silently via launch.vbs
"""

import os
import sys
import struct
import zlib
import base64
import pathlib

HERE = pathlib.Path(__file__).parent.resolve()

# ── 1. Generate icon ──────────────────────────────────────────────────────────

def _make_icon():
    """Draw a simple purple candlestick-chart icon and save as stock_engine.ico."""
    ico_path = HERE / "stock_engine.ico"
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

        bg_r = 8
        d.rounded_rectangle([0, 0, sz-1, sz-1], radius=int(sz*0.12),
                             fill="#660874")

        # simple bar chart: 5 bars of increasing height
        bars   = 5
        margin = sz * 0.15
        bw     = (sz - 2*margin) / (bars * 2 - 1)
        bottom = sz - margin
        heights = [0.35, 0.55, 0.45, 0.75, 0.60]

        for i, h in enumerate(heights):
            x0 = margin + i * bw * 2
            x1 = x0 + bw
            y0 = bottom - h * (sz - 2*margin)
            y1 = bottom
            d.rectangle([x0, y0, x1, y1], fill="white")

        # trend line
        pts = []
        for i, h in enumerate(heights):
            cx = margin + i * bw * 2 + bw / 2
            cy = bottom - h * (sz - 2*margin)
            pts.append((cx, cy))
        lw = max(1, sz // 32)
        for i in range(len(pts)-1):
            d.line([pts[i], pts[i+1]], fill="#ffd6f0", width=lw)

        frames.append(img)

    frames[0].save(
        ico_path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"  Icon created: {ico_path}")
    return ico_path


# ── 2. Create desktop shortcut ────────────────────────────────────────────────

def _desktop():
    return pathlib.Path(os.path.expanduser("~")) / "Desktop"


def _short_path(long_path: pathlib.Path) -> str:
    """Return the Windows 8.3 short path (ASCII-only) for a file/folder."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(str(long_path), buf, 512)
    return buf.value or str(long_path)


def _create_shortcut(ico_path: pathlib.Path):
    lnk = _desktop() / "Stock Engine.lnk"
    vbs = HERE / "launch.vbs"

    # Use 8.3 short paths for anything containing Chinese characters —
    # wscript.exe and the .lnk Arguments field choke on non-ASCII paths.
    vbs_short = _short_path(vbs)
    ico_short = _short_path(ico_path)
    here_short = _short_path(HERE)

    import subprocess, tempfile

    ps_script = (
        '$ws  = New-Object -ComObject WScript.Shell\n'
        f'$lnk = $ws.CreateShortcut("{lnk}")\n'
        '$lnk.TargetPath       = "C:\\Windows\\System32\\wscript.exe"\n'
        f'$lnk.Arguments        = \'"{vbs_short}"\'\n'
        f'$lnk.WorkingDirectory = "{here_short}"\n'
        f'$lnk.IconLocation     = "{ico_short}"\n'
        '$lnk.Description      = "Stock Back-Testing Engine"\n'
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
    print(f"  (VBS path stored as: {vbs_short})")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script is for Windows only.")
        sys.exit(1)

    print("Setting up Stock Engine launcher …")
    ico = _make_icon()
    _create_shortcut(ico)
    print("\nDone!  Double-click 'Stock Engine' on your desktop to launch the app.")
