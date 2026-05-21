"""Open-Meteo Marine + Forecast API client.

Returns aligned hourly arrays for RI south-shore midpoint, next 72h:
- swell_wave_height (m)
- swell_wave_period (s)
- swell_wave_direction (deg)
- wave_height (m)
- wind_speed_10m (m/s)
- wind_direction_10m (deg)
- timestamps (UTC)
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


# RI south-shore midpoint, roughly off Matunuck. Open-Meteo snaps to nearest grid.
DEFAULT_LAT = 41.30
DEFAULT_LON = -71.50

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def current_wind(fc: "HourlyForecast", now_utc: datetime) -> tuple[float | None, float | None]:
    """Pick the forecast hour closest to (and not after) `now_utc`.

    Returns (wind_speed_ms, wind_dir_deg) or (None, None) if no usable hour.
    """
    best_i = None
    for i, t in enumerate(fc.times_utc):
        if t <= now_utc:
            best_i = i
        else:
            break
    if best_i is None and fc.times_utc:
        best_i = 0
    if best_i is None:
        return None, None
    return fc.wind_speed_ms[best_i], fc.wind_dir_deg[best_i]


@dataclass
class HourlyForecast:
    times_utc: list[datetime]
    swell_height_m: list[float | None]
    swell_period_s: list[float | None]
    swell_dir_deg: list[float | None]
    wave_height_m: list[float | None]
    wind_speed_ms: list[float | None]
    wind_dir_deg: list[float | None]
    lat: float
    lon: float


def _http_json(url: str, params: dict, timeout: float = 30.0) -> dict:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    with urllib.request.urlopen(full, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_times(times: list[str]) -> list[datetime]:
    out: list[datetime] = []
    for t in times:
        # Open-Meteo returns "2026-05-21T18:00" in requested timezone (UTC here)
        out.append(datetime.fromisoformat(t).replace(tzinfo=timezone.utc))
    return out


def fetch_forecast(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    hours: int = 72,
) -> HourlyForecast:
    marine = _http_json(MARINE_URL, {
        "latitude": lat,
        "longitude": lon,
        "hourly": "swell_wave_height,swell_wave_period,swell_wave_direction,wave_height",
        "timezone": "UTC",
        "forecast_days": max(2, (hours + 23) // 24),
    })
    weather = _http_json(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_days": max(2, (hours + 23) // 24),
    })

    m_hourly = marine.get("hourly", {})
    w_hourly = weather.get("hourly", {})

    m_times = _parse_times(m_hourly.get("time", []))
    w_times = _parse_times(w_hourly.get("time", []))

    # Align by timestamp; trim to first `hours` entries of marine times that
    # also exist in weather.
    w_index = {t: i for i, t in enumerate(w_times)}

    times: list[datetime] = []
    sh, sp, sd, wh, ws, wd = [], [], [], [], [], []
    for i, t in enumerate(m_times[:hours]):
        wi = w_index.get(t)
        if wi is None:
            continue
        times.append(t)
        sh.append(m_hourly["swell_wave_height"][i])
        sp.append(m_hourly["swell_wave_period"][i])
        sd.append(m_hourly["swell_wave_direction"][i])
        wh.append(m_hourly["wave_height"][i])
        ws.append(w_hourly["wind_speed_10m"][wi])
        wd.append(w_hourly["wind_direction_10m"][wi])

    return HourlyForecast(
        times_utc=times,
        swell_height_m=sh,
        swell_period_s=sp,
        swell_dir_deg=sd,
        wave_height_m=wh,
        wind_speed_ms=ws,
        wind_dir_deg=wd,
        lat=marine.get("latitude", lat),
        lon=marine.get("longitude", lon),
    )
