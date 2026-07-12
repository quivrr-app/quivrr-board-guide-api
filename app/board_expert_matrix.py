from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.models import RiderProfile, SuggestedBoard
from app.rider_fit import recommend_rider_fit


MATRIX_PATH = Path(__file__).parent / "knowledge/generated/board_expert_matrix.json"
ABILITY_ORDER = {
    "beginner": 0,
    "progressing": 1,
    "intermediate": 2,
    "advanced": 3,
    "expert": 4,
}
FAMILY_LANES = {
    "performance_shortboard": {
        "high_performance_shortboard",
        "competition_shortboard",
        "performance_daily_driver",
        "performance_step_up",
    },
    "performance_twin": {"twin_fin_performance", "alternative_performance"},
    "fish": {
        "traditional_fish",
        "performance_fish",
        "modern_fish",
        "small_wave_fish",
        "cruisy_fish",
        "point_break_fish",
        "fish_hybrid",
        "twin_fin_performance",
    },
    "hybrid": {
        "hybrid_daily_driver",
        "forgiving_daily_driver",
        "performance_daily_driver",
        "one_board_quiver",
        "fish_hybrid",
    },
    "small_wave": {
        "groveller",
        "small_wave_daily_driver",
        "weak_wave_board",
        "small_wave_fish",
        "fish_hybrid",
        "hybrid_daily_driver",
        "step_down_shortboard",
        "performance_groveller",
        "forgiving_groveller",
        "high_volume_groveller",
    },
    "step_up": {
        "step_up",
        "performance_step_up",
        "big_wave_step_up",
        "travel_step_up",
        "barrel_board",
    },
    "mid_length": {
        "mid_length",
        "performance_mid_length",
        "cruisy_mid_length",
        "mid_length_twin",
        "mid_length_single_fin",
    },
}
PRIMARY_FAMILY_BY_REQUEST = {
    "true_hpsb": {"High Performance Shortboard", "Performance Shortboard"},
    "performance_shortboard": {"High Performance Shortboard", "Performance Shortboard", "Performance Daily Driver"},
    "performance_daily_driver": {"Performance Daily Driver", "High Performance Shortboard"},
    "forgiving_performance": {"Performance Daily Driver", "Daily Driver", "Hybrid Shortboard", "Performance Shortboard"},
    "performance_twin": {"Performance Twin"},
    "fish": {"Fish", "Performance Fish", "Twin Fin", "Performance Twin"},
    "small_wave": {"Small Wave Shortboard", "Groveller", "Performance Fish", "Fish", "Hybrid Shortboard"},
    "step_up": {"Step Up", "Semi Gun", "Performance Shortboard"},
}


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _normalise_text(*values: str | None) -> str:
    return " ".join(filter(None, values)).lower()


def _ability_rank(value: str | None) -> int:
    return ABILITY_ORDER.get(_key(value), 2)


def _surf_frequency_bucket(profile: RiderProfile) -> str:
    frequency = profile.surf_frequency_per_week or 0
    if frequency >= 3:
        return "regular"
    if frequency >= 1:
        return "moderate"
    return "low"


def _fitness_bucket(profile: RiderProfile) -> str:
    value = _key(profile.fitness_level)
    if value in {"high", "strong", "good", "fit"}:
        return "high"
    if value in {"low", "poor"}:
        return "low"
    return "medium"


def _paddle_bucket(profile: RiderProfile) -> str:
    value = _key(profile.paddle_strength)
    if value in {"high", "strong", "good"}:
        return "high"
    if value in {"low", "weak"}:
        return "low"
    return "medium"


def _support_needs(profile: RiderProfile) -> int:
    support = 0
    if (profile.age or 0) >= 45:
        support += 1
    if _fitness_bucket(profile) == "low":
        support += 2
    elif _fitness_bucket(profile) == "medium":
        support += 1
    if _surf_frequency_bucket(profile) == "low":
        support += 2
    elif _surf_frequency_bucket(profile) == "moderate":
        support += 1
    if _paddle_bucket(profile) == "low":
        support += 2
    elif _paddle_bucket(profile) == "medium":
        support += 1
    return support


@lru_cache(maxsize=1)
def load_matrix() -> list[dict]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8-sig")).get("boards", [])


def find_matrix_board(brand: str, model: str) -> dict | None:
    brand_key, model_key = _key(brand), _key(model)
    return next((row for row in load_matrix() if _key(row.get("brand")) == brand_key and _key(row.get("model")) == model_key), None)


