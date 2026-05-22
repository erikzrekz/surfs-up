"""Surf-quality rules for RI coast.

Generic, not break-specific. Tunable from one place.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from open_meteo import HourlyForecast


LOCAL_TZ = ZoneInfo("America/New_York")


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v else default
    except ValueError:
        return default


THRESHOLDS = {
    # Tier A — "groundswell" (loud, classic surf-up alert).
    # Nowcast (NDBC 44097)
    "now_wvht_ft":      _env_float("NOW_WVHT_FT_MIN", 3.0),
    "now_dpd_s":        _env_float("NOW_DPD_S_MIN", 7.0),
    "now_wind_kt_max":  _env_float("NOW_WIND_KT_MAX", 15.0),
    "now_offshore_kt_max": _env_float("NOW_OFFSHORE_KT_MAX", 25.0),
    # Forecast
    "fc_swell_m":       _env_float("FC_SWELL_M_MIN", 0.9),
    "fc_period_s":      _env_float("FC_PERIOD_S_MIN", 7.0),
    "fc_wind_ms_max":   _env_float("FC_WIND_MS_MAX", 7.0),
    "fc_offshore_ms_max": _env_float("FC_OFFSHORE_MS_MAX", 11.0),

    # Tier B — "clean small day" (RI summer windswell with light offshore).
    # Lower period bar, but requires strictly low wind AND offshore direction.
    "clean_wvht_ft":     _env_float("CLEAN_WVHT_FT_MIN", 3.0),
    "clean_dpd_s":       _env_float("CLEAN_DPD_S_MIN", 5.0),
    "clean_wind_kt_max": _env_float("CLEAN_WIND_KT_MAX", 6.0),
    "clean_swell_m":     _env_float("CLEAN_SWELL_M_MIN", 0.9),   # ~3.0ft
    "clean_period_s":    _env_float("CLEAN_PERIOD_S_MIN", 5.0),
    "clean_wind_ms_max": _env_float("CLEAN_WIND_MS_MAX", 3.0),   # ~6kt

    # Shared
    "fc_min_window_h":  _env_float("FC_MIN_WINDOW_H", 3),
    "fc_daylight_start_h": _env_float("FC_DAYLIGHT_START_H", 6),
    "fc_daylight_end_h":   _env_float("FC_DAYLIGHT_END_H", 18),
}


def is_offshore(wind_dir_deg: float | None) -> bool:
    """North quadrant: 270° (W) round through 0° to 90° (E).

    True for N, NE, NW and anything west-of-N or east-of-N.
    Includes pure W (270) and pure E (90) inclusively.
    """
    if wind_dir_deg is None:
        return False
    d = wind_dir_deg % 360
    return d >= 270 or d <= 90


@dataclass
class NowcastVerdict:
    is_good: bool
    tier: str | None     # "groundswell" | "clean" | None
    reasons: list[str]


def _nowcast_groundswell(wvht_ft, dpd_s, wind_speed_kt, wind_dir_deg):
    """Tier A — groundswell rule. Returns (passes, failure_reasons)."""
    t = THRESHOLDS
    reasons = []
    if wvht_ft is None or wvht_ft < t["now_wvht_ft"]:
        reasons.append(f"WVHT {wvht_ft} < {t['now_wvht_ft']}ft")
    if dpd_s is None or dpd_s < t["now_dpd_s"]:
        reasons.append(f"DPD {dpd_s} < {t['now_dpd_s']}s")
    wind_ok = False
    if wind_speed_kt is not None:
        if wind_speed_kt <= t["now_wind_kt_max"]:
            wind_ok = True
        elif is_offshore(wind_dir_deg) and wind_speed_kt <= t["now_offshore_kt_max"]:
            wind_ok = True
    if not wind_ok:
        reasons.append(
            f"wind {wind_speed_kt}kt @ {wind_dir_deg}° "
            f"(need ≤{t['now_wind_kt_max']}kt or offshore ≤{t['now_offshore_kt_max']}kt)"
        )
    return (not reasons), reasons


def _nowcast_clean(wvht_ft, dpd_s, wind_speed_kt, wind_dir_deg):
    """Tier B — clean small day. Requires strictly low offshore wind."""
    t = THRESHOLDS
    reasons = []
    if wvht_ft is None or wvht_ft < t["clean_wvht_ft"]:
        reasons.append(f"WVHT {wvht_ft} < {t['clean_wvht_ft']}ft")
    if dpd_s is None or dpd_s < t["clean_dpd_s"]:
        reasons.append(f"DPD {dpd_s} < {t['clean_dpd_s']}s")
    if (wind_speed_kt is None
            or wind_speed_kt > t["clean_wind_kt_max"]
            or not is_offshore(wind_dir_deg)):
        reasons.append(
            f"wind {wind_speed_kt}kt @ {wind_dir_deg}° "
            f"(need ≤{t['clean_wind_kt_max']}kt AND offshore)"
        )
    return (not reasons), reasons


def evaluate_nowcast(
    wvht_ft: float | None,
    dpd_s: float | None,
    wind_speed_kt: float | None,
    wind_dir_deg: float | None,
) -> NowcastVerdict:
    a_ok, a_reasons = _nowcast_groundswell(wvht_ft, dpd_s, wind_speed_kt, wind_dir_deg)
    if a_ok:
        return NowcastVerdict(is_good=True, tier="groundswell", reasons=[])
    b_ok, b_reasons = _nowcast_clean(wvht_ft, dpd_s, wind_speed_kt, wind_dir_deg)
    if b_ok:
        return NowcastVerdict(is_good=True, tier="clean", reasons=[])
    # Report whichever tier was closest to passing
    return NowcastVerdict(is_good=False, tier=None, reasons=a_reasons)


@dataclass
class ForecastWindow:
    start_utc: datetime
    end_utc: datetime
    duration_h: int
    peak_swell_m: float
    peak_period_s: float
    peak_wind_ms: float
    representative_wind_dir_deg: float
    score: float  # rough quality score for re-alert deciding
    tier: str  # "groundswell" | "clean"

    @property
    def start_local(self) -> datetime:
        return self.start_utc.astimezone(LOCAL_TZ)

    @property
    def end_local(self) -> datetime:
        return self.end_utc.astimezone(LOCAL_TZ)

    def id_hash(self) -> str:
        s = f"{self.start_utc.isoformat()}|{self.duration_h}"
        return hashlib.sha256(s.encode()).hexdigest()[:12]


def _hour_passes_groundswell(swell_m, period_s, wind_ms, wind_dir) -> bool:
    t = THRESHOLDS
    if swell_m < t["fc_swell_m"]: return False
    if period_s < t["fc_period_s"]: return False
    if wind_ms <= t["fc_wind_ms_max"]: return True
    if is_offshore(wind_dir) and wind_ms <= t["fc_offshore_ms_max"]: return True
    return False


def _hour_passes_clean(swell_m, period_s, wind_ms, wind_dir) -> bool:
    t = THRESHOLDS
    if swell_m < t["clean_swell_m"]: return False
    if period_s < t["clean_period_s"]: return False
    if wind_ms > t["clean_wind_ms_max"]: return False
    if not is_offshore(wind_dir): return False
    return True


def _hour_is_good(
    swell_m: float | None,
    period_s: float | None,
    wind_ms: float | None,
    wind_dir: float | None,
    local_hour: int,
) -> tuple[bool, str | None]:
    t = THRESHOLDS
    if local_hour < t["fc_daylight_start_h"] or local_hour > t["fc_daylight_end_h"]:
        return False, None
    if swell_m is None or period_s is None or wind_ms is None:
        return False, None
    if _hour_passes_groundswell(swell_m, period_s, wind_ms, wind_dir):
        return True, "groundswell"
    if _hour_passes_clean(swell_m, period_s, wind_ms, wind_dir):
        return True, "clean"
    return False, None


def find_forecast_windows(fc: HourlyForecast) -> list[ForecastWindow]:
    """Find runs of ≥ fc_min_window_h consecutive good daylight-local hours."""
    t = THRESHOLDS
    min_h = int(t["fc_min_window_h"])

    flags: list[bool] = []
    tiers: list[str | None] = []
    for i, ts_utc in enumerate(fc.times_utc):
        local_hour = ts_utc.astimezone(LOCAL_TZ).hour
        ok, tier = _hour_is_good(
            fc.swell_height_m[i], fc.swell_period_s[i],
            fc.wind_speed_ms[i], fc.wind_dir_deg[i],
            local_hour,
        )
        flags.append(ok)
        tiers.append(tier)

    windows: list[ForecastWindow] = []
    i = 0
    n = len(flags)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < n and flags[j]:
            j += 1
        if j - i >= min_h:
            peak_swell = max(fc.swell_height_m[i:j])
            peak_period = max(fc.swell_period_s[i:j])
            peak_wind = max(fc.wind_speed_ms[i:j])
            mid = (i + j) // 2
            rep_wind_dir = fc.wind_dir_deg[mid] or 0.0
            duration_h = j - i
            # Groundswell wins over clean if any hour in the window passes A
            window_tier = "groundswell" if "groundswell" in tiers[i:j] else "clean"
            score = peak_swell * peak_period * duration_h
            windows.append(ForecastWindow(
                start_utc=fc.times_utc[i],
                end_utc=fc.times_utc[j - 1] + timedelta(hours=1),
                duration_h=duration_h,
                peak_swell_m=peak_swell,
                peak_period_s=peak_period,
                peak_wind_ms=peak_wind,
                representative_wind_dir_deg=rep_wind_dir,
                score=score,
                tier=window_tier,
            ))
        i = j
    return windows


def next_window(windows: list[ForecastWindow], now_utc: datetime | None = None) -> ForecastWindow | None:
    now_utc = now_utc or datetime.now(timezone.utc)
    future = [w for w in windows if w.end_utc > now_utc]
    return future[0] if future else None
