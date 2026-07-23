from __future__ import annotations

from dataclasses import dataclass

from app.models import RiderProfile, TargetVolumeContext, VolumeRecommendation


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


def _precise(value: float) -> float:
    return round(value, 2)


def _source_label(value: str | None) -> str:
    return {
        "saved_profile": "saved_profile",
        "account_profile": "saved_profile",
        "current_user": "current_message",
        "conversation_user": "conversation_context",
        "conversation_profile": "conversation_context",
        "inferred": "fallback",
    }.get(str(value or "").strip().lower(), "missing")


def infer_volume_lane(profile: RiderProfile, explicit_lane: str | None = None) -> str:
    if explicit_lane:
        return explicit_lane
    text = " ".join(filter(None, [profile.preferred_board_type, profile.desired_feel, profile.goal])).lower()
    waves = " ".join(filter(None, [profile.wave_type, profile.wave_power])).lower()
    if "fish" in text:
        if "reef" in waves:
            return "performance_fish" if "traditional" not in text else "point_break_fish"
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


def build_target_volume_context(profile: RiderProfile, board_lane: str | None = None) -> TargetVolumeContext | None:
    if profile.surfer_stage in {"STAGE_1_TRUE_BEGINNER", "STAGE_2_PROGRESSING_BEGINNER"}:
        # Beginner equipment is selected by stage, dimensions and stability first;
        # a saved shortboard volume must not become a false precision target.
        return None
    lane = infer_volume_lane(profile, board_lane)
    source = _source_label(profile.target_volume_source or profile.field_provenance.get("target_volume_litres") or profile.field_provenance.get("current_volume_litres"))
    confidence = profile.target_volume_confidence or ("high" if source in {"saved_profile", "current_message", "conversation_context"} else "medium")

    if profile.target_volume_litres is not None:
        target = float(profile.target_volume_litres)
        if profile.target_volume_min_litres is not None and profile.target_volume_max_litres is not None:
            minimum = float(profile.target_volume_min_litres)
            maximum = float(profile.target_volume_max_litres)
        elif lane in {"performance_fish"}:
            minimum, maximum = target - 1.0, target + 2.0
        elif lane in {"point_break_fish"}:
            minimum, maximum = target - 1.0, target + 2.0
        elif lane in {"traditional_fish", "cruisy_fish"}:
            minimum, maximum = target, target + 3.0
        else:
            minimum, maximum = target - 1.5, target + 1.5
        return TargetVolumeContext(
            targetLitres=_precise(target),
            minimumLitres=_half(minimum),
            maximumLitres=_half(maximum),
            source=source,
            confidence=confidence,
        )

    if profile.current_volume_litres is not None:
        target = float(profile.current_volume_litres)
        if lane in {"performance_fish", "point_break_fish"}:
            minimum, maximum = target - 1.0, target + 2.0
        elif lane in {"traditional_fish", "cruisy_fish"}:
            minimum, maximum = target, target + 3.0
        else:
            minimum, maximum = target - 1.5, target + 1.5
        return TargetVolumeContext(
            targetLitres=_precise(target),
            minimumLitres=_half(minimum),
            maximumLitres=_half(maximum),
            source=_source_label(profile.field_provenance.get("current_volume_litres")),
            confidence="high",
        )

    fit = recommend_volume_v2(profile, board_lane)
    if fit is None:
        return None
    return TargetVolumeContext(
        targetLitres=fit.target_volume,
        minimumLitres=fit.minimum_volume,
        maximumLitres=fit.maximum_volume,
        source="fallback",
        confidence=fit.confidence,
    )


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
    if profile.surfer_stage in {"STAGE_1_TRUE_BEGINNER", "STAGE_2_PROGRESSING_BEGINNER"}:
        return None
    target_context = build_target_volume_context(profile, board_lane)
    if target_context and target_context.target_litres is not None:
        explanation = (
            f"The current target is about {target_context.target_litres:g}L, with a comfortable working range of "
            f"{target_context.minimum_litres:g} to {target_context.maximum_litres:g}L. Volume is only part of the fit, because outline, "
            "width, rocker, foil and rail shape can make two boards at the same litres feel very different."
        )
        confidence = {"high": 0.9, "medium": 0.7}.get(target_context.confidence, 0.5)
        return VolumeRecommendation(
            target_midpoint_litres=target_context.target_litres,
            comfortable_min_litres=target_context.minimum_litres,
            comfortable_max_litres=target_context.maximum_litres,
            performance_min_litres=max((target_context.minimum_litres or 0.0) - 1.0, 0.0),
            forgiving_max_litres=(target_context.maximum_litres or 0.0) + 1.0,
            confidence=confidence,
            explanation=explanation,
        )

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
