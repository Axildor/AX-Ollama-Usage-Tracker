# Ollama Cloud Usage

![Project Maintenance](https://img.shields.io/maintenance/yes/2026.svg)
[![Validate](https://github.com/Axildor/AX-Ollama-Usage-Tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/Axildor/AX-Ollama-Usage-Tracker/actions/workflows/validate.yml)

A [Home Assistant](https://www.home-assistant.io) custom integration (HACS) that
exposes your **ollama.com cloud usage limits** as sensors.

## What it does

- Polls the (verified-but-undocumented) `GET https://ollama.com/api/usage`
  endpoint once per scan interval (default 300 s, minimum 60 s).
- Shows, per usage window (`session`, `weekly`, `daily`, `monthly`, or any
  other key Ollama introduces):
  - **Usage** — % of the window consumed
  - **Remaining** — % left
  - **Resets At** — computed UTC reset time (modeled windows only)
- Per-account diagnostics:
  - **Activity Cost** — USD spent over the rolling 4-week period
  - **Clock Skew** — seconds between your HA clock and ollama.com's server
    time (a warning is logged beyond ±120 s, because the reset model depends
    on your local clock being correct)
  - **Anchor Divergence** — diagnostic flag raised when an observed usage
    reset deviates from the model by more than 30 minutes

## Getting an API key

Create an API key at **ollama.com → Settings → API keys**.

> ⚠️ This integration authenticates with your **API key** — NOT the browser
> session cookie, and NOT device keys.

## Installation (HACS)

1. Add this repository as a **custom repository** in HACS (category:
   `integration`).
2. Install **Ollama Cloud Usage**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add
   Integration → Ollama Cloud Usage**.

## Configuration

| Field | Description |
|-------|-------------|
| Name | Display name (default "Ollama Cloud") |
| API key | Your ollama.com API key (validated live during setup) |
| Scan interval | Poll interval in seconds (default 300, min 60) |

An optional second step shows the computed next session/weekly resets and
lets you paste `data-time` values from the ollama.com settings page to
sanity-check the reset model. Mismatches are logged and flagged — setup
still completes.

## The reset model (reverse-engineered)

The API returns **no reset timestamps**, so reset times are computed
client-side. The model is deterministic but reverse-engineered — treat it as
a model, not a contract:

- **Weekly** resets **Monday 00:00:00 UTC** (evidence: settings-page
  `data-time="2026-09-21T00:00:00Z"` with the current window opened Monday
  2026-09-14T00:00:00Z).
- **Session** resets in **fixed 5-hour buckets on the UTC lattice anchored
  at 00:00 UTC** (evidence: settings-page `data-time` values
  `2026-09-14T05:00:00Z` and `2026-09-14T15:00:00Z`, both ≡ 0 mod 5 h).
- **Any other window** (`daily`, `monthly`, unknown): reset anchor unknown —
  the *Resets At* sensor reports `unknown` rather than fabricating a value.

A built-in **divergence watchdog** tracks usage drops and compares observed
resets against the model; a deviation beyond 30 minutes raises the
*Anchor Divergence* diagnostic and logs a warning. The model is never
self-modified.

## Undocumented endpoint caveat

The integration reads `https://ollama.com/api/usage`, an **undocumented**
endpoint that **may change or break without notice**. It performs a single
read-only `GET` per poll with your API key — nothing else is ever sent to
ollama.com.

## Example automation — notify when any window ≥ 80%

```yaml
automation:
  - alias: "Ollama usage warning"
    trigger:
      - platform: numeric_state
        entity_id:
          - sensor.ollama_cloud_session_usage
          - sensor.ollama_cloud_weekly_usage
        above: 80
    action:
      - service: notify.persistent_notification
        data:
          title: "Ollama Cloud usage high"
          message: "{{ trigger.to_state.name }} is at {{ trigger.to_state.state }}%."
```

## Multi-account

Each config entry is one account — add the integration again with a
different API key for a second account. Entities are namespaced by entry.

## Re-authentication

If your API key is revoked or expires, a 401 from ollama.com triggers the
reauth flow: you are prompted for a new API key only, and the entry reloads.

## Disclaimer

This integration is not affiliated with or endorsed by Ollama. The endpoint
it reads is undocumented and could change at any time.