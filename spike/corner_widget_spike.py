"""
PULSE — Build Order Step 0 spike: the corner countdown widget.

THE GATE. The whole app rests on this interaction, and it is the highest-risk
piece of the stack (spec §3, §12). Before ANY other code is written, this spike
must prove four things:

  1. A pywebview window that is frameless AND always-on-top.
  2. Positioned bottom-right, near the system clock, inside the taskbar-excluded
     work area.
  3. Renders a live, readable countdown (HTML/CSS/JS).
  4. Takes a "Break now" button click that round-trips into Python (js_api),
     proving the signature interaction end-to-end.

It also probes per-pixel transparency, which the spec flags as unreliable on
Windows. Run modes:

    python corner_widget_spike.py opaque       # rounded-rectangle baseline (default)
    python corner_widget_spike.py transparent  # attempt per-pixel transparency

Every js_api round-trip is appended to spike/spike_events.log so the button
click can be verified independently of a screenshot.

Nothing here is production code — it is a foundation probe. What it proves (and
any quirks) is recorded in spike/SPIKE-NOTES.md.
"""

import ctypes
import os
import sys
import time
import threading
from ctypes import wintypes
from pathlib import Path

import webview

HERE = Path(__file__).resolve().parent
EVENT_LOG = HERE / "spike_events.log"

WIDTH = 240
HEIGHT = 104
MARGIN = 12  # gap from the work-area edge, so it hugs the corner near the clock


def log_event(message: str) -> None:
    """Append a timestamped line so round-trips are verifiable without a screenshot."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}"
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def get_work_area() -> wintypes.RECT:
    """Primary-monitor work area (excludes the taskbar) via SPI_GETWORKAREA.

    This is proof point #2: the clock lives at the inner edge of the taskbar, so
    positioning inside the work area's bottom-right corner puts the widget right
    where the eye already goes. In the real app this moves behind platform/.
    """
    SPI_GETWORKAREA = 0x0030
    rect = wintypes.RECT()
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return rect


def corner_position() -> tuple[int, int]:
    work = get_work_area()
    x = work.right - WIDTH - MARGIN
    y = work.bottom - HEIGHT - MARGIN
    return x, y


class WidgetApi:
    """The js_api bridge. Proof point #4: JS calls these, Python acts."""

    def __init__(self) -> None:
        self.break_started = False

    def break_now(self) -> dict:
        """Fired by the 'Break now' button. This is the signature interaction."""
        self.break_started = True
        log_event("ROUND-TRIP OK: JS 'Break now' click reached Python -> break_now()")
        return {"ok": True, "message": "Break started — get up and move."}

    def countdown_done(self) -> dict:
        log_event("ROUND-TRIP OK: JS reported countdown reached 0 -> countdown_done()")
        return {"ok": True}

    def ready(self) -> dict:
        log_event("WIDGET RENDERED: JS 'ready' fired (window painted).")
        return {"ok": True}