def target_lanes(profile: RiderProfile) -> list[str]:
    text = _normalise_text(profile.preferred_board_type, profile.goal, profile.wave_power, profile.desired_feel)
    lanes: list[str] = []
    if "small wave" in text or "weak wave" in text:
        lanes.extend(["groveller", "small_wave_daily_driver", "weak_wave_board", "small_wave_fish", "fish_hybrid"])
    if "fish" in text:
        if "point" in _key(profile.wave_type):
            lanes.extend(["point_break_fish", "traditional_fish", "performance_fish", "twin_fin_performance"])
        elif "weak" in text or "beach" in _key(profile.wave_type):
            lanes.extend(["small_wave_fish", "cruisy_fish", "fish_hybrid"])
        else:
            lanes.extend(["modern_fish", "performance_fish", "traditional_fish", "cruisy_fish"])
    if "twin" in text:
        lanes.extend(["twin_fin_performance", "modern_fish"])
    if "grov" in text:
        lanes.extend(["groveller", "performance_groveller", "small_wave_daily_driver"])
    if "daily driver" in text:
        if any(token in text for token in ("forgiving", "easy", "paddle", "support")):
            lanes.extend(["forgiving_daily_driver", "hybrid_daily_driver", "one_board_quiver"])
        else:
            lanes.extend(["performance_daily_driver", "high_performance_shortboard"])
    if "performance shortboard" in text or "competition shortboard" in text or "true performance shortboard" in text:
        lanes.extend(["high_performance_shortboard", "performance_step_up", "performance_daily_driver"])
    elif "performance" in text and "daily driver" not in text:
        lanes.extend(["high_performance_shortboard", "performance_daily_driver"])
    if "step" in text:
        lanes.extend(["performance_step_up", "barrel_board"])
    if "mid" in text:
        lanes.append("mid_length")
    if "shortboard" in text and "performance" not in text and "daily driver" not in text:
        lanes.extend(["performance_daily_driver", "forgiving_daily_driver", "high_performance_shortboard"])
    return list(dict.fromkeys(lanes)) or ["one_board_quiver", "forgiving_daily_driver", "performance_daily_driver"]


def resolve_target_family(profile: RiderProfile) -> str | None:
    text = _normalise_text(profile.preferred_board_type, profile.goal, profile.desired_feel, profile.wave_power)
    if "performance twin" in text or ("twin" in text and "performance" in text):
        return "performance_twin"
    if "true performance shortboard" in text or "competition shortboard" in text:
        return "performance_shortboard"
    if "performance shortboard" in text:
        return "performance_shortboard"
    if "fish" in text or "twin" in text:
        return "fish"
    if "small wave" in text or "weak wave" in text or "grov" in text:
        return "small_wave"
    if "step" in text:
        return "step_up"
    if "mid" in text or "egg" in text:
        return "mid_length"
    if "hybrid" in text or "daily driver" in text or "everyday" in text or "shortboard" in text:
        return "hybrid"
    return None


def _volume_distance(board: dict, target: float | None) -> float:
    if target is None:
        return 0
    low, high = board.get("volumeRange", {}).get("min"), board.get("volumeRange", {}).get("max")
    if low is None or high is None:
        return 5
    return 0 if low <= target <= high else min(abs(target - low), abs(target - high))


def _primary_family(board: dict) -> str:
    return str(board.get("primaryFamily") or "Alternative Performance")


def _intent_profile(profile: RiderProfile) -> dict:
    text = _normalise_text(profile.preferred_board_type, profile.goal, profile.desired_feel, profile.wave_power, profile.wave_type)
    strict_hpsb = any(token in text for token in ("true performance shortboard", "competition shortboard", "conventional high performance shortboard", "strict hpsb"))
    wants_performance_twin = "performance twin" in text or ("twin" in text and "performance" in text)
    wants_forgiving = any(token in text for token in ("forgiving", "more forgiving", "support", "paddle help", "easy"))
    wants_performance_daily_driver = (
        "performance daily driver" in text
        or "daily shortboard" in text
        or (
            _key(profile.preferred_board_type) == "daily driver"
            and _ability_rank(profile.ability) >= ABILITY_ORDER["advanced"]
            and not wants_forgiving
        )
    )
    intent_key = "performance_shortboard"
    if wants_performance_twin:
        intent_key = "performance_twin"
    elif wants_performance_daily_driver:
        intent_key = "performance_daily_driver"
    elif "fish" in text:
        intent_key = "fish"
    elif "small wave" in text or "weak wave" in text or "grov" in text:
        intent_key = "small_wave"
    elif "step" in text:
        intent_key = "step_up"
    elif wants_forgiving and "performance" in text:
        intent_key = "forgiving_performance"
    elif strict_hpsb or "performance shortboard" in text:
        intent_key = "performance_shortboard"
    return {
        "text": text,
        "strict_hpsb": strict_hpsb,
        "wants_performance_twin": wants_performance_twin,
        "wants_forgiving": wants_forgiving,
        "wants_performance_daily_driver": wants_performance_daily_driver,
        "intent_key": intent_key,
        "allowed_families": PRIMARY_FAMILY_BY_REQUEST.get(intent_key, set()),
    }


