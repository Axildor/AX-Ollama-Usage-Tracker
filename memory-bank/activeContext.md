# Active Context — AX Ollama Usage Tracker

## Current Status
**README rewritten with user-focused integration functionality (2026-09-14).** Following the AX BPM badge/footer restyle, the README body was rewritten to document actual integration functionality from the source code: sensor tables (per-window Usage/Remaining/Resets At + diagnostics), configuration, reset model, automation example, multi-account, reauth. Docs-only change; no code touched, so no build/pytest verification applies.

## What Was Changed
- `README.md` (full body rewrite, badges + footer preserved):
  - New "Sensors" section with two tables: per-window sensors (`<window> Usage` with models/predicted-reset attributes, `<window> Remaining`, `<window> Resets At`) and diagnostics (Activity Cost USD/4-week, Clock Skew seconds, Anchor Divergence flag). Noted dynamic window pickup.
  - Installation now has HACS + Manual paths (Manual was missing).
  - Configuration table kept; added note that scan interval is changeable via the Configure (options) menu and that the verify step is optional/skippable.
  - "The reset model (reverse-engineered)" section condensed to user-relevant "Reset times" (Monday 00:00 UTC weekly, 5-hour session buckets, unknown → `unknown`), removed the `data-time` evidence/provenance detail.
  - Kept: API key instructions + warning, ≥80% automation example, Multi-account, Re-authentication.
  - Disclaimer merged with the undocumented-endpoint caveat into one section (single read-only GET per poll).
  - AX BPM badge block and ☕ Support/License footer unchanged.

## Files Modified
- `README.md` (body rewrite)
- `memory-bank/activeContext.md`, `memory-bank/progress.md` (this update)

## Key Design Decisions
- **User-relevant content only** — internal implementation details (watchdog thresholds as constants, `data-time` reverse-engineering evidence, backoff internals, unique_id scheme) were dropped or condensed; what remains is what a user needs: what sensors exist, how to install/configure, what reset times mean, and the automation example.
- **Sensor names verified against `sensor.py`** — entity layout (per-window triple + 3 diagnostics), attributes (`models`, `predicted_reset_utc`), and the `unknown` Resets At behavior for unmodeled windows all match the code.
- **Disclaimer + caveat merged** — both said "undocumented endpoint, may break"; one section avoids duplication.

## Previous Context
### Ollama Cloud Usage v0.1.0 (2026-09-14)
- Full HACS custom integration implemented, verified: 54/54 pytest green, ruff clean, all modules py_compile clean. `api.py` (aiohttp client, typed exceptions), `reset_math.py` (5 h UTC session lattice, Monday weekly reset), `coordinator.py` (dynamic windows, backoff, divergence watchdog), `config_flow.py` (live key validation, verify step, reauth), `sensor.py` (per-window sensors + diagnostics), tests (54 passing), `validate.yml` CI, README rewritten.
- Key decisions: aioresponses/respx abandoned (aiohttp 3.14 incompatibility) → real local TestServer + stub client; dynamic window keys never hardcoded; strictly-greater ceil for session buckets; watchdog is coordinator state, model never mutated; HA 2026.x API adaptations; pytest-homeassistant-custom-component 0.13.365 harness.

### Repository Scaffold (2026-09-14)
- Initialized git repo on `main`; created README/LICENSE/.gitignore/memory-bank. (Superseded by the v0.1.0 implementation above.)