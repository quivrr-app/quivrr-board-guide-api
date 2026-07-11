from __future__ import annotations

from dataclasses import dataclass

from app.board_fit_engine import score_board_fit
from app.board_intelligence import BoardIntelligenceRecord, find_board_record, load_board_records
from app.daily_driver_taxonomy import lane_label
from app.models import RiderProfile, SuggestedBoard


TIER_ONE_BRANDS = {
    "channel islands",
    "dhd",
    "firewire",
    "haydenshapes",
    "js industries",
    "lost",
    "pyzel",
    "sharp eye",
}

REGIONAL_BRAND_AFFINITY = {
    "AU": {"js industries", "haydenshapes", "dhd", "chilli", "simon anderson", "firewire"},
    "US": {"lost", "pyzel", "channel islands", "album", "chemistry surfboards", "christenson", "sharp eye"},
    "EU": {"pukas", "channel islands", "pyzel", "lost", "firewire", "christenson"},
    "ID": {"js industries", "channel islands", "pyzel", "dhd", "lost"},
}

CURRENT_YEAR = 2026


@dataclass(frozen=True)
class RankingSignals:
    total: float
    recency: float
    tier_one: float
    regional: float
    preferred_brand: float
    catalogue_depth: float


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def find_board_description(brand: str, model: str, boards: list[dict] | None = None) -> dict | None:
    if boards is not None:
        for board in boards:
            if _normalise(board.get("brand")) == _normalise(brand) and _normalise(board.get("model")) == _normalise(model):
                description = board.get("model_description") or board.get("description") or board.get("summary")
                if not description:
                    return None
                return {
                    "description": description,
                    "shortDescription": board.get("short_description") or board.get("summary"),
                    "sourceUrl": board.get("source_url") or board.get("official_product_url"),
                    "sourceType": board.get("source_type") or "canonical_catalogue",
                }
        return None

    board = find_board_record(brand, model)
    if not board or not board.description:
        return None
    return {
        "description": board.description,
        "shortDescription": board.short_description,
        "sourceUrl": board.official_product_url,
        "sourceType": board.source_type or "canonical_catalogue",
    }


def _brand_limited(
    scored: list[tuple[float, BoardIntelligenceRecord, tuple[str, ...], object, RankingSignals]],
    limit: int,
    per_brand_limit: int = 1,
) -> list[tuple[float, BoardIntelligenceRecord, tuple[str, ...], object, RankingSignals]]:
    selected = []
    brand_counts: dict[str, int] = {}

    for row in scored:
        _, board, _, _, _ = row
        brand = _normalise(board.brand)
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


def _design_context(board: BoardIntelligenceRecord) -> str | None:
    values = list(board.strengths[:2]) + list(board.trade_offs[:1])
    if not values and board.description:
        values = [board.description]
    context = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in context:
            context.append(text.rstrip(".") + ".")
    return " ".join(context[:3]) or None


def _size_label(size) -> str | None:
    if not size:
        return None
    if size.length and size.volume_litres is not None:
        return f"{size.length} | {size.volume_litres:g}L"
    if size.length:
        return size.length
    if size.volume_litres is not None:
        return f"{size.volume_litres:g}L"
    return None


def _preferred_brand_signal(board: BoardIntelligenceRecord, profile: RiderProfile) -> float:
    preferred = {_normalise(item) for item in (profile.preferred_brands or []) if _normalise(item)}
    return 0.12 if _normalise(board.brand) in preferred else 0.0


def _preferred_type_aligned(board: BoardIntelligenceRecord, profile: RiderProfile) -> bool:
    preferred = _normalise(profile.preferred_board_type)
    if not preferred:
        return True
    haystack = " ".join(filter(None, [
        _normalise(board.category),
        _normalise(board.primary_category),
        _normalise(board.lane),
        _normalise(board.model),
    ]))
    if "fish" in preferred:
        return any(token in haystack for token in ["fish", "twin"])
    if "hybrid" in preferred:
        return any(token in haystack for token in ["hybrid", "daily_driver", "everyday"])
    if "daily driver" in preferred or "daily shortboard" in preferred:
        return any(token in haystack for token in ["daily_driver", "everyday", "hybrid"])
    if "shortboard" in preferred:
        return any(token in haystack for token in ["shortboard", "daily_driver", "performance"])
    return True


def _regional_signal(board: BoardIntelligenceRecord, profile: RiderProfile) -> float:
    region = _normalise(profile.region).upper()
    if not region:
        return 0.0
    return 0.1 if _normalise(board.brand) in REGIONAL_BRAND_AFFINITY.get(region, set()) else 0.0


def _tier_one_signal(board: BoardIntelligenceRecord) -> float:
    return 0.06 if _normalise(board.brand) in TIER_ONE_BRANDS else 0.0


