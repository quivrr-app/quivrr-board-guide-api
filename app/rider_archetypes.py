from __future__ import annotations

from dataclasses import asdict, dataclass
import math


ARCHETYPES = {
    "beginner_weekend": (0.50, 0.60),
    "improver": (0.43, 0.50),
    "intermediate": (0.38, 0.43),
    "advanced": (0.34, 0.38),
    "expert": (0.31, 0.35),
}


@dataclass(frozen=True)
class ArchetypeVolumeGuidance:
    archetype: str
    volume_low: float
    volume_high: float
    confidence: str
    reasoning: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def canonical_archetype(skill: str, sessions_per_week: float | None) -> str:
    value = (skill or "intermediate").strip().lower().replace(" ", "_")
    if value in {"beginner", "novice"}:
        return "beginner_weekend" if sessions_per_week is None or sessions_per_week <= 1 else "improver"
    if value in ARCHETYPES:
        return value
    return "intermediate"


def recommend_archetype_volume(
    *, height_cm: float | None, weight_kg: float, skill: str,
    fitness: str | None, sessions_per_week: float | None, age: int | None = None,
) -> ArchetypeVolumeGuidance:
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")
    archetype = canonical_archetype(skill, sessions_per_week)
    low_factor, high_factor = ARCHETYPES[archetype]
    low, high = weight_kg * low_factor, weight_kg * high_factor
    reasons = [f"{archetype} baseline uses {low_factor:.2f}-{high_factor:.2f} litres per kilogram"]
    fitness_key = (fitness or "average").strip().lower()
    if fitness_key in {"low", "poor", "lower"}:
        low += 1.5; high += 2.5; reasons.append("added 1.5-2.5L for lower paddle fitness")
    elif fitness_key in {"high", "strong", "very high"}:
        low -= 0.5; high -= 0.5; reasons.append("removed 0.5L for strong paddle fitness")
    if sessions_per_week is not None and sessions_per_week < 1:
        low += 1.0; high += 1.5; reasons.append("added 1-1.5L for less than weekly surfing")
    elif sessions_per_week is not None and sessions_per_week >= 4:
        low -= 0.5; high -= 0.5; reasons.append("removed 0.5L for four or more sessions per week")
    if age is not None and age >= 50 and archetype not in {"expert"}:
        low += 1.5; high += 2.0; reasons.append("added 1.5-2L for age-related paddle forgiveness")
    if height_cm is not None:
        reasons.append("height is retained for future length-fit guidance; volume remains weight-led")
    low = float(math.floor(low + 0.5)); high = float(math.ceil(high - 0.25))
    confidence = "high" if height_cm and fitness and sessions_per_week is not None else "medium"
    return ArchetypeVolumeGuidance(archetype, low, high, confidence, reasons)
