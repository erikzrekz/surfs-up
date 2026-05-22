# Spec: LLM reasoning layer

Status: Drafted, not implemented. Pick this up when ready to add judgment + better-written alerts.

## Motivation

Today the cron evaluates buoy + forecast against hard-coded thresholds and, if they pass, sends a templated alert (`"Surf is firing at 44097 — 3.0ft @ 7.0s"`). That works, but it has two real limits a senior surfer would notice:

1. **No holistic judgment.** A passing window could be borderline (e.g., 3.0ft @ 7.0s with a SW wind about to build at noon) or genuinely standout (4ft @ 11s, NW wind, all-day window). Today the alert sounds the same.
2. **No weekly outlook.** The user has to read `data.json` themselves to know that Monday afternoon is the standout this week. The alerter only tells them when *one* window opens, not how the week shapes up.

An LLM reasoning step can fix both without replacing the deterministic trigger.

## Goals

- Better-written, context-aware alert text on existing trigger events.
- Optional veto: LLM can suppress an alert that the rules barely passed but it judges to be marginal.
- New "morning digest" delivery summarizing the next 5 days.
- Stay cheap (<$1/month) and reliable (fail-open to today's static messages).

## Non-goals

- LLM does not *fire* new alerts. Rules remain the trigger floor. Predictability of when you'll get pinged is more valuable than added cleverness.
- No real-time inference. We only invoke when an alert would fire (1–3×/day) and once per morning for the digest.
- No fine-tuning, no agents, no tool use. Single-shot generation with a structured JSON output.

## Architecture

Two independent pieces, both calling Anthropic's API directly. Both fail open.

### Piece 1: "Rules trigger, LLM authors"

Wired into `check_surf.py`. When the existing rule engine decides to fire (nowcast edge-trigger or forecast new-window), call `reason.compose_alert(context)` to produce subject/body. If the call fails or times out (>10s), fall back to the current static templates.

```
NDBC + Open-Meteo ─► rules engine ─► (fires?) ─► reason.compose_alert ─► notify.send
                                          │              │
                                          │              └─ fail open: static template
                                          │
                                          └─ (no) ─► no-op
```

### Piece 2: "Morning digest" (orthogonal new feature)

New workflow `.github/workflows/morning-digest.yml`. Cron at `0 10 * * *` (5am Eastern accounting for DST window of 9–10 UTC). Calls `scripts/digest.py` which:

1. Pulls Open-Meteo for the next 7 days (one extra day of buffer).
2. Calls `reason.compose_digest(forecast_7d, recent_alerts)`.
3. Sends one notification (push + email) regardless of whether windows exist — silence is fine if conditions are flat, the digest will say so.

Once per day. Cheap. Useful even when the alerter is otherwise quiet.

## Model & cost

- **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`). Fast (~1s typical), cheap, plenty smart for this task.
- **Prompt caching** on the system prompt + thresholds + station metadata (all static across runs). Pushes effective input cost down further.
- Expected per call: ~2k input tokens, ~300 output tokens.
- Expected calls/month: ~10 alert authoring + 30 daily digests = 40. At ~$0.003/call uncached, ~$0.002/call cached → **<$0.10/month total**.

If quality is unsatisfactory, easy upgrade path to **Claude Sonnet 4.6** (still cheap at this volume).

## LLM interface

### Input — `compose_alert(context)`

```jsonc
{
  "trigger": "nowcast" | "forecast",
  "now": {
    "wvht_ft": 3.0, "dpd_s": 7.0, "apd_s": 5.2,
    "wind_kt": 4.4, "wind_dir": "SSW", "wind_dir_deg": 195,
    "swell_dir": "S", "swell_dir_deg": 187,
    "tier_passed": "groundswell" | "clean" | null,
    "observed_at": "2026-05-21T20:50:00Z",
    "source_url": "..."
  },
  "next_window": { /* same shape as data.json's forecast.next_window, plus tier */ },
  "all_windows_120h": [ /* ... */ ],
  "trend": {
    "last_3h_wvht_ft": [3.2, 3.0, 3.0],
    "next_6h_wind_kt_dir": [[5, "SW"], [8, "SW"], ...]
  },
  "thresholds": { /* THRESHOLDS dict */ },
  "recent_alerts_sent": [
    { "sent_at": "...", "tier": "groundswell", "subject": "...", "outcome": "user-rated?" }
  ]
}
```

### Output

```jsonc
{
  "should_send": true,
  "priority": "high" | "medium" | "low",
  "subject": "Short subject — < 80 chars",
  "body": "2–5 short paragraphs of plain text. Surf vocab OK. No emojis unless the user opts in.",
  "reasoning": "1–3 sentences for the log; never shown to user"
}
```

`should_send=false` is the soft-veto path. Defaults to `true` if the LLM call fails.

### Input — `compose_digest(forecast_7d, recent_alerts)`

```jsonc
{
  "today_local": "2026-05-22",
  "days": [
    {
      "date": "2026-05-22", "weekday": "Fri",
      "daylight_hourly": [ { "hour": "06", "swell_ft": ..., "period_s": ..., "wind_kt": ..., "wind_dir": "..." }, ... ],
      "good_windows": [ /* same shape, may be empty */ ],
      "summary_stats": { "max_swell_ft": 3.2, "max_period_s": 6, "min_wind_kt": 4 }
    },
    /* ... 5–7 entries ... */
  ],
  "recent_alerts_sent": [ /* last 5 days */ ]
}
```

### Output — digest

```jsonc
{
  "subject": "Surf week — Mon stands out, otherwise quiet",
  "body": "Single message, ≤ 400 words. Lead with the standout day if any. Note what's likely to change in the forecast vs. what's stable. Be honest about marginal calls.",
  "tldr": "One-line summary suitable for the push notification (≤ 80 chars)",
  "reasoning": "..."
}
```

## Prompt design

System prompt (cached):

> You are a senior Rhode Island surfer reviewing buoy and model data. Be honest, concise, and grounded. Use surf vocabulary naturally (groundswell, wind swell, clean, blown out, dawn patrol) but never hype marginal conditions. Prefer practical statements ("better to go before noon, SW wind builds after") over generic ones ("conditions look favorable"). Output only the JSON object specified in the user message.

User prompt body: the JSON context above, followed by a short instruction restating the schema.

Notes:
- Lock the model to JSON output via `response_format` or by explicit instruction + a parse-retry-on-failure loop.
- Always include the `thresholds` so the LLM can reason about *why* the rules triggered.
- Include `recent_alerts_sent` so it can avoid repetition and recognize a multi-day pattern.

## Failure modes & fail-open

1. **API down / timeout (>10s)** → log + use the current static subject/body. Send.
2. **JSON parse failure** → log raw output + use static. Send.
3. **`should_send=false`** → log reasoning + skip the notify call. Persist state as if sent (so the edge-trigger doesn't re-fire next minute). Exception: never let the LLM suppress two consecutive alerts of the same tier — fail to send anyway.
4. **API key missing** → skip the reasoning step entirely. Static path only. No error.

The user must never miss an alert because the LLM had a bad day.

## Implementation plan

When picking this up:

1. **`scripts/reason.py`** — Anthropic SDK client, two functions `compose_alert(ctx)` and `compose_digest(ctx)`. Prompt caching enabled on the system prompt. 10s timeout. Returns the structured dict.
2. **Wire into `check_surf.py`** at the two `fire_*` branches. Build `ctx` from existing `nowcast_payload`, `forecast_payload`, plus a slice of recent alert history (read from `state.json`, persist to it).
3. **`scripts/digest.py`** — separate entrypoint. Fetches 7d forecast, calls `compose_digest`, sends via `notify.notify_all`.
4. **`.github/workflows/morning-digest.yml`** — `cron: "0 10 * * *"` (5–6am ET depending on DST). Same secrets pattern as `surf-alerts.yml`. No state to commit (digest is fire-and-forget).
5. **New secret**: `ANTHROPIC_API_KEY` in repo secrets.
6. **State changes** in `state.json`:
   - `recent_alerts_sent`: ring buffer of last ~10 alerts (sent_at, tier, subject)
   - `last_digest_sent_day_local`: prevents double-digest if the morning workflow gets retried
7. **Tests**:
   - Mock the Anthropic client; verify fail-open paths
   - Verify `should_send=false` is respected once but not twice in a row
   - Verify digest is sent at most once per local day

Use the `claude-api` skill when implementing — it enforces prompt caching, current model IDs, and timeout patterns.

## Open questions

- **Tone control**: should the LLM be allowed to use emojis in the body, or never? Current alerts use one leading emoji in the subject. Lean: keep that, no emoji in body. Revisit after we see real output.
- **User feedback loop**: nice-to-have eventually. A "rate this session" link in each alert, results piped back into `recent_alerts_sent.outcome`, LLM learns calibration over time. Out of scope for v1.
- **Suppression bound**: should `should_send=false` count against the daily cap? Lean: no (a vetoed alert is still informational — but logging-only). Document the choice in code.
- **Multi-user**: the prompt currently assumes a single audience (you and friends in RI). If the alerter ever covers more people or other coasts, persona prompt needs parameterization.

## Future extensions (post-v1)

- **Comparative reasoning** in alerts: "This Monday is better than the last 14 days; comparable to the Oct 12 session." Requires a longer history log.
- **Tide integration** (NOAA CO-OPS station 8452660 Newport) added to LLM context — many RI breaks are tide-sensitive and the LLM can speak to that better than rigid rules.
- **Per-break tuning**: a profile for "south shore", "Newport", "Block Island", each with their own swell-direction preferences; LLM picks which break(s) to mention.
- **Photo/cam integration**: if a public webcam URL exists for a spot, link it in alerts.
