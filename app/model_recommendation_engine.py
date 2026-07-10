from __future__ import annotations

from app.board_fit_engine import score_board_fit
from app.board_intelligence import BoardIntelligenceRecord, find_board_record, load_board_records
from app.daily_driver_taxonomy import lane_label
from app.models import RiderProfile, SuggestedBoard


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


def _brand_limited(scored: list[tuple[float, BoardIntelligenceRecord, tuple[str, ...], object]], limit: int, per_brand_limit: int = 1) -> list[tuple[float, BoardIntelligenceRecord, tuple[str, ...], object]]:
    selected = []
    brand_counts: dict[str, int] = {}

    for row in scored:
        _, board, _, _ = row
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


def recommend_models(profile: RiderProfile, limit: int = 10) -> list[SuggestedBoard]:
    scored_rows = []
    for board in load_board_records():
        fit = score_board_fit(board, profile)
        if fit.hard_exclusions or fit.score.total <= 0:
            continue
        scored_rows.append((fit.score.total, board, fit.reasons, fit))

    scored_rows.sort(
        key=lambda row: (
            -row[0],
            -row[3].score.evidence_quality,
            -row[3].score.goal_fit,
            row[1].brand.lower(),
            row[1].model.lower(),
        )
    )
    per_brand_limit = 2 if "daily driver" in _normalise(profile.preferred_board_type) else 1
    scored_rows = _brand_limited(scored_rows, limit=limit, per_brand_limit=per_brand_limit)

    suggestions = []
    for total, board, reasons, fit in scored_rows[:limit]:
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