def _family_score(board: dict, intent: dict) -> tuple[float, list[str], list[str]]:
    family = _primary_family(board)
    reasons: list[str] = []
    exclusions: list[str] = []
    score = 0.0

    if intent["allowed_families"] and family not in intent["allowed_families"]:
        if intent["strict_hpsb"] and family == "Performance Twin":
            exclusions.append("Strict conventional high-performance shortboard request excludes performance twins.")
        elif intent["intent_key"] == "fish" and family not in {"Fish", "Performance Fish", "Twin Fin", "Performance Twin"}:
            exclusions.append("Fish request excludes non-fish shortboard families.")
        else:
            score -= 35
    else:
        score += 45

    if intent["wants_performance_daily_driver"] and family == "High Performance Shortboard":
        score -= 18
    if intent["wants_performance_daily_driver"] and family == "Performance Daily Driver":
        score += 16

    if family == "High Performance Shortboard":
        reasons.append("genuine high-performance thruster direction")
    elif family == "Performance Daily Driver":
        reasons.append("performance daily-driver direction")
    elif family == "Performance Twin":
        reasons.append("alternative performance twin direction")
    return score, reasons, exclusions


def _ability_score(board: dict, profile: RiderProfile, intent: dict) -> tuple[float, list[str], list[str]]:
    family = _primary_family(board)
    surfer_rank = _ability_rank(profile.ability)
    minimum_rank = _ability_rank(board.get("abilityMin")) if board.get("abilityMin") else None
    preferred_ranks = [_ability_rank(value) for value in board.get("abilityPreferred", [])]
    reasons: list[str] = []
    exclusions: list[str] = []
    score = 0.0

    if family == "High Performance Shortboard" and surfer_rank <= ABILITY_ORDER["progressing"]:
        exclusions.append("Beginners and low intermediates should not be pushed onto a true high-performance shortboard.")
        return score, reasons, exclusions
    if family == "High Performance Shortboard" and surfer_rank <= ABILITY_ORDER["intermediate"] and not intent["strict_hpsb"]:
        if _support_needs(profile) >= 3 or intent["wants_forgiving"]:
            exclusions.append("This rider profile needs a more forgiving performance board than a true high-performance shortboard.")
            return score, reasons, exclusions

    if minimum_rank is not None and surfer_rank < minimum_rank:
        score -= 25
    else:
        score += 18
    if preferred_ranks and surfer_rank in preferred_ranks:
        score += 8
        reasons.append("ability lines up with the board's intended level")
    elif family == "Performance Daily Driver" and surfer_rank >= ABILITY_ORDER["intermediate"]:
        score += 8
        reasons.append("ability suits a forgiving performance board")
    return score, reasons, exclusions


def _wave_score(board: dict, profile: RiderProfile, intent: dict) -> tuple[float, list[str], list[str]]:
    text = intent["text"]
    reasons: list[str] = []
    exclusions: list[str] = []
    score = 0.0
    family = _primary_family(board)

    if ("weak wave" in text or "small wave" in text) and family in {"High Performance Shortboard", "Performance Shortboard"}:
        exclusions.append("Weak-wave request excludes narrow, high-rocker performance shortboards.")
        return score, reasons, exclusions

    wave_types = {_key(item) for item in board.get("waveTypes", [])}
    wave_power = {_key(item) for item in board.get("wavePower", [])}
    if "point" in _key(profile.wave_type) and "point break" in " ".join(wave_types):
        score += 8
        reasons.append("point-break direction matches")
    if profile.wave_power and _key(profile.wave_power) in wave_power:
        score += 8
        reasons.append("wave power fit is coherent")
    elif not profile.wave_power and family in {"High Performance Shortboard", "Performance Shortboard"} and "stronger" in text:
        score += 8
        reasons.append("stronger-wave brief fits the design lane")
    return score, reasons, exclusions


