# Active Context — AX Ollama Usage Tracker

## Current Status
Repository scaffold created (2026-09-14). No features implemented yet — the scope of the Ollama usage tracker (likely a HACS custom integration exposing sensors for Ollama usage: requests, tokens generated, per-model stats) is **to be decided** in a future session.

## What Was Changed
- Initialized git repository on `main`.
- Created `README.md` (title, purpose statement, scaffold-phase note, placeholder feature list).
- Created `LICENSE` (MIT, matching sibling repos).
- Created `.gitignore` (Python artifacts + misc, mirroring `ax_dose_logger` conventions).
- Created `memory-bank/` structure (`activeContext.md`, `progress.md`, `projectstructure.md`, `old/` archive).

## Files Modified
- `README.md` (new)
- `LICENSE` (new)
- `.gitignore` (new)
- `memory-bank/activeContext.md` (new)
- `memory-bank/progress.md` (new)
- `memory-bank/projectstructure.md` (new)
- `memory-bank/old/.gitkeep` (new)

## Key Design Decisions
- **Scaffold only** — per user direction, features are deferred; README explicitly notes the scaffold phase so future sessions have clear context.
- **Memory bank initialized immediately** — any future AI session (any mode) starts with proper context per the workspace protocol.
- **No `.devcontainer.json`** — the repo lives inside the unified DevContainer; container config deferred until the repo diverges.
- **MIT license** — consistent with sibling repos (`Home-Assistant-Pill-Logger`, `AX-BPM`).

## Previous Context
_(none — this is the first entry)_