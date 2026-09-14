# Active Context — AX Ollama Usage Tracker

## Current Status
**README restyled to match AX BPM branding (2026-09-14).** Badge block replaced with the AX BPM badge set (GitHub Release, HACS Custom, Validate workflow, Ko-fi — all `flat-square`) and the AX BPM footer structure (☕ Support the Project + License sections) appended. Docs-only change; no code touched, so no build/pytest verification applies.

## What Was Changed
- `README.md`:
  - Replaced the old header (maintenance badge + plain Validate badge) with the AX BPM badge row: GitHub Release, HACS Custom, Validate workflow (flat-square, branch=main, label=Validate), Buy me a tea (Ko-fi).
  - Retitled the H1 to "Ollama Cloud Usage for Home Assistant" (matching AX BPM's "… for Home Assistant" naming).
  - Appended the AX BPM footer after the Disclaimer section: horizontal rule, "☕ Support the Project" section (solo-developer-on-disability blurb + for-the-badge Ko-fi banner), horizontal rule, "License" section (MIT).

## Files Modified
- `README.md` (badges + footer restyle)
- `memory-bank/activeContext.md`, `memory-bank/progress.md` (this update)

## Key Design Decisions
- **Badge parity with AX BPM, adapted to this repo** — the Add-on Build badge was replaced by the Validate workflow badge (this repo has no add-on; `validate.yml` is its only workflow). Repo name in badge URLs is `Axildor/AX-Ollama-Usage-Tracker`.
- **Footer copied verbatim from AX BPM** — same ☕ section text, same for-the-badge Ko-fi banner, same MIT License section, preserving cross-repo brand consistency.
- **Disclaimer kept** — the Ollama non-affiliation/undocumented-endpoint disclaimer is retained above the footer, as it is specific to this integration.

## Previous Context
### Ollama Cloud Usage v0.1.0 (2026-09-14)
- Full HACS custom integration implemented, verified: 54/54 pytest green, ruff clean, all modules py_compile clean. `api.py` (aiohttp client, typed exceptions), `reset_math.py` (5 h UTC session lattice, Monday weekly reset), `coordinator.py` (dynamic windows, backoff, divergence watchdog), `config_flow.py` (live key validation, verify step, reauth), `sensor.py` (per-window sensors + diagnostics), tests (54 passing), `validate.yml` CI, README rewritten.
- Key decisions: aioresponses/respx abandoned (aiohttp 3.14 incompatibility) → real local TestServer + stub client; dynamic window keys never hardcoded; strictly-greater ceil for session buckets; watchdog is coordinator state, model never mutated; HA 2026.x API adaptations; pytest-homeassistant-custom-component 0.13.365 harness.

### Repository Scaffold (2026-09-14)
- Initialized git repo on `main`; created README/LICENSE/.gitignore/memory-bank. (Superseded by the v0.1.0 implementation above.)