def _variant_score(board: dict, profile: RiderProfile, intent: dict) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    exclusions: list[str] = []
    score = 0.0

    if not board.get("xlVariant"):
        if board.get("baseModel") and board.get("baseModel") != board.get("model"):
            reasons.append("standard variant keeps the outline and rail line cleaner")
        return 6, reasons, exclusions

    support_need = _support_needs(profile)
    explicit_support = any(token in intent["text"] for token in ("extra paddle", "more support", "stability", "forgiving"))
    weight = profile.weight_kg or 0
    min_weight = board.get("riderWeightMinKg") or 0
    if weight and min_weight and weight < min_weight and support_need <= 2 and not explicit_support:
        exclusions.append("XL variant would add width and foam beyond what this rider has asked for.")
        return score, reasons, exclusions
    if intent["strict_hpsb"] and weight and weight <= 78 and support_need <= 2 and not explicit_support:
        exclusions.append("Strict performance shortboard brief excludes XL variants that force unnaturally short sizing for lighter advanced surfers.")
        return score, reasons, exclusions

    if support_need >= 4 or explicit_support:
        score += 22
        reasons.append("extra support, foam, and width are justified here")
    else:
        score -= 16
    return score, reasons, exclusions


def _age_fitness_score(board: dict, profile: RiderProfile) -> tuple[float, list[str]]:
    support_need = _support_needs(profile)
    family = _primary_family(board)
    reasons: list[str] = []
    score = 0.0

    if support_need >= 4 and family in {"Performance Daily Driver", "Daily Driver", "Hybrid Shortboard", "Performance Shortboard"}:
        score += 12
        reasons.append("extra support suits the current age, fitness, and surf-frequency mix")
    elif support_need <= 1 and family == "High Performance Shortboard":
        score += 10
        reasons.append("fitness and frequency support a more technical shortboard")
    return score, reasons


def _goal_score(board: dict, profile: RiderProfile, intent: dict) -> tuple[float, list[str]]:
    text = intent["text"]
    reasons: list[str] = []
    score = 0.0
    family = _primary_family(board)

    if "performance progression" in text or "performance" in text:
        if family in {"High Performance Shortboard", "Performance Shortboard", "Performance Daily Driver"}:
            score += 12
            reasons.append("performance goal matches the design brief")
    if intent["wants_forgiving"] and family in {"Performance Daily Driver", "Daily Driver", "Hybrid Shortboard"}:
        score += 12
        reasons.append("more forgiving than a pure comp board")
    if intent["wants_performance_daily_driver"] and family == "Performance Daily Driver":
        score += 14
        reasons.append("daily-driver brief without drifting into generic hybrids")
    return score, reasons


def _priority_score(board: dict, profile: RiderProfile, intent: dict) -> tuple[float, list[str]]:
    model_key = _key(board.get("model"))
    support_need = _support_needs(profile)
    reasons: list[str] = []
    score = 0.0

    if intent["strict_hpsb"] or intent["intent_key"] == "performance_shortboard":
        priority = {
            "monsta": 24,
            "ghost": 18,
            "ghost pro": 16,
            "driver 2 0": 16,
            "fever": 14,
            "inferno 72": 14,
        }
        score += priority.get(model_key, 0)
    if intent["wants_performance_daily_driver"]:
        priority = {
            "phantom": 24,
            "xero gravity": 22,
            "happy everyday": 20,
            "inferno 72": 18,
            "rad ripper": 18,
            "monsta": -6,
        }
        score += priority.get(model_key, 0)
    if intent["wants_forgiving"]:
        priority = {
            "phantom": 18,
            "phantom xl": 20,
            "xero gravity": 16,
            "happy everyday": 16,
            "better everyday": 15,
            "dominator pro": 14,
            "ghost xl": 24 if support_need >= 3 else 0,
        }
        score += priority.get(model_key, 0)
    if score > 0:
        reasons.append("reviewed priority model for this brief")
    return score, reasons


