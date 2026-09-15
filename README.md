[![GitHub Release](https://img.shields.io/github/v/release/Axildor/AX-Ollama-Usage-Tracker?style=flat-square)](https://github.com/Axildor/AX-Ollama-Usage-Tracker/releases)
[![HACS Status](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://github.com/hacs/integration)
[![Validate](https://img.shields.io/github/actions/workflow/status/Axildor/AX-Ollama-Usage-Tracker/validate.yml?branch=main&label=Validate&style=flat-square)](https://github.com/Axildor/AX-Ollama-Usage-Tracker/actions/workflows/validate.yml)
[![Buy me a tea](https://img.shields.io/badge/Buy_me_a_tea-☕-FF5E5B?style=flat-square&logo=ko-fi&logoColor=white)](https://ko-fi.com/axildor)


#  AX Ollama Usage Tracker for Home Assistant <img width="75" height="75" alt="AX Ollama usage tracker" src="https://github.com/user-attachments/assets/c7c9748c-a7ea-41b0-9a3d-d1f5bd62e824" />

A [Home Assistant](https://www.home-assistant.io) custom integration (HACS) that
exposes your **ollama.com cloud usage limits** as sensors — so you can see how
much of your session and weekly quota is left, get notified before you run out,
and track your spending, all inside Home Assistant.

<img width="1002" height="895" alt="image" src="https://github.com/user-attachments/assets/f8589afa-0e08-4481-831d-ed2b6709168a" />

## Sensors

For every usage window your account reports (`session`, `weekly`, `daily`,
`monthly`, …) the integration creates these sensors:

| Sensor | Description |
|--------|-------------|
| `<Window> Usage` | % of the window consumed (attributes: models used, predicted reset time) |
| `<Window> Remaining` | % left in the window |
| `<Window> Resets At` | When the window resets (UTC timestamp) |
| `<Window> <model> Requests` | Request count for one model in that window (e.g. *Session glm-5.3-flash Requests*) |

Plus one device-level diagnostic set per account:

| Sensor | Description |
|--------|-------------|
| Activity Cost | USD spent over the rolling 4-week period |
| Clock Skew | Seconds between your Home Assistant clock and ollama.com's server time *(diagnostic)* |
| Anchor Divergence | Turns on if observed resets deviate from the predicted reset model *(diagnostic)* |

Windows are picked up **dynamically** — if Ollama adds a new usage window, its
sensors appear automatically on the next poll. Per-model request sensors are
likewise created automatically for every model your account uses in a window;
if a model stops appearing in the payload, its sensor reports *unavailable*
but is not removed.

All entities carry human-readable names (e.g. **Ollama Cloud Session Usage**,
**Ollama Cloud Weekly Remaining**). The two diagnostic sensors are hidden from
dashboards by default but visible under the device's diagnostics area.

## Getting an API key

Create an API key at **ollama.com → Settings → API keys**.

> ⚠️ This integration authenticates with your **API key** — NOT the browser
> session cookie, and NOT device keys.

## Installation

**HACS (recommended)**
1. Add this repository as a **custom repository** in HACS (category:
   `integration`).
2. Install **AX Ollama Usage Tracker**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add
   Integration → AX Ollama Usage Tracker**.

**Manual**
1. Copy `custom_components/ax_ollama_usage` into your
   `config/custom_components` directory.
2. Restart Home Assistant.

## Upgrading from v0.1.x

Version 0.2.0 renamed the integration domain from `ollama_cloud_usage` to
`ax_ollama_usage` to avoid a conflict with another integration. This is a
**breaking change**: existing config entries created under the old domain
will no longer load.

1. Note your API key (or just have it ready).
2. Remove the old **AX Ollama Usage Tracker** entry via
   **Settings → Devices & Services**.
3. Delete the old `custom_components/ollama_cloud_usage` folder if you
   installed manually.
4. Re-add the integration (see Installation above).

Entity IDs regenerate under the new `sensor.ax_ollama_usage_*` prefix, so
automations or dashboards referencing the old `sensor.ollama_cloud_usage_*`
entity IDs must be updated.

## Configuration

| Field | Description |
|-------|-------------|
| Name | Display name (default "Ollama Cloud") |
| API key | Your ollama.com API key (validated live during setup) |
| Scan interval | Poll interval in seconds (default 300, minimum 60) |

The scan interval can be changed later via the integration's **Configure**
(options) menu. During setup an optional second step shows the computed next
session and weekly reset times so you can sanity-check them against the
ollama.com settings page — you can skip it.

## Reset times

The ollama.com API does not return reset timestamps, so the integration
computes them:

- **Weekly** windows reset **Monday 00:00 UTC**.
- **Session** windows reset in **fixed 5-hour buckets** (00:00, 05:00, 10:00,
  15:00, 20:00 UTC).
- **Other windows** (`daily`, `monthly`, unknown): the reset anchor is
  unknown, so *Resets At* reports `unknown` instead of guessing.

A built-in watchdog compares observed usage resets against these predictions;
if they disagree by more than 30 minutes, the *Anchor Divergence* sensor turns
on and a warning is logged.

## Example automation — notify when usage ≥ 80%

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

This integration is not affiliated with or endorsed by Ollama. It reads an
**undocumented** endpoint (`https://ollama.com/api/usage`) that may change or
break without notice. It performs a single read-only `GET` per poll with your
API key — nothing else is ever sent to ollama.com.

---

## ☕ Support the Project

I'm a solo developer on disability building Home Assistant integrations
and add-ons independently. Your support keeps servers online, API quotas
funded, and the black tea brewing while I debug Python.

If this integration is useful to you, there's no obligation — but any
support is highly appreciated.

[![Buy me a tea](https://img.shields.io/badge/Buy_me_a_tea-on_Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/axildor)

---

## License

MIT
