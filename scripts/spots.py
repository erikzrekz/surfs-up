"""Named spot registry.

Each spot gets its own page under /spots/<slug>/ and its own data file at
docs/spots/<slug>.json. Display only — no alert routing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spot:
    slug: str
    name: str
    subtitle: str
    lat: float
    lon: float


SPOTS: list[Spot] = [
    Spot(
        slug="ocean-mist",
        name="Ocean Mist",
        subtitle="Matunuck, RI",
        lat=41.37378,
        lon=-71.54470,
    ),
    Spot(
        slug="narragansett",
        name="Narragansett Town Beach",
        subtitle="Narragansett, RI",
        lat=41.4324,
        lon=-71.4567,
    ),
    Spot(
        slug="sachuest",
        name="Second Beach",
        subtitle="Sachuest · Middletown, RI",
        lat=41.4824,
        lon=-71.2533,
    ),
    Spot(
        slug="long-sands",
        name="Long Sands Beach",
        subtitle="York, ME",
        lat=43.1450,
        lon=-70.6394,
    ),
    Spot(
        slug="hampton",
        name="Hampton Beach",
        subtitle="Hampton, NH",
        lat=42.9067,
        lon=-70.8044,
    ),
    Spot(
        slug="nauset",
        name="Nauset Beach",
        subtitle="Orleans, MA",
        lat=41.7902,
        lon=-69.9387,
    ),
    Spot(
        slug="long-beach",
        name="Long Beach",
        subtitle="Long Island, NY",
        lat=40.5860,
        lon=-73.6592,
    ),
    Spot(
        slug="rockaway",
        name="Rockaway Beach",
        subtitle="Queens, NY",
        lat=40.5817,
        lon=-73.8358,
    ),
    Spot(
        slug="manasquan",
        name="Manasquan",
        subtitle="Manasquan, NJ",
        lat=40.1018,
        lon=-74.0337,
    ),
    Spot(
        slug="popham",
        name="Popham Beach",
        subtitle="Phippsburg, ME",
        lat=43.7378,
        lon=-69.7872,
    ),
]
