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
]
