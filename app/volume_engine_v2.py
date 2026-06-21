from __future__ import annotations

from dataclasses import dataclass

from app.models import RiderProfile


@dataclass(frozen=True)
class VolumeFitV2:
    minimum_volume: float
    target_volume: float
    maximum_volume: float
    volume_band_label: str
    board_lane: str
    reasoning: list[str]
    confidence: str


LANE_FACTORS = {
    "performance_shortboard": (.368, .388, .408),
    "performance_daily_driver": (.382, .401, .421),
    "traditional_fish": (.421, .447, .474),
    "performance_fish": (.401, .421, .447),
    "point_break_fish": (.408, .434, .461),
    "cruisy_fish": (.447, .474, .500),
    "groveller": (.434, .467, .500),
    "step_up": (.375, .395, .414),
}


def _half(value: float) -> float:
    return round(value * 2) / 2


def infer_volume_lane(profile: RiderProfile, explicit_lane: str | None = None) -> str:
    if explicit_lane:
        return explicit_lane
    text = " ".join(filter(None, [profile.preferred_board_type, profile.desired_feel, profile.goal])).lower()
    waves = " ".join(filter(None, [profile.wave_type, profile.wave_power])).lower()
    if "fish" in text:
        if "traditional" in text:
            return "traditional_fish"
        if "cruisy" in text:
            return "cruisy_fish"
        if "performance" in text:
            return "performance_fish"
        if "point" in waves:
            return "point_break_fish"
        return "performance_fish"
    if "grov" in text:
        return "groveller"
    if "step" in text:
        return "step_up"
    if "daily" in text:
        return "performance_daily_driver"
    return "performance_shortboard"


def recommend_volume_v2(profile: RiderProfile, board_lane: str | None = None) -> VolumeFitV2 | None:
    if not profile.weight_kg:
        return None
    lane = infer_volume_lane(profile, board_lane)
    factors = LANE_FACTORS.get(lane, LANE_FACTORS["performance_shortboard"])
    low, target, high = (profile.weight_kg * value for value in factors)
    reasons = [f"Started with the {lane.replace('_', ' ')} volume band for a {profile.weight_kg:g}kg surfer"]
    ability = (profile.ability or "intermediate").lower()
    fitness = (profile.fitness_level or "").lower()
    frequency = profile.surf_frequency_per_week
    waves = " ".join(filter(None, [profile.wave_type, profile.wave_power, profile.wave_size])).lower()
    desired = " ".join(filter(None, [profile.desired_feel, profile.goal])).lower()
    adjustment = 0.0
    if ability == "advanced":
        adjustment -= 1.0; reasons.append("Reduced 1L for advanced ability")
    elif ability == "expert":
        adjustment -= 2.0; reasons.append("Reduced 2L for expert ability")
    elif ability == "beginner":
        adjustment += 3.0; reasons.append("Added 3L for beginner stability and wave entry")
    if fitness in {"low", "lower", "poor"}:
        adjustment += 2.0; reasons.append("Added 2L for lower paddle fitness")
    if frequency is not None and frequency <= 1:
        adjustment += 1.0; reasons.append("Added 1L for low surf frequency")
    if "weak" in waves or "soft" in waves:
        adjustment += 1.0; reasons.append("Added 1L for weak-wave speed and wave entry")
    if "powerful" in waves and ability in {"advanced", "expert"}:
        adjustment -= .5; reasons.append("Reduced 0.5L because advanced surfers need less flotation in powerful waves")
    if profile.age and profile.age >= 50 and (fitness in {"low", "lower", "poor"} or frequency is not None and frequency <= 1 or "forgiv" in desired):
        adjustment += 1.5; reasons.append("Added 1.5L for age together with a stated forgiveness or paddling need")
    low, target, high = low + adjustment, target + adjustment, high + adjustment
    if profile.current_volume_litres is not None:
        target = target * .6 + profile.current_volume_litres * .4
        low = min(low, target - 1.5)
        high = max(high, target + 1.5)
        reasons.append(f"Anchored the target partly to the current {profile.current_volume_litres:g}L board")
    low, target, high = _half(low), _half(target), _half(high)
    confidence = "high" if profile.ability and profile.fitness_level else "medium"
    return VolumeFitV2(low, target, high, f"{low:g} to {high:g}L", lane, reasons, confidence)


def fish_volume_bands(profile: RiderProfile) -> dict[str, VolumeFitV2]:
    return {lane: recommend_volume_v2(profile, lane) for lane in ("traditional_fish", "performance_fish", "point_break_fish", "cruisy_fish")}
