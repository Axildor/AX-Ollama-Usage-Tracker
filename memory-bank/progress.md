# Progress — AX Ollama Usage Tracker

## Ollama Cloud Usage v0.1.0 — Full Integration (2026-09-14)
- [x] Scaffold `custom_components/ollama_cloud_usage/`, `tests/`, `.github/workflows/`, root configs
- [x] `manifest.json` (domain `ollama_cloud_usage`, config_flow, cloud_polling, service, v0.1.0) + `hacs.json` + `const.py`
- [x] `api.py` — aiohttp client, Bearer auth, 15 s timeout, HA UA, typed exceptions, injectable base_url
- [x] `reset_math.py` — pure `next_session_reset` (strictly-greater 5 h UTC ceil), `next_weekly_reset` (Monday 00:00 UTC), `next_reset_for_window` (unmodeled → None)
- [x] `coordinator.py` — dynamic window parsing, string-cost parse, nanosecond server_time, 429/5xx backoff (cap 1 h), 401 → ConfigEntryAuthFailed, network → UpdateFailed, divergence watchdog (drop < 0.5×, > 30 min deviation flag)
- [x] `config_flow.py` — user step with live key validation, optional verify step (data-time paste, > 5 min mismatch logs + flags), reauth (key only), options flow
- [x] `sensor.py` — per-window Usage/Remaining/Resets At (dynamic keys, stable unique_ids) + Activity Cost/Clock Skew/Anchor Divergence; single DeviceInfo
- [x] `strings.json` + `translations/en.json`
- [x] Tests: 4 payload fixtures (verbatim legacy, daily+weekly, monthly-only, weird_window), real aiohttp test server for api tests, stub client for coordinator tests — 54/54 passing
- [x] `.github/workflows/validate.yml` (ruff + hassfest + hacs/action + pytest), README rewritten, `.ruff.toml`, `pytest.ini`
- [x] Verify: `pytest tests/` 54 passed; `ruff check` + `ruff format --check` clean; `py_compile` all modules OK
- [x] Memory bank updated (activeContext, progress, projectstructure)

**Notes:** aioresponses/respx incompatible with aiohttp 3.14 (HA 2026.x pin) — replaced with a real local aiohttp test server + stub client. hassfest/hacs-action run in CI (GitHub), not locally.

## Repository Scaffold (2026-09-14)
- [x] Create repo directory `/workspaces/AX-Ollama-Usage-Tracker` and `git init -b main`
- [x] Create `README.md` — title, purpose statement, scaffold-phase status badge, placeholder feature list
- [x] Create `LICENSE` — MIT, matching sibling repos' style
- [x] Create `.gitignore` — Python artifacts + misc (mirrors `ax_dose_logger` conventions)
- [x] Create `memory-bank/` structure — `activeContext.md`, `progress.md`, `projectstructure.md`, `old/` archive with `.gitkeep`
- [x] Initial git commit on `main`
- [x] Verify: `git log`, file listing, repo visible in DevContainer workspace

## README Content Rewrite — User-Focused Functionality (2026-09-14)
- [x] Read `sensor.py`, `config_flow.py`, `const.py`, `coordinator.py` to extract actual functionality
- [x] Add "Sensors" section: per-window Usage/Remaining/Resets At table + diagnostics table (Activity Cost, Clock Skew, Anchor Divergence)
- [x] Note dynamic window pickup (new Ollama windows become sensors automatically)
- [x] Add Manual installation path alongside HACS
- [x] Condense reset-model section to user-relevant "Reset times" (drop data-time evidence)
- [x] Add options-flow note (scan interval changeable via Configure) and mark verify step skippable
- [x] Merge Disclaimer + undocumented-endpoint caveat into one section
- [x] Keep badges, automation example, multi-account, reauth, ☕ footer, License
- [x] Memory bank updated (activeContext, progress)
- [x] Verify: docs-only change — sensor names/attributes cross-checked against `sensor.py` and `const.py`; no build verification applicable

## README Restyle — AX BPM Badge/Footer Parity (2026-09-14)
- [x] Read AX BPM README badge block and footer structure as the reference
- [x] Replace README header badges with AX BPM set: GitHub Release, HACS Custom, Validate workflow (flat-square), Ko-fi tea
- [x] Retitle H1 to "Ollama Cloud Usage for Home Assistant"
- [x] Append AX BPM footer: ☕ Support the Project section (Ko-fi for-the-badge banner) + License (MIT)
- [x] Keep the Ollama-specific Disclaimer section above the footer
- [x] Memory bank updated (activeContext, progress)
- [x] Verify: docs-only change — README structure reviewed against AX BPM reference; no code/build verification applicable