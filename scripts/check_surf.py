#!/usr/bin/env python3
"""Main runner: fetch nowcast + forecast, evaluate, alert, write docs/data.json.

Designed for GitHub Actions cron. Idempotent: if no alert conditions change,
no notifications fire. State is read from and written to STATE_PATH so the
workflow can commit it back to the repo.

Exit code 0 on success. Non-zero only on hard fetch failures.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ndbc
import open_meteo
import rules
import state as state_mod
from notify import notify_all


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = Path(os.environ.get("STATE_PATH", REPO_ROOT / "state.json"))
DATA_PATH = Path(os.environ.get("DATA_PATH", REPO_ROOT / "docs" / "data.json"))

STALE_NOWCAST_MAX_AGE = timedelta(hours=3)
NOWCAST_SAME_DAY_UTC_CAP = True
FORECAST_NEAR_TERM_SUPPRESS_H = 3


def _ms_to_kt(v: float | None) -> float | None:
    return None if v is None else round(v * 1.94384, 1)


def _m_to_ft(v: float | None) -> float | None:
    return None if v is None else round(v * 3.28084, 1)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run() -> int:
    now_utc = datetime.now(timezone.utc)
    state = state_mod.load_state(STATE_PATH)
    new_state = dict(state)

    # ---- Forecast (also provides current-hour wind for the wave-only buoy) ----
    forecast_payload: dict | None = None
    next_win = None
    fc = None
    try:
        fc = open_meteo.fetch_forecast(hours=120)
        windows = rules.find_forecast_windows(fc)
        next_win = rules.next_window(windows, now_utc)

        def serialize_window(w):
            return {
                "start_utc": w.start_utc.isoformat(),
                "end_utc": w.end_utc.isoformat(),
                "start_local": w.start_local.isoformat(),
                "end_local": w.end_local.isoformat(),
                "duration_h": w.duration_h,
                "peak_swell_ft": _m_to_ft(w.peak_swell_m),
                "peak_period_s": round(w.peak_period_s, 1),
                "peak_wind_kt": _ms_to_kt(w.peak_wind_ms),
                "wind_dir": ndbc.deg_to_compass(w.representative_wind_dir_deg),
                "id": w.id_hash(),
                "score": round(w.score, 2),
                "tier": w.tier,
            }

        forecast_payload = {
            "lat": fc.lat,
            "lon": fc.lon,
            "next_window": serialize_window(next_win) if next_win else None,
            "all_windows_72h": [serialize_window(w) for w in windows],
        }
        if next_win:
            print(f"forecast next={next_win.start_local.isoformat()} "
                  f"dur={next_win.duration_h}h swell={next_win.peak_swell_m:.1f}m "
                  f"period={next_win.peak_period_s:.1f}s")
        else:
            print("forecast no_windows_72h")
    except Exception as e:
        print(f"forecast-error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    # ---- Nowcast (buoy 44097 waves + Open-Meteo wind) --------------------
    nowcast_payload: dict | None = None
    nowcast_is_good = False
    try:
        obs = ndbc.fetch_observation(station=44097)
        stale = (
            obs.observed_at is not None
            and (now_utc - obs.observed_at) > STALE_NOWCAST_MAX_AGE
        )
        if stale:
            print(f"nowcast=stale observed_at={obs.observed_at.isoformat()}")

        # 44097 has no wind sensor; pull current wind from the forecast grid.
        wind_kt = obs.wind_speed_kt
        wind_dir = obs.wind_dir_deg
        wind_source = "44097"
        if (wind_kt is None or wind_dir is None) and fc is not None:
            ws_ms, wd_deg = open_meteo.current_wind(fc, now_utc)
            if ws_ms is not None:
                wind_kt = round(ws_ms * 1.94384, 1)
            if wd_deg is not None:
                wind_dir = wd_deg
            wind_source = "open-meteo"

        verdict = rules.evaluate_nowcast(
            wvht_ft=obs.wvht_ft, dpd_s=obs.dpd_s,
            wind_speed_kt=wind_kt, wind_dir_deg=wind_dir,
        )
        nowcast_is_good = (not stale) and verdict.is_good
        nowcast_payload = {
            "station": obs.station,
            "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
            "wvht_ft": obs.wvht_ft,
            "dpd_s": obs.dpd_s,
            "apd_s": obs.apd_s,
            "swell_dir_deg": obs.swell_dir_deg,
            "swell_dir": ndbc.deg_to_compass(obs.swell_dir_deg),
            "wind_speed_kt": wind_kt,
            "wind_dir_deg": wind_dir,
            "wind_dir": ndbc.deg_to_compass(wind_dir),
            "wind_source": wind_source,
            "is_good": nowcast_is_good,
            "tier": verdict.tier,
            "stale": stale,
            "reasons": verdict.reasons,
            "source_url": obs.raw_url,
        }
        print(f"nowcast wvht={obs.wvht_ft} dpd={obs.dpd_s} "
              f"wind={wind_kt}kt@{wind_dir}° ({wind_source}) good={nowcast_is_good}")
    except Exception as e:
        print(f"nowcast-error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    # ---- Write docs/data.json --------------------------------------------
    data_payload = {
        "fetched_at": now_utc.isoformat(),
        "nowcast": nowcast_payload,
        "forecast": forecast_payload,
        "thresholds": rules.THRESHOLDS,
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(data_payload, f, indent=2, sort_keys=True)
        f.write("\n")

    # ---- Nowcast alert decision ------------------------------------------
    today = _today_utc()
    nowcast_was_good = bool(state.get("nowcast_was_good"))
    nowcast_last_day = state.get("nowcast_last_sent_day_utc")

    fire_nowcast = (
        nowcast_payload is not None
        and nowcast_is_good
        and not nowcast_was_good
        and not (NOWCAST_SAME_DAY_UTC_CAP and nowcast_last_day == today)
    )

    if fire_nowcast:
        n = nowcast_payload
        tier_label = "Clean small day" if n.get("tier") == "clean" else "Surf is firing"
        subject = f"🌊 {tier_label} at 44097 — {n['wvht_ft']}ft @ {n['dpd_s']}s"
        body = (
            f"Block Island buoy 44097 is showing surfable conditions right now.\n\n"
            f"• Wave height: {n['wvht_ft']} ft\n"
            f"• Dominant period: {n['dpd_s']} s (groundswell)\n"
            f"• Wind: {n['wind_speed_kt']} kt from {n['wind_dir']} ({n['wind_dir_deg']}°)\n\n"
            f"Source: {n['source_url']}\n"
            f"Observed: {n['observed_at']}\n"
        )
        result = notify_all(subject=subject, body=body, push_title="🌊 Go now — surf is up")
        print(f"alert-nowcast email={result.email_sent} push={result.push_sent} "
              f"email_err={result.email_error} push_err={result.push_error}")
        new_state["nowcast_last_sent_day_utc"] = today

    new_state["nowcast_was_good"] = nowcast_is_good

    # ---- Forecast alert decision -----------------------------------------
    last_win_id = state.get("forecast_last_window_id")
    last_win_score = state.get("forecast_last_window_score")

    fire_forecast = False
    if next_win is not None:
        starts_soon = (next_win.start_utc - now_utc) <= timedelta(hours=FORECAST_NEAR_TERM_SUPPRESS_H)
        if starts_soon:
            pass  # let nowcast handle it
        else:
            new_id = next_win.id_hash()
            if new_id != last_win_id:
                fire_forecast = True
            elif last_win_score is not None and next_win.score >= last_win_score * 1.3:
                fire_forecast = True  # window got materially better

    if fire_forecast and next_win is not None:
        local_start = next_win.start_local
        local_end = next_win.end_local
        swell_ft = _m_to_ft(next_win.peak_swell_m)
        wind_kt = _ms_to_kt(next_win.peak_wind_ms)
        wind_dir = ndbc.deg_to_compass(next_win.representative_wind_dir_deg)
        when = local_start.strftime("%a %b %d, %I:%M%p").lstrip("0")
        until = local_end.strftime("%I:%M%p").lstrip("0")
        tier_tag = "Clean day" if next_win.tier == "clean" else "Surf window"
        subject = f"🏄 {tier_tag} forecast {when}–{until} ({swell_ft}ft @ {next_win.peak_period_s:.0f}s)"
        body = (
            f"Open-Meteo is forecasting a good RI surf window:\n\n"
            f"• When: {when} – {until} ({next_win.duration_h}h)\n"
            f"• Swell: {swell_ft} ft @ {next_win.peak_period_s:.0f}s\n"
            f"• Wind: {wind_kt} kt {wind_dir}\n\n"
            f"You'll get a 'go now' alert once 44097 confirms.\n"
        )
        result = notify_all(subject=subject, body=body, push_title="🏄 Surf window incoming")
        print(f"alert-forecast email={result.email_sent} push={result.push_sent} "
              f"email_err={result.email_error} push_err={result.push_error}")
        new_state["forecast_last_window_id"] = next_win.id_hash()
        new_state["forecast_last_window_score"] = next_win.score
        new_state["forecast_last_sent_at"] = now_utc.isoformat()
    elif next_win is not None:
        new_state["forecast_last_window_id"] = next_win.id_hash()
        new_state["forecast_last_window_score"] = next_win.score
    else:
        new_state["forecast_last_window_id"] = None
        new_state["forecast_last_window_score"] = None

    state_mod.save_state(STATE_PATH, new_state)
    return 0


if __name__ == "__main__":
    sys.exit(run())
