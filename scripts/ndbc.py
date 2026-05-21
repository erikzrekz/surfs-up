"""Fetch and parse NDBC buoy observations (station 44097, Block Island).

The latest_obs RSS feed is a small HTML-in-XML blob. We pull a handful of
fields with tolerant regex: WVHT (significant wave height), DPD (dominant
period), APD (average period), wind speed and direction.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


RSS_URL_TEMPLATE = "https://www.ndbc.noaa.gov/data/latest_obs/{station}.rss"


@dataclass
class BuoyObs:
    station: int
    wvht_ft: float | None
    dpd_s: float | None
    apd_s: float | None
    swell_dir_deg: float | None  # "Mean Wave Direction" from RSS
    wind_speed_kt: float | None  # Often None for wave-only buoys like 44097
    wind_dir_deg: float | None
    observed_at: datetime | None
    raw_url: str


_NUM = r"([0-9]+(?:\.[0-9]+)?)"


def _find_near(text: str, term: str, pattern: str) -> str | None:
    lo = text.lower()
    idx = lo.find(term.lower())
    if idx < 0:
        return None
    tail = text[idx : idx + 1500]
    m = re.search(pattern, tail, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ft_from_meters(m: float | None) -> float | None:
    return None if m is None else round(m * 3.28084, 2)


def _kt_from_knots_or_ms(value: float | None, unit_hint: str | None) -> float | None:
    if value is None:
        return None
    if unit_hint and "m/s" in unit_hint.lower():
        return round(value * 1.94384, 1)
    return round(value, 1)


# Compass abbreviation -> degrees (where the wind is coming FROM)
_COMPASS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def _dir_deg(text: str, term: str) -> float | None:
    # Tries "Term: ABBR (123°)" first, then "Term: 123°", then "Term: ABBR".
    after = _find_near(text, term, r":\s*[A-Z]{1,3}\s*\(\s*" + _NUM + r"\s*(?:&#176;|&deg;|°)")
    if after:
        return _to_float(after)
    after = _find_near(text, term, _NUM + r"\s*(?:&#176;|&deg;|°)")
    if after:
        return _to_float(after)
    abbr = _find_near(text, term, r":\s*([NSEW]{1,3})\b")
    if abbr and abbr.upper() in _COMPASS:
        return float(_COMPASS[abbr.upper()])
    return None


def _observed_at(text: str) -> datetime | None:
    # NDBC RSS sometimes has <pubDate> in RFC822 form
    m = re.search(r"<pubDate>([^<]+)</pubDate>", text)
    if not m:
        return None
    raw = m.group(1).strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def fetch_observation(station: int = 44097, timeout: float = 30.0) -> BuoyObs:
    url = RSS_URL_TEMPLATE.format(station=station)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return parse_observation(text, station=station, raw_url=url)


def parse_observation(text: str, station: int, raw_url: str) -> BuoyObs:
    wvht_m = _to_float(_find_near(text, "wave height", _NUM + r"\s*m\b"))
    wvht_ft_direct = _to_float(_find_near(text, "wave height", _NUM + r"\s*ft\b"))
    wvht_ft = wvht_ft_direct if wvht_ft_direct is not None else _ft_from_meters(wvht_m)

    dpd_s = _to_float(_find_near(text, "dominant wave period", _NUM + r"\s*sec"))
    apd_s = _to_float(_find_near(text, "average period", _NUM + r"\s*sec"))

    wind_kt_direct = _to_float(_find_near(text, "wind speed", _NUM + r"\s*kt\b"))
    wind_ms = _to_float(_find_near(text, "wind speed", _NUM + r"\s*m/s\b"))
    wind_kt = wind_kt_direct if wind_kt_direct is not None else _kt_from_knots_or_ms(wind_ms, "m/s")

    return BuoyObs(
        station=station,
        wvht_ft=wvht_ft,
        dpd_s=dpd_s,
        apd_s=apd_s,
        swell_dir_deg=_dir_deg(text, "mean wave direction"),
        wind_speed_kt=wind_kt,
        wind_dir_deg=_dir_deg(text, "wind direction"),
        observed_at=_observed_at(text),
        raw_url=raw_url,
    )


def deg_to_compass(deg: float | None) -> str | None:
    if deg is None:
        return None
    ix = int((deg % 360) / 22.5 + 0.5) % 16
    return [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ][ix]
