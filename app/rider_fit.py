from __future__ import annotations

from dataclasses import dataclass
import math

from app.models import RiderProfile


@dataclass(frozen=True)
class RiderFitResult:
    volume_low: float
    volume_high: float
    board_category: str
    explanation: str
    adjustment_factors: list[str]

    @property
    def volume_range_label(self) -> str:
        return f"{self.volume_low:g} to {self.volume_high:g}L"


def _key(value: str | None) -> str:
    return (value or "").strip().lower()


def _round_range(low: float, high: float) -> tuple[float, float]:
    # Whole litres are easier to use as guidance and deliberately avoid false precision.
    return float(math.floor(low + 0.5)), float(math.ceil(high - 0.25))


def recommend_rider_fit(profile: RiderProfile) -> RiderFitResult | None:
    if not profile.weight_kg:
        return None

    ability = _key(profile.ability) or "intermediate"
    fitness = _key(profile.fitness_level)
    board_type = _key(profile.preferred_board_type)
    desired = _key(profile.desired_feel or profile.goal)
    waves = " ".join(filter(None, [_key(profile.wave_size), _key(profile.wave_type), _key(profile.wave_power)]))
    frequency = profile.surf_frequency_per_week
    adjustments: list[str] = []

    if ability in {"advanced", "expert"}:
        low_factor, high_factor = 0.34, 0.38
        category = "Performance shortboard or refined daily driver"
    elif ability == "beginner":
        low_factor, high_factor = 0.45, 0.55
        category = "Forgiving hybrid, funboard or mid length"
    else:
        low_factor, high_factor = 0.38, 0.43
        category = "Everyday shortboard or forgiving hybrid"

    low = profile.weight_kg * low_factor
    high = profile.weight_kg * high_factor

    if frequency is not None and frequency <= 1:
        low += 0.5
        high += 0.75
        adjustments.append("Added roughly 1L for low surf frequency")
    elif frequency is not None and frequency >= 3:
        adjustments.append("No frequency uplift: surfing three or more times per week")

    if fitness in {"low", "lower", "poor"}:
        low += 1.5
        high += 2.5
        adjustments.append("Added 1.5-2.5L for lower paddle fitness")
    elif fitness in {"high", "very high", "strong"}:
        adjustments.append("No fitness uplift: strong paddle fitness")

    if any(token in waves for token in ["small", "weak", "soft", "1-2", "1 to 2"]):
        low += 1.0
        high += 2.0
        adjustments.append("Added 1-2L for small or weak waves")

    if any(token in desired for token in ["performance", "responsive", "tighter turns"]):
        low -= 1.0
        high -= 1.0
        category = "Performance shortboard"
        adjustments.append("Reduced 1L for a more performance-focused feel")

    easy_tokens = ["easier paddle", "forgiving", "catch more", "more paddle"]
    buoyant_types = ["groveller", "fish", "hybrid", "mid length", "mid-length"]
    if any(token in desired for token in easy_tokens):
        low += 2.0
        high += 3.0
        adjustments.append("Added 2-3L for easier paddling and forgiveness")
    if any(token in board_type for token in buoyant_types):
        low += 2.0
        high += 4.0
        category = profile.preferred_board_type or "Groveller, fish or hybrid"
        adjustments.append("Added 2-4L for the preferred higher-volume board category")

    if profile.age is not None and profile.age >= 50 and "performance" not in desired:
        low += 2.0
        high += 2.0
        adjustments.append("Added 2L for an older surfer seeking useful forgiveness")

    low, high = _round_range(low, high)
    if profile.target_volume_litres is not None:
        target = profile.target_volume_litres
        adjustments.append(f"Compared against the stated {target:g}L target")

    explanation = (
        f"This starts with the {ability} weight-to-volume guide, then adjusts for surf frequency, "
        "paddle fitness, wave type and the feel you want. Volume is only one part of fit; outline, "
        "rocker, rails and construction still matter."
    )
    return RiderFitResult(low, high, category, explanation, adjustments)
