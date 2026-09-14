# Active Context — AX Ollama Usage Tracker

## Current Status
**"Ollama Cloud Usage" v0.1.0 complete (2026-09-14).** Full HACS custom integration implemented, verified: 54/54 pytest green, ruff clean, all modules py_compile clean. Ready for commit and CI run (hassfest/hacs-action run on GitHub).

## What Was Changed
- Implemented the complete `custom_components/ollama_cloud_usage/` integration:
  - `api.py` — aiohttp client for `GET https://ollama.com/api/usage` (Bearer auth, 15 s timeout, `ha-ollama-cloud-usage/0.1.0` UA, typed exceptions `OllamaAuthError`/`OllamaRateLimitError`/`OllamaApiError`, injectable `base_url` for tests).
  - `reset_math.py` — pure reset model: `next_session_reset` (strictly-greater ceil on the 5 h UTC lattice), `next_weekly_reset` (Monday 00:00 UTC), `next_reset_for_window` (unmodeled keys → `None`).
  - `coordinator.py` — `DataUpdateCoordinator` with dynamic window parsing (`WindowData`), string-cost parsing, nanosecond `server_time` capture, exponential backoff on 429/5xx (cap 1 h), `ConfigEntryAuthFailed` on 401, `UpdateFailed` on network errors, divergence watchdog (drop < 0.5× → reset event; > 30 min deviation → `anchor_divergence` flag + warning; model never self-modifies).
  - `config_flow.py` — user step (name/api_key/scan_interval, live key validation), optional verify step (computed resets + `data-time` paste, > 5 min mismatch logs + flags but completes), reauth steps (API key only), options flow (scan interval).
  - `sensor.py` — per-window Usage/Remaining/Resets At (dynamic window keys, stable unique_ids `{entry_id}_{window}_{suffix}`) + Activity Cost / Clock Skew / Anchor Divergence diagnostics; single DeviceInfo (Ollama / Ollama Cloud).
  - `__init__.py`, `const.py`, `manifest.json` (domain `ollama_cloud_usage`, `config_flow`, `cloud_polling`, `service`, version `0.1.0`), `strings.json`, `translations/en.json`.
- Scaffolding: `hacs.json`, `.ruff.toml`, `pytest.ini`, `.github/workflows/validate.yml` (ruff + hassfest + hacs/action + pytest), README rewritten (API-key instructions, sensor list, undocumented-endpoint caveat, reset-model provenance, ≥80 % automation example, multi-account, reauth).
- Tests (`tests/`, 54 passing): conftest with 4 payload fixtures (verbatim legacy sample, daily+weekly, monthly-only, weird_window) + real aiohttp test server + stub client; `test_api.py`, `test_reset_math.py`, `test_coordinator.py`, `test_watchdog.py`, `test_config_flow.py`, `test_sensors.py`.

## Files Modified
- `custom_components/ollama_cloud_usage/`: `__init__.py`, `manifest.json`, `const.py`, `api.py`, `reset_math.py`, `coordinator.py`, `config_flow.py`, `sensor.py`, `strings.json`, `translations/en.json` (all new)
- `tests/`: `__init__.py`, `conftest.py`, `test_api.py`, `test_reset_math.py`, `test_coordinator.py`, `test_watchdog.py`, `test_config_flow.py`, `test_sensors.py` (all new)
- Root: `hacs.json`, `.ruff.toml`, `pytest.ini`, `.github/workflows/validate.yml`, `README.md` (all new/rewritten)
- `memory-bank/activeContext.md`, `memory-bank/progress.md`, `memory-bank/projectstructure.md` (updated)

## Key Design Decisions
- **aioresponses abandoned** — aioresponses 0.7.9 (and respx 0.23) are incompatible with the aiohttp 3.14 pin in HA 2026.x (`ClientResponse` now requires `stream_writer`). HTTP-client tests use a real local `aiohttp.test_utils.TestServer` (with pytest-socket's `socket_enabled`); coordinator tests use a stub client injected at `coordinator._client`. `OllamaClient` gained an injectable `base_url` for this.
- **Dynamic windows everywhere** — the window key list is never hardcoded; unknown keys (`weird_window`, `monthly`) become sensors with `Resets At = unknown`.
- **Strictly-greater ceil** for session buckets: `(floor(epoch/18000)+1)*18000` — exact-boundary input yields the next boundary (15:00Z → 20:00Z).
- **Watchdog is coordinator state, not model state** — observed resets are recorded and compared against `reset_math` predictions; the model is never mutated.
- **HA 2026.x API adaptations** — `ConfigEntry` requires `discovery_keys`/`subentries_data`; `ConfigEntries.async_add` is a coroutine; `_reauth_entry_id` is a reserved ConfigFlow property (renamed `_reauth_target`); `web.Response(json=...)` removed (use `web.json_response`).
- **pytest-homeassistant-custom-component 0.13.365** (HA 2026.9.2) as the harness; PHACC's `enable_custom_integrations` fixture used for config-flow tests.

## Previous Context
### Repository Scaffold (2026-09-14)
- Initialized git repo on `main`; created README/LICENSE/.gitignore/memory-bank. No features — scope deferred. (Superseded by the v0.1.0 implementation above.)