def _explanation(board: dict, profile: RiderProfile, reasons: list[str], target: float | None, distance: float) -> str:
    family = _primary_family(board)
    if board.get("model") == "Ghost":
        return (
            f"Standard Ghost suits your {profile.weight_kg:g} kg weight and advanced ability better than the XL. "
            f"It keeps the rail line and width more appropriate for a performance shortboard near your target volume."
        )
    if board.get("model") == "Monsta":
        return "The Monsta is a genuine high-performance thruster and fits a goal of more responsive surfing in stronger waves."
    reason_text = ", ".join(dict.fromkeys(reasons[:3])) if reasons else family.lower()
    if target is not None:
        return f"{family} fit with {reason_text}. The size band sits {distance:g}L from the {target:g}L target."
    return f"{family} fit with {reason_text}."


def recommend_from_matrix(profile: RiderProfile, limit: int = 12) -> list[SuggestedBoard]:
    lanes = target_lanes(profile)
    family = resolve_target_family(profile)
    allowed_lanes = FAMILY_LANES.get(family, set())
    fit = recommend_rider_fit(profile)
    target = profile.target_volume_litres or ((fit.volume_low + fit.volume_high) / 2 if fit else None)
    intent = _intent_profile(profile)
    rows = []

    for board in load_matrix():
        if profile.requested_brand and _key(board.get("brand")) != _key(profile.requested_brand):
            continue

        board_lanes = {board["primaryLane"], *board.get("secondaryLanes", []), *board.get("boardLanes", [])}
        if allowed_lanes and not (board_lanes & allowed_lanes):
            continue

        lane_rank = next((len(lanes) - index for index, lane in enumerate(lanes) if lane in board_lanes), 0)
        if lane_rank == 0:
            continue

        distance = _volume_distance(board, target)
        score = lane_rank * 18 - distance * 4
        reasons: list[str] = []
        exclusions: list[str] = []

        for part_score, part_reasons, part_exclusions in (
            _family_score(board, intent),
            _ability_score(board, profile, intent),
            _wave_score(board, profile, intent),
            _variant_score(board, profile, intent),
        ):
            score += part_score
            reasons.extend(part_reasons)
            exclusions.extend(part_exclusions)

        age_score, age_reasons = _age_fitness_score(board, profile)
        goal_score, goal_reasons = _goal_score(board, profile, intent)
        priority_score, priority_reasons = _priority_score(board, profile, intent)
        score += age_score + goal_score + priority_score
        reasons.extend(age_reasons)
        reasons.extend(goal_reasons)
        reasons.extend(priority_reasons)

        if exclusions:
            continue

        if profile.preferred_brands and any(_key(board["brand"]) == _key(brand) for brand in profile.preferred_brands):
            score += 4
            reasons.append("preferred brand")

        if board.get("primaryFamily") == "Performance Daily Driver" and intent["wants_forgiving"]:
            score += 8
        if board.get("primaryFamily") == "Performance Twin" and intent["wants_performance_twin"]:
            score += 14

        rows.append((score, board, distance, reasons))

    rows.sort(key=lambda item: (-item[0], item[1]["brand"], item[1]["model"]))
    selected: list[SuggestedBoard] = []
    brands: dict[str, int] = {}

    for score_value, board, distance, reasons in rows:
        brand_key = _key(board["brand"])
        if brands.get(brand_key, 0) >= 2:
            continue
        brands[brand_key] = brands.get(brand_key, 0) + 1

        confidence = {"high": 0.94, "medium": 0.78, "low": 0.58}.get(board.get("confidence"), 0.55)
        selected.append(
            SuggestedBoard(
                brand=board["brand"],
                model=board["model"],
                category=_primary_family(board),
                confidence=confidence,
                why_it_fits=_explanation(board, profile, reasons, target, distance),
                description=board.get("manufacturerDescription"),
                volume_range=(
                    f"{board['volumeRange']['min']:g}-{board['volumeRange']['max']:g}L"
                    if board.get("volumeRange", {}).get("min") is not None
                    else None
                ),
                wave_range=(
                    f"{board['waveRangeMinFt']:g}-{board['waveRangeMaxFt']:g}ft"
                    if board.get("waveRangeMinFt") is not None and board.get("waveRangeMaxFt") is not None
                    else None
                ),
                skill_fit=" to ".join(filter(None, [board.get("abilityMin"), board.get("abilityMax")])) or None,
                source="quivrr_board_expert_matrix",
                board_model_id=board.get("boardModelId"),
            )
        )
        if len(selected) >= limit:
            break
    return selected
