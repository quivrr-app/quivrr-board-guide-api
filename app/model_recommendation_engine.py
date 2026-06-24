import json
from pathlib import Path

from app.models import RiderProfile, SuggestedBoard
from app.rider_fit import recommend_rider_fit
from app.daily_driver_taxonomy import daily_driver_lane, lane_label


INTELLIGENCE_PATH = Path(__file__).parent / "knowledge" / "board_intelligence.json"
GENERATED_INTELLIGENCE_PATH = Path(__file__).parent / "knowledge" / "generated" / "board_intelligence_generated.json"
CANONICAL_PROFILES_PATH = Path(__file__).parent / "knowledge" / "generated" / "canonical_board_profiles.json"


def _load_board_intelligence() -> list[dict]:
    if not INTELLIGENCE_PATH.exists():
        return []

    try:
        data = json.loads(INTELLIGENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    boards = data.get("boards", [])
    if not isinstance(boards, list):
        return []

    return boards


def _load_generated_intelligence() -> list[dict]:
    if not GENERATED_INTELLIGENCE_PATH.exists():
        return []

    try:
        data = json.loads(GENERATED_INTELLIGENCE_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []

    boards = data.get("boards", [])
    if not isinstance(boards, list):
        return []

    return boards


def find_board_description(brand: str, model: str, boards: list[dict] | None = None) -> dict | None:
    for board in boards if boards is not None else _load_generated_intelligence():
        if _normalise(board.get("brand")) != _normalise(brand):
            continue
        if _normalise(board.get("model")) != _normalise(model):
            continue
        description = board.get("model_description") or board.get("summary")
        if not description:
            return None
        return {
            "description": description,
            "shortDescription": board.get("short_description") or board.get("summary"),
            "sourceUrl": board.get("source_url") or board.get("official_product_url"),
            "sourceType": board.get("source_type") or "canonical_catalogue",
        }
    return None


def _load_canonical_profiles() -> list[dict]:
    if not CANONICAL_PROFILES_PATH.exists():
        return []

    try:
        data = json.loads(CANONICAL_PROFILES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    return data


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _profile_target_volume(profile: RiderProfile) -> tuple[float | None, float | None]:
    if profile.target_volume_litres is not None:
        return profile.target_volume_litres - 1.0, profile.target_volume_litres + 1.0
    fit = recommend_rider_fit(profile)
    return (fit.volume_low, fit.volume_high) if fit else (None, None)


def _profile_volume_mid(profile: RiderProfile) -> float | None:
    low, high = _profile_target_volume(profile)
    if low is None or high is None:
        return None
    return round((low + high) / 2, 1)


def _canonical_volume_stats(board: dict) -> tuple[float | None, float | None, float | None]:
    volumes = []

    for size in board.get("sizes", []):
        volume = size.get("volume_litres")
        try:
            if volume is not None:
                volumes.append(float(volume))
        except (TypeError, ValueError):
            continue

    if not volumes:
        return None, None, None

    return min(volumes), max(volumes), round(sum(volumes) / len(volumes), 1)


def _description_blob(board: dict) -> str:
    values = [
        board.get("category"),
        board.get("description"),
        board.get("model"),
        board.get("model_family"),
    ]
    return " ".join(_normalise(str(value)) for value in values if value)


def _score_canonical_board(board: dict, profile: RiderProfile) -> tuple[float, list[str], str | None]:
    score = 0.0
    reasons = []

    ability = _normalise(profile.ability)
    wave_type = _normalise(profile.wave_type)
    goal = _normalise(profile.goal)
    wave_size = _normalise(profile.wave_size)

    text = _description_blob(board)
    category = _normalise(board.get("category"))
    construction = _normalise(board.get("construction"))

    volume_low, volume_high, volume_avg = _canonical_volume_stats(board)
    target_mid = _profile_volume_mid(profile)

    if target_mid is not None and volume_low is not None and volume_high is not None:
        if volume_low <= target_mid <= volume_high:
            score += 4.0
            reasons.append("has sizes near your target volume")
        else:
            distance = min(abs(target_mid - volume_low), abs(target_mid - volume_high))
            if distance <= 2.0:
                score += 2.0
                reasons.append("has sizes close to your target volume")

    if any(token in goal for token in ["paddle", "catch", "easy", "small", "soft"]):
        if any(token in text for token in ["groveller", "small wave", "easy", "paddle", "forgiving", "foam", "speed", "fish", "hybrid"]):
            score += 3.0
            reasons.append("supports paddle power and easier wave entry")

    if any(token in goal for token in ["turn", "responsive", "performance"]):
        if any(token in text for token in ["performance", "responsive", "drive", "rail", "shortboard", "everyday"]):
            score += 2.0
            reasons.append("still keeps a performance shortboard feel")

    if "beach" in wave_type:
        if any(token in text for token in ["beach", "everyday", "small wave", "groveller", "hybrid", "fish", "pocket", "speed"]):
            score += 2.0
            reasons.append("makes sense for beach break conditions")

    if any(token in wave_type for token in ["reef", "point"]):
        if any(token in text for token in ["reef", "point", "step up", "hold", "drive", "barrel"]):
            score += 2.0
            reasons.append(f"has design cues for {profile.wave_type.lower()}")

    if "intermediate" in ability:
        if not any(token in text for token in ["pro level", "elite", "expert only"]):
            score += 1.0
            reasons.append("does not look too specialist for an intermediate surfer")

    if any(token in wave_size for token in ["2", "3", "4", "small"]):
        if any(token in text for token in ["small wave", "everyday", "groveller", "hybrid", "fish"]):
            score += 1.5

    if construction in ["softboard", "foamie"]:
        score -= 2.0

    description = board.get("description")
    if description:
        score += 0.5

    if not reasons and board.get("description"):
        reasons.append("matches based on manufacturer board profile data")

    return score, reasons, description


def _score_seeded_board(board: dict, profile: RiderProfile) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    ability = _normalise(profile.ability)
    wave_type = _normalise(profile.wave_type)
    goal = _normalise(profile.goal)
    wave_size = _normalise(profile.wave_size)

    board_category = _normalise(board.get("category"))
    ability_tags = [_normalise(x) for x in board.get("ability_tags", [])]
    wave_tags = [_normalise(x) for x in board.get("wave_tags", [])]
    feel_tags = [_normalise(x) for x in board.get("feel_tags", [])]
    goal_tags = [_normalise(x) for x in board.get("goal_tags", [])]

    if ability and ability in ability_tags:
        score += 2.0
        reasons.append(f"suits a {profile.ability.lower()} surfer")

    if wave_type:
        for tag in wave_tags:
            if tag and tag in wave_type:
                score += 2.0
                reasons.append(f"works for {profile.wave_type.lower()}")
                break

    if "beach" in wave_type and board_category in ["hybrid shortboard", "groveller", "fish", "performance fish", "everyday shortboard"]:
        score += 1.0

    if any(token in goal for token in ["paddle", "catch more waves", "speed"]):
        for tag in ["paddles well", "easy speed", "forgiving", "small wave speed"]:
            if tag in feel_tags or tag in goal_tags:
                score += 1.5
                reasons.append("helps with paddle power and easy speed")
                break

    if any(token in goal for token in ["turn", "performance", "hold"]):
        for tag in ["responsive", "hold", "performance", "drive"]:
            if tag in feel_tags or tag in goal_tags:
                score += 1.0
                reasons.append("still gives room to turn properly")
                break

    if wave_size and any(tag in wave_size for tag in wave_tags):
        score += 0.5

    if not reasons and board.get("quivrr_summary"):
        reasons.append(board["quivrr_summary"])

    return score, reasons


def _dedupe_suggestions(scored: list[tuple[float, dict, list[str], str]]) -> list[tuple[float, dict, list[str], str]]:
    seen = set()
    output = []

    for score, board, reasons, source in scored:
        key = (
            _normalise(board.get("brand")),
            _normalise(board.get("model")),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append((score, board, reasons, source))

    return output


def _volume_range_stats(board: dict) -> tuple[float | None, float | None]:
    volume_range = board.get("volume_range") or {}

    try:
        low = volume_range.get("min")
        high = volume_range.get("max")
        if low is None or high is None:
            return None, None
        return float(low), float(high)
    except (TypeError, ValueError, AttributeError):
        return None, None


def _score_generated_board(board: dict, profile: RiderProfile) -> tuple[float, list[str]]:
    score, reasons = _score_seeded_board(board, profile)

    category = _normalise(board.get("category"))
    target_mid = _profile_volume_mid(profile)
    volume_low, volume_high = _volume_range_stats(board)

    preferred_type = _normalise(profile.preferred_board_type)
    ability = _normalise(profile.ability)
    wave_power = _normalise(profile.wave_power)
    lane = daily_driver_lane(board.get("brand"), board.get("model"))

    if category in ["hybrid shortboard", "groveller", "everyday shortboard", "performance fish", "fish"]:
        score += 2.5
        reasons.append("matches the target board category")

    if "daily driver" in preferred_type:
        performance_brief = ability in {"advanced", "expert"} and wave_power in {
            "average to powerful", "powerful"
        }
        if lane == "performance_daily_driver":
            score += 10.0 if performance_brief else 5.0
            reasons.insert(0, "is a proper performance daily driver for better waves")
        elif lane == "forgiving_daily_driver":
            score += 4.0
            reasons.insert(0, "is a forgiving daily driver with extra paddle help")
        elif lane == "hybrid_daily_driver":
            score += 2.0
            reasons.insert(0, "is a forgiving hybrid daily driver")
            if performance_brief:
                score -= 6.0
                reasons.append("is less precise than the performance daily-driver lane")
        elif lane == "small_wave_daily_driver":
            score += 2.0 if wave_power == "weak" else -2.0
            reasons.insert(0, "leans toward a small-wave daily-driver feel")

        performance_order = {
            ("pyzel", "phantom"): 1.8,
            ("js industries", "xero gravity"): 1.7,
            ("js industries", "monsta"): 1.6,
            ("sharp eye", "inferno 72"): 1.5,
            ("channel islands", "better everyday"): 1.4,
            ("js industries", "golden child"): 1.3,
            ("lost", "rad ripper"): 1.1,
            ("lost", "driver 2.0"): 1.0,
        }
        score += performance_order.get((_normalise(board.get("brand")), _normalise(board.get("model"))), 0)

    if board.get("override_applied"):
        score += 2.0
        reasons.append("has Quivrr reviewed board intelligence")

    if target_mid is not None and volume_low is not None and volume_high is not None:
        if volume_low <= target_mid <= volume_high:
            score += 2.0
            reasons.append("has sizes near your target volume")
        else:
            distance = min(abs(target_mid - volume_low), abs(target_mid - volume_high))
            if distance <= 2.0:
                score += 1.0
                reasons.append("has sizes close to your target volume")

    if category in ["step up", "longboard"]:
        score -= 3.0

    return score, reasons


def _brand_limited(scored: list[tuple[float, dict, list[str], str]], limit: int, per_brand_limit: int = 1) -> list[tuple[float, dict, list[str], str]]:
    selected = []
    brand_counts = {}

    for row in scored:
        _, board, _, _ = row
        brand = _normalise(board.get("brand"))

        if brand_counts.get(brand, 0) >= per_brand_limit:
            continue

        selected.append(row)
        brand_counts[brand] = brand_counts.get(brand, 0) + 1

        if len(selected) >= limit:
            return selected

    for row in scored:
        if row in selected:
            continue

        selected.append(row)
        if len(selected) >= limit:
            break

    return selected


def _design_context(board: dict) -> str | None:
    fields = [
        board.get("rocker_notes"),
        board.get("tail_notes"),
        board.get("fin_setup_notes"),
        board.get("construction_notes"),
        board.get("surfer_profile"),
    ]
    values = []
    for value in fields:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text.rstrip(".") + ".")
    return " ".join(values[:3]) or None


def recommend_models(profile: RiderProfile, limit: int = 10) -> list[SuggestedBoard]:
    scored = []
    generated_boards = _load_generated_intelligence()

    for board in generated_boards:
        if not board.get("brand") or not board.get("model"):
            continue

        score, reasons = _score_generated_board(board, profile)
        if score <= 0:
            continue

        scored.append((score, board, reasons, "quivrr_generated_board_intelligence"))

    for board in _load_board_intelligence():
        if not board.get("brand") or not board.get("model"):
            continue

        score, reasons = _score_seeded_board(board, profile)
        if score <= 0:
            continue

        scored.append((score + 3.0, board, reasons, "quivrr_curated_board_intelligence"))

    if not generated_boards:
        for board in _load_canonical_profiles():
            if not board.get("brand") or not board.get("model"):
                continue

            score, reasons, description = _score_canonical_board(board, profile)
            if score <= 0:
                continue

            scored.append((score, board, reasons, "quivrr_canonical_catalogue"))

    scored.sort(key=lambda row: row[0], reverse=True)
    scored = _dedupe_suggestions(scored)
    per_brand_limit = 2 if "daily driver" in _normalise(profile.preferred_board_type) else 1
    scored = _brand_limited(scored, limit=limit, per_brand_limit=per_brand_limit)

    suggestions = []
    for score, board, reasons, source in scored[:limit]:
        # Keep enough score resolution for the inventory layer to preserve suitability order.
        # A hard .96 ceiling made very different boards tie and fall back to source ordering.
        confidence = min(round(0.35 + (score / 30.0), 2), 0.98)
        why = "; ".join(dict.fromkeys(reasons[:4])) or "Fits the selected rider profile."

        lane = daily_driver_lane(board.get("brand"), board.get("model"))
        suggestions.append(
            SuggestedBoard(
                brand=board["brand"],
                model=board["model"],
                category=lane_label(lane) or board.get("category") or "Surfboard",
                confidence=confidence,
                why_it_fits=why,
                description=board.get("model_description") or board.get("description"),
                short_description=board.get("short_description") or board.get("summary"),
                design_context=_design_context(board),
                trade_offs=board.get("trade_offs"),
                volume_range=(
                    f"{board['volume_range']['min']:g}-{board['volume_range']['max']:g}L"
                    if isinstance(board.get("volume_range"), dict)
                    and board["volume_range"].get("min") is not None
                    and board["volume_range"].get("max") is not None
                    else None
                ),
                wave_range=(
                    board.get("wave_range")
                    or board.get("recommended_wave_range")
                    or ", ".join(board.get("wave_tags", []))
                    or None
                ),
                skill_fit=", ".join(board.get("ability_tags", [])) or None,
                source=source,
                board_model_id=board.get("board_model_id") or board.get("boardModelId"),
            )
        )

    return suggestions

def build_recommendation_context(suggested_boards: list[SuggestedBoard]) -> str:
    if not suggested_boards:
        return (
            "Controlled board model context: no controlled board model recommendations were generated. "
            "Do not invent specific board models. Recommend only board categories."
        )

    lines = [
        "Controlled board model context:",
        "Only recommend the specific board models listed below. Do not invent other model names.",
    ]

    for board in suggested_boards:
        lines.append(
            f"- {board.brand} {board.model}: {board.category}. "
            f"Why: {board.why_it_fits}. "
            f"Manufacturer description: {board.short_description or 'Not available'}. "
            f"Design cues: {board.design_context or 'Not specified'}. "
            f"Wave range: {board.wave_range or 'Not specified'}. "
            f"Skill fit: {board.skill_fit or 'Not specified'}. "
            f"Regional availability: {board.available_count} in {board.region or 'unspecified region'} "
            f"({board.manufacturer_direct_count} manufacturer direct, {board.retailer_count} retailer). "
            f"Live source: {board.example_live_source_url or 'None verified'}. "
            f"Price range: {board.price_range or 'Not available'}. "
            f"Trade offs: {board.trade_offs or 'Not specified.'}. "
            f"Source: {board.source}."
        )

    return "\n".join(lines)
