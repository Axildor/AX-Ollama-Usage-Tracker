# Project Structure — AX Ollama Usage Tracker

> Live reference: directory tree + one-line file roles. Long-form rationale lives in [`memory-bank/old/projectstructure-archive.md`](memory-bank/old/projectstructure-archive.md) — read it only if a one-line summary here lacks the context you need.

---

## Directory Tree

```
AX-Ollama-Usage-Tracker/
├── custom_components/
│   └── ollama_cloud_usage/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── api.py
│       ├── reset_math.py
│       ├── coordinator.py
│       ├── config_flow.py
│       ├── sensor.py
│       ├── strings.json
│       └── translations/
│           └── en.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_reset_math.py
│   ├── test_coordinator.py
│   ├── test_watchdog.py
│   ├── test_config_flow.py
│   └── test_sensors.py
├── .github/
│   └── workflows/
│       └── validate.yml
├── README.md
├── LICENSE
├── hacs.json
├── pytest.ini
├── .ruff.toml
├── .gitignore
└── memory-bank/
    ├── activeContext.md
    ├── progress.md
    ├── projectstructure.md
    └── old/
        └── .gitkeep
```

---

## Root-Level Files (one-line roles)

| File | Role |
|------|------|
| [`README.md`](README.md) | User doc — what it does, API-key creation, sensor list, undocumented-endpoint caveat, reset-model provenance, automation example, multi-account, reauth. |
| [`hacs.json`](hacs.json) | HACS manifest (name, render_readme, min HA 2026.1.0). |
| [`pytest.ini`](pytest.ini) | Pytest config (asyncio auto mode, testpaths, pythonpath). |
| [`.ruff.toml`](.ruff.toml) | Ruff lint/format config (HA style, py313, line 88). |
| [`LICENSE`](LICENSE) | MIT license. |
| [`.gitignore`](.gitignore) | Python artifacts + misc ignores. |
| [`.github/workflows/validate.yml`](.github/workflows/validate.yml) | CI: ruff check/format, hassfest, hacs/action (integration), pytest. |

---

## `custom_components/ollama_cloud_usage/`

| File | Role |
|------|------|
| [`__init__.py`](custom_components/ollama_cloud_usage/__init__.py) | Entry setup/unload: coordinator creation, first refresh, platform forwarding, update listener reload. |
| [`manifest.json`](custom_components/ollama_cloud_usage/manifest.json) | Hassfest manifest — domain `ollama_cloud_usage`, config_flow, cloud_polling, service, v0.1.0, no requirements. |
| [`const.py`](custom_components/ollama_cloud_usage/const.py) | Domain constants: endpoints, timeouts, backoff caps, watchdog thresholds, sensor suffixes, attribute keys. |
| [`api.py`](custom_components/ollama_cloud_usage/api.py) | aiohttp client for `GET /api/usage` — Bearer auth, 15 s timeout, UA, typed exceptions (Auth/RateLimit/Api), injectable base_url. |
| [`reset_math.py`](custom_components/ollama_cloud_usage/reset_math.py) | Pure reset model: session (strictly-greater 5 h UTC ceil), weekly (Monday 00:00 UTC), unmodeled windows → None. |
| [`coordinator.py`](custom_components/ollama_cloud_usage/coordinator.py) | DataUpdateCoordinator: dynamic window parsing, string-cost parse, server_time capture, 429/5xx backoff, 401 → auth failed, watchdog (drop detection, reset events, divergence flag). |
| [`config_flow.py`](custom_components/ollama_cloud_usage/config_flow.py) | Config flow: user step (live key validation), optional verify step (data-time paste), reauth steps, options flow (scan interval). |
| [`sensor.py`](custom_components/ollama_cloud_usage/sensor.py) | Sensor platform: per-window Usage/Remaining/Resets At (dynamic keys) + Activity Cost/Clock Skew/Anchor Divergence diagnostics; single DeviceInfo. |
| [`strings.json`](custom_components/ollama_cloud_usage/strings.json) | Flow strings (user/verify/reauth steps, errors, aborts, options). |
| [`translations/en.json`](custom_components/ollama_cloud_usage/translations/en.json) | English translations (mirrors strings.json). |

---

## `tests/`

| File | Role |
|------|------|
| [`conftest.py`](tests/conftest.py) | Payload fixtures (legacy/daily+weekly/monthly/weird_window), real aiohttp test server, stub usage client, coordinator factory. |
| [`test_api.py`](tests/test_api.py) | HTTP client tests against the local server: happy path, headers, 401/429/5xx, timeout, non-JSON. |
| [`test_reset_math.py`](tests/test_reset_math.py) | Pure reset model: mid-bucket, exact-boundary strictly-greater, Monday-exact +7 d, Friday→Monday, unmodeled → None. |
| [`test_coordinator.py`](tests/test_coordinator.py) | Parsing (all 4 fixtures), 401 → auth failed, 429 backoff + cap, timeout/network → UpdateFailed, backoff reset, window disappearance, ISO/model parsing helpers. |
| [`test_watchdog.py`](tests/test_watchdog.py) | Drop → reset event, > 30 min deviation → flag, no-drop at boundary → no flag, small drop ignored, unmodeled event without flag. |
| [`test_config_flow.py`](tests/test_config_flow.py) | User step errors (invalid_auth/cannot_connect), good key → verify, empty verify → create entry, divergent paste logs but completes, reauth prompts key only. |
| [`test_sensors.py`](tests/test_sensors.py) | Usage value/attributes, remaining, resets-at (session computed, unmodeled unknown), vanished window unavailable, diagnostics, shared DeviceInfo. |

---

## `memory-bank/` Directory

| File | Role |
|------|------|
| [`memory-bank/activeContext.md`](memory-bank/activeContext.md) | Current feature status + recent changes (truncated; current + last 2 archived blocks). |
| [`memory-bank/progress.md`](memory-bank/progress.md) | Recent completed work (truncated; last ~16 feature sections). |
| [`memory-bank/projectstructure.md`](memory-bank/projectstructure.md) | This file — live directory tree + one-line file roles. |
| [`memory-bank/old/`](memory-bank/old/) | Full history archive; read only when the truncated root files lack context. |

---

> 📜 **Long-form per-file descriptions are archived in [`memory-bank/old/projectstructure-archive.md`](memory-bank/old/projectstructure-archive.md)** — read it only if a one-line summary above lacks the context you need.