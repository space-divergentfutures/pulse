# PULSE — movement, focus & reflection companion

**A privacy-first, open-source desktop companion that nudges movement, protects deep focus, and builds gentle self-knowledge — designed for (but not limited to) ADHD and autistic minds.**

Built by the creator behind **Humans in Space** and **Divergent Futures**.

> **Status: pre-build.** The design is complete and decision-final in
> [`pulse-build-spec-v2_1.md`](./pulse-build-spec-v2_1.md); implementation has not started.
> [`pulse-review-packet-v1.md`](./pulse-review-packet-v1.md) holds the external design review.

## The idea

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
  no cloud requirement. Multi-machine sync is optional and conflict-safe by design.

## Stack (per spec)

Python + pywebview desktop app for Windows; SQLite storage; PyInstaller + Inno Setup
distribution. Build order starts with a spike proving the frameless always-on-top corner
widget — the highest-risk piece and the signature interaction.

## License

**GNU AGPL-3.0** — see [`LICENSE`](./LICENSE).

Copyright (C) 2026 Divergent Futures / Humans in Space

Free to use, study, modify, and share, including commercially. Any version you
distribute — including hosting a modified version as a service — must remain open source
under this same license, with all copyright and attribution notices preserved. No
closed-source derivatives.
