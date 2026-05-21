# Rory Surf Alerts

Tells you when the surf will be good on the Rhode Island coast, before it happens.

Two alert types:

- **Forecast heads-up** — "Sat 11am–3pm looks like 4ft @ 11s with NW wind." Fires when Open-Meteo's marine + wind forecast first shows a good window in the next 72 hours.
- **Go-now** — "It's firing right now at buoy 44097." Fires when NDBC observations cross the surf-quality bar in real time.

Runs entirely on GitHub Actions (free), no servers.

## Architecture

```
NDBC buoy 44097 ──┐
                  ├─► rules engine ─► AgentMail (email) + ntfy.sh (push)
Open-Meteo Marine ┘                    │
+ wind 10m                             └─► docs/data.json (static frontend)
```

- `scripts/check_surf.py` — runs every 15 min via Actions cron
- `scripts/rules.py` — thresholds + window detection (see "Tuning" below)
- `scripts/ndbc.py` — buoy 44097 RSS parser (wave-only buoy; wind comes from Open-Meteo)
- `scripts/open_meteo.py` — marine + wind forecast client
- `scripts/notify.py` — AgentMail + ntfy senders
- `state.json` — debounce state, committed back to repo each tick
- `docs/` — static frontend reading `docs/data.json`

## Setup

### 1. GitHub repo

Push this repo to GitHub. The workflow `.github/workflows/surf-alerts.yml` runs every 15 minutes once the repo has Actions enabled.

### 2. Secrets (repo Settings → Secrets and variables → Actions)

| Name | Value |
|---|---|
| `AGENTMAIL_API_KEY` | Your AgentMail bearer token |
| `AGENTMAIL_INBOX_ID` | Inbox to send from |
| `NTFY_TOPIC` | A hard-to-guess topic like `rory-surf-alerts-ri-7g4kq` |

### 3. Variables (same screen, "Variables" tab)

| Name | Value |
|---|---|
| `ALERT_TO` | Comma-separated email list, e.g. `eriksreks@gmail.com,rory@...` |

### 4. Subscribe to push

1. Install the [ntfy app](https://ntfy.sh) on your phone (iOS / Android).
2. Add the topic — same string as the `NTFY_TOPIC` secret.
3. Share that topic name with friends who want alerts. (Don't post it publicly — anyone with the topic can subscribe.)

### 5. Frontend (optional)

Publish `docs/` via the `here-now` skill or any static host. It will show the current buoy reading and the next forecast window.

## Tuning

All thresholds live in `scripts/rules.py` under `THRESHOLDS`. Each is overridable via env var in the workflow:

| Threshold | Default | Env var |
|---|---|---|
| Nowcast min wave height | 3.0 ft | `NOW_WVHT_FT_MIN` |
| Nowcast min dominant period | 9.0 s | `NOW_DPD_S_MIN` |
| Nowcast max wind (onshore-tolerated) | 15 kt | `NOW_WIND_KT_MAX` |
| Nowcast max wind (offshore) | 25 kt | `NOW_OFFSHORE_KT_MAX` |
| Forecast min swell height | 0.9 m | `FC_SWELL_M_MIN` |
| Forecast min swell period | 9.0 s | `FC_PERIOD_S_MIN` |
| Forecast max wind | 7 m/s (~13 kt) | `FC_WIND_MS_MAX` |
| Forecast min window length | 3 h | `FC_MIN_WINDOW_H` |
| Daylight start (local) | 06:00 | `FC_DAYLIGHT_START_H` |
| Daylight end (local) | 18:00 | `FC_DAYLIGHT_END_H` |

After a few weeks of real alerts, the most likely tune is bumping `NOW_DPD_S_MIN` from 9 to 10 if you get noisy weather-window alerts.

## Local testing

```bash
# Unit tests
python -m unittest tests.test_rules -v

# Dry-run against live APIs (no emails sent)
DRY_RUN=1 python scripts/check_surf.py
cat docs/data.json
```

## Notes

- Buoy 44097 (Block Island) is wave-only — no wind sensor. The script pulls current wind from the Open-Meteo forecast grid at the nowcast moment.
- GitHub Actions cron is best-effort — 15-min intervals slip to 20–30 min under load. Fine for surf, which evolves over hours.
- The script is generic across RI breaks; it doesn't try to predict south-shore vs Newport vs Block Island specifically. Add `swell_wave_direction` gating in `rules.py` if you want to narrow.
- Tide isn't considered yet. NOAA CO-OPS station 8452660 (Newport) is the natural next addition.