def _catalogue_depth_signal(board: BoardIntelligenceRecord) -> float:
    signal = 0.0
    if board.graph_eligible:
        signal += 0.02
    if board.source_confidence >= 0.9:
        signal += 0.02
    if len(board.sizes) >= 4:
        signal += 0.01
    return signal


def _recency_signal(board: BoardIntelligenceRecord) -> float:
    if board.is_discontinued:
        return -0.1
    if board.release_year:
        age = CURRENT_YEAR - board.release_year
        if age <= 2:
            return 0.15
        if age <= 5:
            return 0.07
        return 0.0
    if board.is_current_model:
        return 0.1
    if board.model_generation and board.is_current_model is not False:
        return 0.04
    return 0.0


def _secondary_signals(board: BoardIntelligenceRecord, profile: RiderProfile) -> RankingSignals:
    if not _preferred_type_aligned(board, profile):
        return RankingSignals(
            total=-0.05,
            recency=0.0,
            tier_one=0.0,
            regional=0.0,
            preferred_brand=0.0,
            catalogue_depth=-0.05,
        )
    if _normalise(profile.preferred_board_type):
        preferred_brand = _preferred_brand_signal(board, profile)
        return RankingSignals(
            total=round(preferred_brand, 3),
            recency=0.0,
            tier_one=0.0,
            regional=0.0,
            preferred_brand=preferred_brand,
            catalogue_depth=0.0,
        )
    recency = _recency_signal(board)
    tier_one = _tier_one_signal(board)
    regional = _regional_signal(board, profile)
    preferred_brand = _preferred_brand_signal(board, profile)
    catalogue_depth = _catalogue_depth_signal(board)
    return RankingSignals(
        total=round(recency + tier_one + regional + preferred_brand + catalogue_depth, 3),
        recency=recency,
        tier_one=tier_one,
        regional=regional,
        preferred_brand=preferred_brand,
        catalogue_depth=catalogue_depth,
    )


def recommend_models(profile: RiderProfile, limit: int = 10) -> list[SuggestedBoard]:
    scored_rows = []
    for board in load_board_records():
        fit = score_board_fit(board, profile)
        if fit.hard_exclusions or fit.score.total <= 0:
            continue
        scored_rows.append((fit.score.total, board, fit.reasons, fit, _secondary_signals(board, profile)))

    def base_sort_key(row):
        return (
            -row[0],
            -row[3].score.evidence_quality,
            -row[3].score.goal_fit,
            row[1].brand.lower(),
            row[1].model.lower(),
        )

    def weighted_sort_key(row):
        return (
            -round(row[0], 1),
            -row[0],
            -row[4].total,
            -row[3].score.evidence_quality,
            -row[3].score.goal_fit,
            row[1].brand.lower(),
            row[1].model.lower(),
        )

    scored_rows.sort(key=base_sort_key)
    per_brand_limit = 2 if "daily driver" in _normalise(profile.preferred_board_type) else 1
    shortlist = _brand_limited(scored_rows, limit=max(limit * 2, limit), per_brand_limit=per_brand_limit)
    shortlist.sort(key=weighted_sort_key)
    scored_rows = _brand_limited(shortlist, limit=limit, per_brand_limit=per_brand_limit)

    suggestions = []
    for total, board, reasons, fit, _signals in scored_rows[:limit]:
        confidence = min(round(0.4 + (total / 10.0), 2), 0.98)
        why = "; ".join(dict.fromkeys(reasons[:4])) or "Fits the selected rider profile."
        lane = board.lane
        size = fit.size_match.size
        volume_range = (
            f"{board.volume_min_litres:g}-{board.volume_max_litres:g}L"
            if board.volume_min_litres is not None and board.volume_max_litres is not None
            else None
        )
        wave_range = (
            f"{board.wave_height_min_ft:g}-{board.wave_height_max_ft:g}ft"
            if board.wave_height_min_ft is not None and board.wave_height_max_ft is not None
            else ", ".join(board.wave_types or board.wave_tags) or None
        )
        suggestions.append(
            SuggestedBoard(
                brand=board.brand,
                model=board.model,
                category=lane_label(lane) or board.category or board.primary_category or "Surfboard",
                confidence=confidence,
                why_it_fits=why,
                description=board.description,
                short_description=board.short_description,
                design_context=_design_context(board),
                trade_offs="; ".join(board.trade_offs) or None,
                suggested_size=_size_label(size),
                volume_range=volume_range,
                wave_range=wave_range,
                skill_fit=", ".join(board.ability_tags) or None,
                source="quivrr_normalized_board_intelligence",
                board_model_id=board.board_model_id,
                source_product_url=board.official_product_url,
                selected_volume_litres=size.volume_litres if size else None,
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
        "Only recommend the specific board models listed below. Do not invent, reorder, or replace model names.",
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
