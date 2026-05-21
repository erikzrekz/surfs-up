"""Tiny JSON state store. Committed back to the repo by the workflow."""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_STATE = {
    "nowcast_was_good": False,
    "nowcast_last_sent_day_utc": None,
    "forecast_last_window_id": None,
    "forecast_last_window_score": None,
    "forecast_last_sent_at": None,
}


def load_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return dict(DEFAULT_STATE)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)
    return {**DEFAULT_STATE, **data}


def save_state(path: str | Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, p)
