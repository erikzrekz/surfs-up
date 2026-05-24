"""Daylight indicator: classify a moment as dark / dawn / daylight / last-light.

Uses sunrise/sunset from Open-Meteo. Dawn and last-light are the 45-minute
windows on either side of usable light.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/New_York")
EDGE_MINUTES = 45  # dawn / dusk window on either side of sunrise / sunset


@dataclass(frozen=True)
class DaylightVerdict:
    status: str   # dawn | day | dusk | night
    emoji: str
    label: str
    note: str
    sunrise_local: str | None
    sunset_local: str | None


def _fmt_local(t: datetime | None) -> str | None:
    if t is None:
        return None
    return t.astimezone(LOCAL_TZ).strftime("%-I:%M %p")


def _fmt_mins(mins: float) -> str:
    m = int(round(mins))
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}"


def evaluate_daylight(
    now_utc: datetime,
    sunrises_utc: list[datetime],
    sunsets_utc: list[datetime],
) -> DaylightVerdict | None:
    """Timezone-agnostic. Sorts all sun events, finds the most-recent past one
    and the next future one, and infers state from there.
    """
    if not sunrises_utc and not sunsets_utc:
        return None

    events = sorted(
        [(t, "rise") for t in sunrises_utc] + [(t, "set") for t in sunsets_utc]
    )
    past = [(t, k) for t, k in events if t <= now_utc]
    future = [(t, k) for t, k in events if t > now_utc]
    last = past[-1] if past else None
    nxt = future[0] if future else None

    # Used for the static sunrise/sunset of today's NY date.
    local_today = now_utc.astimezone(LOCAL_TZ).date()
    today_rise = next(
        (s for s in sunrises_utc if s.astimezone(LOCAL_TZ).date() == local_today),
        None,
    )
    today_set = next(
        (s for s in sunsets_utc if s.astimezone(LOCAL_TZ).date() == local_today),
        None,
    )
    sunrise_str = _fmt_local(today_rise)
    sunset_str = _fmt_local(today_set)

    in_day = last is not None and last[1] == "rise"

    if in_day:
        mins_since_rise = (now_utc - last[0]).total_seconds() / 60
        mins_to_set = (nxt[0] - now_utc).total_seconds() / 60 if nxt else None
        if mins_since_rise < EDGE_MINUTES:
            return DaylightVerdict(
                "dawn", "🌅", "Dawn patrol",
                f"Sunrise was {_fmt_mins(mins_since_rise)} ago — golden hour",
                sunrise_str, sunset_str,
            )
        if mins_to_set is not None and mins_to_set < EDGE_MINUTES:
            return DaylightVerdict(
                "dusk", "🌇", "Last light",
                f"Sunset in {_fmt_mins(mins_to_set)} — burn-rate session",
                sunrise_str, sunset_str,
            )
        return DaylightVerdict(
            "day", "☀️", "Daylight",
            f"Sunset {sunset_str}" if sunset_str else "Daylight",
            sunrise_str, sunset_str,
        )

    # Night: either no past events, or last past was a sunset.
    if nxt is not None and nxt[1] == "rise":
        mins = (nxt[0] - now_utc).total_seconds() / 60
        return DaylightVerdict(
            "night", "🌙", "Dark",
            f"Sunrise in {_fmt_mins(mins)} ({_fmt_local(nxt[0])})",
            sunrise_str, sunset_str,
        )
    return DaylightVerdict(
        "night", "🌙", "Dark",
        "Past sunset",
        sunrise_str, sunset_str,
    )
