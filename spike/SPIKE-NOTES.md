# Step 0 spike — corner countdown widget: RESULT

**Verdict: GATE PASSED.** The signature interaction works with **pywebview alone**,
using the **opaque rounded-rectangle** baseline. The Win32 layered-window fallback is
**not needed**. Build may proceed to Step 1.

Date: 2026-07-08 · Windows 11 (10.0.26200) · primary display 1920×1080
Python 3.12.10 · pywebview 6.2.1 (EdgeChromium / WebView2 runtime 149.0.4022.98) · pywin32 312

---

## What had to be proven (spec §3, §12) and the evidence

| # | Requirement | Result | Evidence |
|---|-------------|--------|----------|
| 1 | Frameless **and** always-on-top pywebview window | ✅ | `frameless=True, on_top=True`; screenshots show no title bar/chrome, floating above the desktop |
| 2 | Positioned bottom-right, near the system clock, inside the taskbar-excluded work area | ✅ | `SPI_GETWORKAREA` → window at (1668, 916); sits directly above the clock (see image) |
| 3 | Live, readable countdown rendered in HTML/CSS/JS | ✅ | ticked 8 → 7 → 6 across captures; 34px tabular-nums digit |
| 4 | "Break now" click round-trips JS → Python → JS | ✅ | `spike_events.log`: `ROUND-TRIP OK ... break_now()`; on-screen status became the exact string returned by Python (`"Break started — get up and move."`) |

Screenshots (`spike/img/`):
- `opaque_countdown.png` — countdown running, "Break in 7", above the clock.
- `opaque_after_click.png` — after the round-trip: status line is the Python return value.
- `transparent_halo_artifact.png` — the transparency failure (see below).

The `pywebviewready` bridge event and a fallback `setTimeout` both fired `api.ready()`,
so the window painted reliably (belt-and-braces confirmed by two `WIDGET RENDERED` lines).

---

## Transparency probe — FAILS on Windows, as the spec predicted

`transparent=True` does **not** give clean per-pixel transparency on the WebView2
backend. The rounded-corner cutouts (the region outside the card) render as a **light
grey/white rectangular halo** instead of showing the desktop behind — visible in
`transparent_halo_artifact.png`. This is the exact "per-pixel transparency on Windows is
unreliable" risk flagged in spec §3.

**Decision:** ship the **opaque rounded-rectangle** widget (solid dark card,
`#12141a` window background, CSS `border-radius`). On a dark desktop the corners blend
away; on a light desktop the window is a small dark rounded card — clean and legible.
The signature interaction never depended on transparency, so nothing about the design
(§5a corner countdown) is compromised.

**Fallback status:** the native Win32 layered-window fallback documented in §3 is **held
in reserve, not required.** We would only reach for it if a future need for true
transparency (e.g. a non-rectangular glow that must sit over arbitrary content) proves
worth it. For v1 the opaque card is correct and simpler.

---

## Notes carried into the production widget (Step 2)

- **Stop the countdown on "Break now".** Spike-only cosmetic: the 1-second interval keeps
  running after the click and overwrites the ✓ with the next number. Production widget must
  cancel the timer the moment a break starts (and switch to the self-started break timer, §5a).
- **DPI awareness must be set before computing the corner.** The spike calls
  `SetProcessDpiAwareness(2)` (per-monitor v2) so `SPI_GETWORKAREA` pixels match the window
  placement. Keep this in the Windows platform adapter.
- **Work-area math belongs behind `platform/`.** `get_work_area()` here is inline for the
  spike; in the app it moves into the Windows adapter (multi-monitor: use the monitor that
  owns the primary taskbar / clock).
- **Positioning is top-left origin.** pywebview `x`/`y` place the top-left corner; bottom-right
  placement = `work.right - W - margin`, `work.bottom - H - margin`.

## How to reproduce

```powershell
# opaque baseline (default) — the shippable version
.\.venv\Scripts\python.exe .\spike\corner_widget_spike.py opaque

# transparency probe — observe the light halo at the corners
.\.venv\Scripts\python.exe .\spike\corner_widget_spike.py transparent

# headless demo used for the screenshots above (auto-clicks, captures, closes):
$env:SPIKE_DEMO="1"; $env:SPIKE_SHOT_DIR="<dir>"
.\.venv\Scripts\python.exe .\spike\corner_widget_spike.py opaque
```
Without `SPIKE_DEMO`, the widget stays up for real interaction (click "Break now" yourself;
close the window to exit). Every round-trip is appended to `spike/spike_events.log`.
