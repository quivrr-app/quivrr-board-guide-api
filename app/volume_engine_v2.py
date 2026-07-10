from __future__ import annotations

from dataclasses import dataclass

from app.models import RiderProfile, VolumeRecommendation


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
    lane = infer_volume_lane(profile, board_lane)
    reasons = []
    if profile.weight_kg:
        factors = LANE_FACTORS.get(lane, LANE_FACTORS["performance_shortboard"])
        low, target, high = (profile.weight_kg * value for value in factors)
        reasons.append(f"Started with the {lane.replace('_', ' ')} volume band for a {profile.weight_kg:g}kg surfer")
    elif profile.current_volume_litres is not None:
        target = profile.current_volume_litres
        low = target - 1.5
        high = target + 1.5
        reasons.append(f"Started from the current comfortable {profile.current_volume_litres:g}L because weight was not supplied")
    else:
        return None
    ability = (profile.ability or "intermediate").lower()
    fitness = (profile.fitness_level or "").lower()
    paddle_strength = (profile.paddle_strength or "").lower()
    frequency = profile.surf_frequency_per_week
    waves = " ".join(filter(None, [profile.wave_type, profile.wave_power, profile.wave_size])).lower()
    desired = " ".join(filter(None, [profile.desired_feel, profile.goal])).lower()
    feedback = (profile.current_board_feedback or "").lower()
    adjustment = 0.0
    if ability == "advanced":
        adjustment -= 1.0; reasons.append("Reduced 1L for advanced ability")
    elif ability == "expert":
        adjustment -= 2.0; reasons.append("Reduced 2L for expert ability")
    elif ability == "beginner":
        adjustment += 3.0; reasons.append("Added 3L for beginner stability and wave entry")
    if fitness in {"low", "lower", "poor"}:
        adjustment += 2.0; reasons.append("Added 2L for lower paddle fitness")
    if paddle_strength == "strong":
        adjustment -= 0.5; reasons.append("Strong paddle strength: -0.5L")
    elif paddle_strength == "weak":
        adjustment += 1.0; reasons.append("Weak paddle strength: +1.0L")
    if frequency is not None and frequency <= 1:
        adjustment += 1.0; reasons.append("Added 1L for low surf frequency")
    if "weak" in waves or "soft" in waves:
        adjustment += 1.0; reasons.append("Added 1L for weak-wave speed and wave entry")
    if "powerful" in waves:
        adjustment -= 0.5; reasons.append("Powerful waves: -0.5L")
    if "powerful" in waves and ability in {"advanced", "expert"}:
        adjustment -= .5; reasons.append("Reduced 0.5L because advanced surfers need less flotation in powerful waves")
    if profile.age and profile.age >= 50 and (fitness in {"low", "lower", "poor"} or frequency is not None and frequency <= 1 or "forgiv" in desired):
        adjustment += 1.5; reasons.append("Added 1.5L for age together with a stated forgiveness or paddling need")
    if "forgiv" in desired or "stable" in desired or "catch more waves" in desired:
        adjustment += 1.0; reasons.append("Forgiving brief: +1.0L")
    if "high performance" in desired or "responsive" in desired or "improve turns" in desired:
        adjustment -= 0.5; reasons.append("High-performance brief: -0.5L")
    if "hard to paddle" in feedback or "too small" in feedback:
        adjustment += 1.5; reasons.append("Current board feels under-volumed: +1.5L")
    if "too big" in feedback or "too corky" in feedback:
        adjustment -= 1.0; reasons.append("Current board feels over-volumed: -1.0L")
    low, target, high = low + adjustment, target + adjustment, high + adjustment
    if profile.current_volume_litres is not None:
        target = target * .6 + profile.current_volume_litres * .4
        low = min(low, target - 1.5)
        high = max(high, target + 1.5)
        reasons.append(f"Anchored the target partly to the current {profile.current_volume_litres:g}L board")
        if "hard to paddle" in feedback or "too small" in feedback:
            target += 0.5
            reasons.append("Post-anchor correction for an under-volumed current board: +0.5L")
        if "too big" in feedback or "too corky" in feedback:
            target -= 0.5
            reasons.append("Post-anchor correction for an over-volumed current board: -0.5L")
    low, target, high = _half(low), _half(target), _half(high)
    confidence = "high" if profile.ability and profile.fitness_level else "medium"
    return VolumeFitV2(low, target, high, f"{low:g} to {high:g}L", lane, reasons, confidence)


def fish_volume_bands(profile: RiderProfile) -> dict[str, VolumeFitV2]:
    return {lane: recommend_volume_v2(profile, lane) for lane in ("traditional_fish", "performance_fish", "point_break_fish", "cruisy_fish")}


def build_volume_recommendation(profile: RiderProfile, board_lane: str | None = None) -> VolumeRecommendation | None:
    fit = recommend_volume_v2(profile, board_lane)
    if fit is None:
        return None

    explanation = (
        f"The current target is about {fit.target_volume:g}L, with a comfortable working range of "
        f"{fit.minimum_volume:g} to {fit.maximum_volume:g}L. Volume is only part of the fit, because outline, "
        "width, rocker, foil and rail shape can make two boards at the same litres feel very different."
    )
    return VolumeRecommendation(
        target_midpoint_litres=fit.target_volume,
        comfortable_min_litres=fit.minimum_volume,
        comfortable_max_litres=fit.maximum_volume,
        performance_min_litres=max(fit.minimum_volume - 1.0, 0.0),
        forgiving_max_litres=fit.maximum_volume + 1.0,
        confidence=0.9 if fit.confidence == "high" else 0.7 if fit.confidence == "medium" else 0.5,
        explanation=explanation,
    )