def build_html(transparent: bool) -> str:
    # Transparent mode: page background is see-through; only the card paints.
    # Opaque mode: the card fills a solid rounded rectangle (the reliable baseline).
    page_bg = "transparent" if transparent else "#12141a"
    mode_label = "transparent" if transparent else "opaque"
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; height: 100%;
    background: {page_bg};
    font-family: "Segoe UI", system-ui, sans-serif;
    -webkit-user-select: none; user-select: none; overflow: hidden;
  }}
  .card {{
    box-sizing: border-box;
    width: 100%; height: 100%;
    background: linear-gradient(160deg, #1b1f2a 0%, #12141a 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    box-shadow: 0 6px 22px rgba(0,0,0,0.45);
    color: #e8ebf2;
    display: flex; flex-direction: column;
    padding: 10px 12px; gap: 6px;
  }}
  .row {{ display: flex; align-items: baseline; justify-content: space-between; }}
  .label {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
            color: #8b93a7; }}
  .count {{ font-size: 34px; font-weight: 700; line-height: 1;
            font-variant-numeric: tabular-nums; color: #7fd1c1; }}
  .count.done {{ color: #f2b84b; }}
  button {{
    appearance: none; border: none; cursor: pointer;
    background: #2f6f63; color: #eafff8;
    font-size: 13px; font-weight: 600; border-radius: 9px;
    padding: 7px 0; width: 100%;
    transition: background .12s ease;
  }}
  button:hover {{ background: #3a8577; }}
  button:active {{ background: #275d53; }}
  .status {{ font-size: 10px; color: #8b93a7; min-height: 12px; text-align: center; }}
</style>
</head>
<body>
  <div class="card">
    <div class="row">
      <span class="label">Break in</span>
      <span class="count" id="count">10</span>
    </div>
    <button id="breakBtn">Break now</button>
    <div class="status" id="status">countdown running &middot; {mode_label}</div>
  </div>

<script>
  let remaining = 10;
  const countEl  = document.getElementById('count');
  const statusEl = document.getElementById('status');
  const btn      = document.getElementById('breakBtn');

  function fmt(s) {{ return s > 0 ? s : 0; }}

  const tick = setInterval(() => {{
    remaining -= 1;
    countEl.textContent = fmt(remaining);
    if (remaining <= 0) {{
      clearInterval(tick);
      countEl.classList.add('done');
      countEl.textContent = '0';
      statusEl.textContent = 'time for a break';
      if (window.pywebview) window.pywebview.api.countdown_done();
    }}
  }}, 1000);

  btn.addEventListener('click', async () => {{
    if (window.pywebview) {{
      const res = await window.pywebview.api.break_now();
      statusEl.textContent = res && res.message ? res.message : 'break started';
    }} else {{
      statusEl.textContent = 'break started (no bridge)';
    }}
    countEl.textContent = '\\u2713';
    countEl.classList.add('done');
  }});

  // Signal to Python that the window actually painted.
  window.addEventListener('pywebviewready', () => window.pywebview.api.ready());
  // Fallback in case the ready event already fired before this listener attached.
  setTimeout(() => {{ if (window.pywebview) window.pywebview.api.ready(); }}, 800);
</script>
</body>
</html>"""


def capture_screen(path: Path, label: str) -> None:
    """Grab the full primary screen so the widget can be inspected as a real pixel
    result — the honest way to judge frameless/transparency/position on Windows."""
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab()
        img.save(path)
        log_event(f"SCREENSHOT [{label}] saved -> {path} ({img.width}x{img.height})")
    except Exception as exc:  # pragma: no cover - diagnostic path
        log_event(f"SCREENSHOT [{label}] FAILED: {exc!r}")


def demo_driver(window) -> None:
    """Headless proof harness (SPIKE_DEMO=1): let it render, screenshot it, drive the
    'Break now' button through the JS bridge, screenshot the result, then close.
    The round-trip through window.pywebview.api.break_now() is genuine regardless of
    whether a human or this driver triggers the DOM click."""
    shot_dir = Path(os.environ.get("SPIKE_SHOT_DIR", HERE))
    mode = os.environ.get("SPIKE_MODE", "opaque")
    time.sleep(3.5)  # let the window paint and the countdown tick a few seconds
    capture_screen(shot_dir / f"spike_{mode}_1_countdown.png", "countdown")
    try:
        window.evaluate_js("document.getElementById('breakBtn').click()")
        log_event("DEMO: synthetic click dispatched to #breakBtn")
    except Exception as exc:
        log_event(f"DEMO: evaluate_js click FAILED: {exc!r}")
    time.sleep(1.2)
    capture_screen(shot_dir / f"spike_{mode}_2_after_click.png", "after_click")
    time.sleep(0.4)
    try:
        window.destroy()
    except Exception:
        pass


def main() -> None:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "opaque").lower()
    transparent = mode == "transparent"
    os.environ["SPIKE_MODE"] = mode
    demo = os.environ.get("SPIKE_DEMO") == "1"

    # Keep pixel math honest on high-DPI displays before we compute the corner.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor-aware v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    x, y = corner_position()
    log_event(
        f"SPIKE START mode={mode} frameless=True on_top=True "
        f"size={WIDTH}x{HEIGHT} pos=({x},{y})"
    )

    api = WidgetApi()
    window = webview.create_window(
        "PULSE spike",
        html=build_html(transparent),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        frameless=True,       # proof point #1a
        on_top=True,          # proof point #1b
        resizable=False,
        transparent=transparent,   # probe: unreliable on Windows per spec
        background_color="#12141a",
        easy_drag=False,
    )
    # debug=False so no devtools frame; this is the real frameless experience.
    if demo:
        webview.start(demo_driver, window, debug=False)
    else:
        webview.start(debug=False)
    log_event("SPIKE END (window closed)")


if __name__ == "__main__":
    main()
