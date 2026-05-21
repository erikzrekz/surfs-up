"""Smoke tests for the rules engine. Run with: python -m unittest tests.test_rules"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import rules  # noqa: E402
from open_meteo import HourlyForecast  # noqa: E402


def _hourly(n: int, swell_m, period_s, wind_ms, wind_dir, start_utc=None):
    start = start_utc or datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)  # 10am EDT
    times = [start + timedelta(hours=i) for i in range(n)]
    return HourlyForecast(
        times_utc=times,
        swell_height_m=[swell_m] * n,
        swell_period_s=[period_s] * n,
        swell_dir_deg=[180.0] * n,
        wave_height_m=[swell_m] * n,
        wind_speed_ms=[wind_ms] * n,
        wind_dir_deg=[wind_dir] * n,
        lat=41.3, lon=-71.5,
    )


class NowcastTests(unittest.TestCase):
    def test_good(self):
        v = rules.evaluate_nowcast(wvht_ft=4.0, dpd_s=11, wind_speed_kt=8, wind_dir_deg=315)
        self.assertTrue(v.is_good, v.reasons)

    def test_low_period_fails(self):
        v = rules.evaluate_nowcast(wvht_ft=4.0, dpd_s=7, wind_speed_kt=8, wind_dir_deg=315)
        self.assertFalse(v.is_good)

    def test_low_height_fails(self):
        v = rules.evaluate_nowcast(wvht_ft=1.0, dpd_s=11, wind_speed_kt=8, wind_dir_deg=315)
        self.assertFalse(v.is_good)

    def test_strong_onshore_fails(self):
        v = rules.evaluate_nowcast(wvht_ft=4.0, dpd_s=11, wind_speed_kt=22, wind_dir_deg=180)
        self.assertFalse(v.is_good)

    def test_strong_offshore_ok(self):
        v = rules.evaluate_nowcast(wvht_ft=4.0, dpd_s=11, wind_speed_kt=22, wind_dir_deg=315)
        self.assertTrue(v.is_good, v.reasons)


class ForecastTests(unittest.TestCase):
    def test_finds_good_daylight_window(self):
        fc = _hourly(12, swell_m=1.2, period_s=11, wind_ms=4, wind_dir=315)
        windows = rules.find_forecast_windows(fc)
        self.assertGreaterEqual(len(windows), 1)
        self.assertGreaterEqual(windows[0].duration_h, 3)

    def test_skips_short_periods(self):
        fc = _hourly(12, swell_m=1.2, period_s=6, wind_ms=4, wind_dir=315)
        self.assertEqual(rules.find_forecast_windows(fc), [])

    def test_skips_blown_out(self):
        fc = _hourly(12, swell_m=1.2, period_s=11, wind_ms=12, wind_dir=180)
        self.assertEqual(rules.find_forecast_windows(fc), [])

    def test_keeps_strong_offshore(self):
        fc = _hourly(12, swell_m=1.2, period_s=11, wind_ms=10, wind_dir=315)
        self.assertGreaterEqual(len(rules.find_forecast_windows(fc)), 1)

    def test_filters_night_hours(self):
        # Start at 02:00 UTC = 22:00 prev day local — all should be filtered as night
        start = datetime(2026, 6, 1, 2, 0, tzinfo=timezone.utc)
        fc = _hourly(4, swell_m=1.2, period_s=11, wind_ms=4, wind_dir=315, start_utc=start)
        self.assertEqual(rules.find_forecast_windows(fc), [])


class OffshoreTests(unittest.TestCase):
    def test_offshore_directions(self):
        for d in [0, 45, 90, 270, 315, 359]:
            self.assertTrue(rules.is_offshore(d), d)

    def test_onshore_directions(self):
        for d in [91, 135, 180, 225, 269]:
            self.assertFalse(rules.is_offshore(d), d)


if __name__ == "__main__":
    unittest.main()
