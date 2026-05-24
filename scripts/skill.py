"""Beginner-mode skill assessment.

Translates face-height / period / wind into a plain-language verdict for a
beginner surfer. Independent of the alert rules (which target any rideable
condition); this layer says whether the *user* should paddle out.

Tuned against a real session: May 16, Ocean Mist, ~2ft face @ 5–6s windswell —
described as "got knocked around, stuck inside 15min, body-surfed in."
That's the canonical "worked" tier.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillVerdict:
    level: str   # out-of-range | worked | manageable | marginal | flat | unknown
    emoji: str
    label: str
    note: str


def evaluate_skill(
    face_ft: float | None,
    period_s: float | None,
    wind_kt: float | None,
) -> SkillVerdict:
    if face_ft is None:
        return SkillVerdict("unknown", "❓", "No read", "Couldn't read conditions.")

    p = period_s or 0.0
    w = wind_kt or 0.0

    # Too big — head-high+ at a beach break is past beginner territory.
    if face_ft >= 5.0:
        return SkillVerdict(
            "out-of-range", "🫠", "Too big for you",
            f"~{face_ft:.0f}ft face — sit this one out and watch.",
        )

    # Windswell of any size taxes a beginner more than the height suggests.
    # The "knocked around" zone.
    if face_ft >= 1.8 and p < 7.0:
        return SkillVerdict(
            "worked", "😤", "You're gonna get worked",
            f"{face_ft:.1f}ft @ {p:.0f}s — short-period windswell. Expect a beating on the paddle-out.",
        )

    # Sized right, cleaner period, light wind: the green-light tier.
    if 1.5 <= face_ft <= 4.0 and p >= 7.0 and w <= 12.0:
        return SkillVerdict(
            "manageable", "🤙", "This is your wave",
            f"{face_ft:.1f}ft @ {p:.0f}s, wind {w:.0f}kt. Clean enough, sized right — go.",
        )

    # Small but rideable — play tier.
    if face_ft >= 1.0:
        if w > 15.0:
            return SkillVerdict(
                "marginal", "💨", "Blown out",
                f"Wind {w:.0f}kt — surface will be choppy. Small and messy.",
            )
        return SkillVerdict(
            "marginal", "🌊", "Mushy fun",
            f"{face_ft:.1f}ft @ {p:.0f}s — small and forgiving. Good for practicing pop-ups.",
        )

    # Below 1ft face.
    return SkillVerdict(
        "flat", "🥱", "Flat",
        f"~{face_ft:.1f}ft face. Nothing to ride. Coffee instead.",
    )
