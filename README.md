[![GitHub Release](https://img.shields.io/github/v/release/Axildor/AX-Ollama-Usage-Tracker?style=flat-square)](https://github.com/Axildor/AX-Ollama-Usage-Tracker/releases)
[![HACS Status](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://github.com/hacs/integration)
[![Validate](https://img.shields.io/github/actions/workflow/status/Axildor/AX-Ollama-Usage-Tracker/validate.yml?branch=main&label=Validate&style=flat-square)](https://github.com/Axildor/AX-Ollama-Usage-Tracker/actions/workflows/validate.yml)
[![Buy me a tea](https://img.shields.io/badge/Buy_me_a_tea-☕-FF5E5B?style=flat-square&logo=ko-fi&logoColor=white)](https://ko-fi.com/axildor)


#  AX Ollama Usage Tracker for Home Assistant <img width="75" height="75" alt="AX Ollama usage tracker" src="https://github.com/user-attachments/assets/c7c9748c-a7ea-41b0-9a3d-d1f5bd62e824" />

A [Home Assistant](https://www.home-assistant.io) custom integration (HACS) that
exposes your **ollama.com cloud usage and balance** as sensors — so you can see how
much of your session and weekly quota is left, track your request volume, watch
your purchased credits, and get notified before you run out, all inside Home
Assistant.

<img width="1002" height="895" alt="image" src="https://github.com/user-attachments/assets/f8589afa-0e08-4481-831d-ed2b6709168a" />

## Sensors

For every usage window your account reports (`session`, `weekly`, `daily`,
`monthly`, …) the integration creates these sensors:

| Sensor | Description |
|--------|-------------|
| `<Window> Usage` | % of the window consumed (attributes: server reset time, window key) |
| `<Window> Remaining` | % left in the window (straight from the server) |
| `<Window> Resets At` | When the window resets — the server's own timestamp, passed through (UTC) |

Plus one device-level set per account:

| Sensor | Description |
|--------|-------------|
| Requests 24h | Requests over the last 24 hours (attribute: current-hour count — a live rate signal) |
| Requests 7d | Requests over the last 7 days |
| Purchased Balance | Your purchased credit balance in USD |
| Included Balance | Included credit balance in USD *(credits-plan accounts only)* |
| Included Allowance | Included allowance in USD *(credits-plan accounts only)* |
| Included Resets At | When the included-credit period ends *(credits-plan accounts only)* |
| Clock Skew | Seconds between your Home Assistant clock and ollama.com's server time *(diagnostic)* |
| Anchor Divergence | Turns on if observed resets deviate from the predicted reset model *(diagnostic, watchdog opt-in)* |

Windows are picked up **dynamically** — if Ollama adds a new usage window, its
sensors appear automatically on the next poll. If a window stops appearing in
the payload, its sensors report *unavailable* but are not removed.

Both balance-plan shapes are supported: legacy accounts (per-window
`remaining_percent` + `resets_at`) and credits-plan accounts
(`balance_usd` / `allowance_usd` + period). If Ollama flips your account
between the two, the integration follows automatically.

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

## Upgrading from v0.2.x

Version 0.3.0 migrates to the new documented balance + usage endpoints. The
**Activity Cost** and per-model **Requests** sensors are **removed on
upgrade** — their registry entries are cleaned up automatically, so no
unavailable ghosts linger. Your existing `<Window> Usage` / `Remaining` /
`Resets At` sensors keep their entity IDs and meaning (Usage is still the
consumed percentage — the integration converts the server's remaining figure
for you).

## Configuration

| Field | Description |
|-------|-------------|
| Name | Display name (default "Ollama Cloud") |
| API key | Your ollama.com API key (validated live during setup) |
| Scan interval | Poll interval in seconds (default 300, minimum 60) |

The scan interval and an optional **reset-divergence watchdog** toggle can be
changed later via the integration's **Configure** (options) menu. The watchdog
is off by default — the server's own reset timestamps are authoritative.

## Reset times

Since v0.3 the ollama.com API returns reset timestamps directly, and the
*Resets At* sensors pass them through untouched (server-authoritative).

An optional watchdog (off by default) cross-checks observed resets against a
reverse-engineered model:

- **Weekly** windows reset **Monday 00:00 UTC**.
- **Session** windows reset in **fixed 5-hour buckets anchored in epoch
  time** — because 5 hours does not divide a day, the boundary times drift
  4 hours earlier each day on a 5-day cycle (e.g. 00/05/10/15/20 one day,
  03/08/13/18/23 three days later). This is expected behavior, not a bug.
- **Other windows** (`daily`, `monthly`, unknown): no model — the watchdog
  records the event but cannot flag divergence.

If the watchdog is enabled and an observed reset disagrees with the model by
more than 30 minutes, the *Anchor Divergence* sensor turns on and a warning
is logged. The model itself is never modified.

## Rate budget

Each poll performs three read-only GETs (balance, 24h usage, 7d usage). At
the default 300 s interval that is **0.6 requests/minute** against the
documented 10 requests/minute cap (shared across the account's API keys) —
comfortable even with multiple accounts. If the server rate-limits you, the
integration honors the `Retry-After` header exactly.

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

> ℹ️ A **403** (account suspended, or team scope requested without team admin
> access) is different: the key is still valid, so no reauth is triggered —
> the sensors simply report unavailable with a suspension message in the
> logs.

## Disclaimer

This integration is not affiliated with or endorsed by Ollama. It reads the
documented balance and usage endpoints (`https://ollama.com/api/balance`,
`https://ollama.com/api/usage`) with your API key. Response shapes are
handled tolerantly, but Ollama may change them without notice. It performs
read-only `GET`s per poll — nothing else is ever sent to ollama.com.

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
