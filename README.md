# PULSE — movement, focus & reflection companion

**A privacy-first, open-source desktop companion that nudges movement, protects deep focus, and builds gentle self-knowledge — designed for (but not limited to) ADHD and autistic minds.**

Built by the creator behind **Humans in Space** and **Divergent Futures**.

---

## What PULSE is — and what it isn't

PULSE is a **mirror, not a tracker**. Every feature serves reflection rather than data
collection or compulsive accountability:

- **Movement nudges** — gentle, user-timed breaks instead of forced interrupts; hydration
  prompts ride on every break card; configurable meal windows ("go make a sandwich" mode).
- **Focus protection** — manual Focus Mode that holds interruptions back during deep work.
- **Honest accountability** — the "hard-lock" is a best-effort wall, explained plainly:
  PULSE offers accountability, it can't force it. An hour and one minute is better than nothing.
- **The unlock meter** — no pattern is surfaced until ~15+ real observations exist behind it;
  watching your data accumulate toward the first insight *is* the reward loop. A mirror that
  shows fake patterns is worse than no mirror.
- **Privacy first** — all data local (SQLite, WAL mode), self-reported, no surveillance,
  no cloud requirement. Multi-machine sync is optional and Tailscale-only by design.

**PULSE is not medical advice.** It is a general-purpose wellbeing tool. It does not
diagnose, does not place anyone on a clinical spectrum, and does not claim to treat
anything. The patterns it surfaces are personal rhythms from your own data — they are
observations, not conclusions. If you are concerned about health, movement, focus, or
anything else, please talk to a doctor.

---

## Quick start

1. Launch PULSE — a small countdown card appears near the system clock.
2. When the countdown reaches zero (or whenever you like), click **Break now**.
3. Take the offered break — movement suggestion, hydration, meal check when relevant.
4. Rate the block afterwards (optional, one tap) — ratings feed the unlock meter
   toward your first real insight.
5. Everything else lives in the tray icon: **Pause/Resume · Break now · Insights ·
   Settings · Quit**.

First run walks you through the core choices with plain-language explainers — about
two minutes.

---

## Key features

| Area | Highlights |
|---|---|
| **Presence** | ACTIVE / IDLE / AWAY / LOCKED detection via Win32; laptop sleep never counts as work |
| **Light breaks** | Configurable interval + advance warning; self-started 90 s timer; movement + hydration |
| **Training** | 6 exercise categories × 3 levels, auto-progress/deload, 12-min "go outside" Big Break |
| **Meal support** | "Have you eaten today?" in meal windows, food-break duration picker, food/water detail chips |
| **Reflection** | Progressive stages (rating → block type → note); "was this useful?" every ~5.5 active hours |
| **Insights** | Weekly chart, pattern detection behind a 15-observation evidence floor, unlock meter |
| **Focus Guard** | Suppresses escalation during deep work; training waits for a natural edge |
| **Profiles** | 5 tunable starting points — never diagnoses |
| **Your data** | Local SQLite; one-click CSV/JSON export from Settings; optional Tailscale-only sync |

---

## Installing (Windows)

### Recommended: installer

Download `PULSE-Setup-x.x.x.exe` from the [Releases](../../releases) page and run it.

**SmartScreen warning** — you may see a blue "Windows protected your PC" screen. This is
normal for unsigned open-source software and does not mean PULSE is harmful. Click
**More info → Run anyway** to proceed. Code-signing (which removes this prompt) requires a
paid certificate; it's a later option as the project grows.

**WebView2** — PULSE uses Microsoft's WebView2 Runtime for its interface. It ships with
Windows 11 and any machine that has Microsoft Edge installed. If it is missing, the
installer will prompt you with a link to the free Microsoft download (< 1 minute to install).

### From source

```powershell
git clone https://github.com/space-divergentfutures/pulse.git
cd pulse
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pulse
```

Python 3.11+ required. WebView2 Runtime must be installed (ships with Windows 11 / Edge).

---

## Building the installer

```powershell
pip install pyinstaller
.\build.ps1 -Version 1.0.0
```

Output: `dist\PULSE\` (one-dir bundle) and, if Inno Setup 6 is installed, an
`installer\PULSE-Setup-1.0.0.exe`. See [`build.ps1`](./build.ps1) for details.

---

## Platform notes

**Windows** — fully supported (Windows 10 1809+ / Windows 11).

**Linux (X11)** — presence/idle detection works via `GetLastInputInfo` equivalent (XSS
extension or similar). Not yet packaged; run from source.

**Linux (Wayland)** ⚠️ — Wayland deliberately restricts idle-watching for security.
PULSE's presence detection does not currently have a Wayland-native path. The app will
run but idle/away detection will not function correctly. A Wayland-friendly path
(`org.freedesktop.ScreenSaver` / logind idle hints) is planned for a future release.

**macOS** — not yet packaged; may work from source with minor adjustments to the platform
layer. Not tested.

---

## Settings

See [`SETTINGS.md`](./SETTINGS.md) for a full reference of every setting, its type,
default, and what it does. Every setting also carries a plain-language **?** explainer
inside the app itself.

---

## Privacy

- All data stays on your machine in a local SQLite database (`%LOCALAPPDATA%\PULSE\pulse.db`).
- PULSE records only aggregates and self-reported ratings — never window titles, app names,
  keystrokes, or screenshots.
- Optional PocketBase sync (disabled by default) runs only over your own Tailscale network —
  it is never configured to send data to any external server.
- There is no analytics, no telemetry, no account, and no cloud dependency.

**Your data is exportable.** Settings → "Your data" exports your check-ins, breaks, meal
answers, and daily active time to CSV or JSON files in a folder you choose — with a README
explaining every column. The files are yours: analyse them, back them up, take them
elsewhere. Nothing is ever sent anywhere without your explicit action.

---

## Roadmap

Recently shipped: data export (CSV/JSON), meal detail chips, countdown deadline fix.

Under consideration (feedback welcome via Issues):

- Per-user meal window time editing in Settings
- Exercise customisation (disable/toggle first, custom library later)
- Linux idle-detection adapter (the big unlock for open-source reach)
- Optional voice/audio cue for full-screen users
- Streaks and richer habit views in Insights
- macOS platform layer

---

## Contributing

Contributions that align with the core philosophy are welcome:

- Privacy-first and local-by-default
- Non-diagnostic, honour-based, low-shame language
- A three-part explainer (what / who it suits / trade-off) for every new setting
- Test coverage for new logic

Please open an issue first for larger changes so we can discuss fit.

---

## License

**GNU AGPL-3.0** — see [`LICENSE`](./LICENSE).

Copyright (C) 2026 Divergent Futures / Humans in Space

Free to use, study, modify, and share, including commercially. Any version you
distribute — including hosting a modified version as a service — must remain open source
under this same license, with all copyright and attribution notices preserved. No
closed-source derivatives.

---

**PULSE** — track state, not people. Reflect, don't perform.
