from __future__ import annotations

from dataclasses import dataclass

from app.board_fit_engine import BoardFitResult, score_board_fit
from app.board_dna import find_board_dna
from app.board_intelligence import BoardIntelligenceRecord, find_board_record
from app.models import BoardComparison, BoardReference, RiderProfile


@dataclass(frozen=True)
class ComparisonEngineResult:
    comparison: BoardComparison
    left_fit: BoardFitResult | None
    right_fit: BoardFitResult | None
    ordered_boards: tuple[BoardIntelligenceRecord, ...]


def _common_values(left: tuple[str, ...], right: tuple[str, ...]) -> list[str]:
    return sorted(set(left).intersection(right))


DNA_COMPARISON_METRICS = (
    "paddle", "speed_generation", "drive", "release", "hold",
    "forgiveness", "sensitivity",
)


def _dna_summary(board: dict | None, ability: str | None) -> dict:
    if not board:
        return {}
    ability_key = (ability or "").strip().lower()
    return {
        "family": board["public_family"],
        "detailed_category": board["primary_category"],
        "behaviour": {key: board["behaviour"][key] for key in DNA_COMPARISON_METRICS},
        "wave_context": dict(board["conditions"]),
        "ability_fit": board["rider_fit"].get(ability_key),
        "quiver_roles": list(board.get("quiver_roles") or []),
        "fin_configurations": list(board["physical_design"].get("fin_configurations") or []),
        "confidence": board["evidence"]["behaviour_confidence"],
    }


def _dna_tradeoffs(left: dict | None, right: dict | None) -> list[str]:
    if not left or not right:
        return []
    rows = []
    left_name = f"{left['brand']} {left['model']}"
    right_name = f"{right['brand']} {right['model']}"
    deltas = sorted(
        ((metric, left["behaviour"][metric] - right["behaviour"][metric]) for metric in DNA_COMPARISON_METRICS),
        key=lambda row: (-abs(row[1]), row[0]),
    )
    for metric, delta in deltas[:3]:
        if delta > 0:
            rows.append(f"{left_name} offers more {metric.replace('_', ' ')} ({left['behaviour'][metric]} vs {right['behaviour'][metric]}).")
        elif delta < 0:
            rows.append(f"{right_name} offers more {metric.replace('_', ' ')} ({right['behaviour'][metric]} vs {left['behaviour'][metric]}).")
    if left["public_family"] != right["public_family"]:
        rows.append(
            f"Family trade-off: {left_name} is {left['public_family'].replace('_', ' ')} while "
            f"{right_name} is {right['public_family'].replace('_', ' ')}."
        )
    return rows


def compare_board_models(
    left_brand: str,
    left_model: str,
    right_brand: str,
    right_model: str,
    profile: RiderProfile | None = None,
) -> ComparisonEngineResult | None:
    left = find_board_record(left_brand, left_model)
    right = find_board_record(right_brand, right_model)
    if not left or not right:
        return None

    profile = profile or RiderProfile()
    # Phase 3 manufacturer-expansion models have official descriptions, images
    # and standard sizes, but no official public-family evidence.  Preserve
    # their usefulness for factual comparison without letting generic scoring
    # turn missing classification into an apparent performance verdict.
    if (
        left.source_type == "official_manufacturer_canonical_dry_run"
        or right.source_type == "official_manufacturer_canonical_dry_run"
    ):
        size_note = []
        if left.volume_min_litres is not None and right.volume_min_litres is not None:
            size_note.append(
                f"Published standard-size volume ranges are {left.volume_min_litres:g}-{left.volume_max_litres:g}L "
                f"for {left.brand} {left.model} and {right.volume_min_litres:g}-{right.volume_max_litres:g}L "
                f"for {right.brand} {right.model}."
            )
        comparison = BoardComparison(
            board_a=BoardReference(brand=left.brand, model=left.model),
            board_b=BoardReference(brand=right.brand, model=right.model),
            similarities=["Both have an official manufacturer description, product URL and approved standard-size evidence."],
            differences=size_note,
            rider_specific_conclusion=(
                "Bodhi will not rank these models for rider fit until official public-family evidence is available."
            ),
            evidence_confidence=min(left.source_confidence, right.source_confidence),
        )
        return ComparisonEngineResult(
            comparison=comparison,
            left_fit=None,
            right_fit=None,
            ordered_boards=(left, right),
        )

    left_fit = score_board_fit(left, profile)
    right_fit = score_board_fit(right, profile)
    left_dna = find_board_dna(left.brand, left.model)
    right_dna = find_board_dna(right.brand, right.model)
    dna_tradeoffs = _dna_tradeoffs(left_dna, right_dna)

    similarities = []
    differences = []
    better_for_left = []
    better_for_right = []

    if left.category and left.category == right.category:
        similarities.append(f"Both sit in the {left.category} lane.")
    shared_wave_types = _common_values(left.wave_types, right.wave_types)
    if shared_wave_types:
        similarities.append(f"Both target {', '.join(shared_wave_types[:3])} surf.")
    shared_feel = _common_values(left.feel_tags, right.feel_tags)
    if shared_feel:
        similarities.append(f"Both share feel cues like {', '.join(shared_feel[:3])}.")

    if left_fit.score.goal_fit > right_fit.score.goal_fit:
        better_for_left.append("Stronger match for the stated feel or progression goal.")
    elif right_fit.score.goal_fit > left_fit.score.goal_fit:
        better_for_right.append("Stronger match for the stated feel or progression goal.")

    if left_fit.score.condition_fit > right_fit.score.condition_fit:
        better_for_left.append("Better aligned with the stated conditions.")
    elif right_fit.score.condition_fit > left_fit.score.condition_fit:
        better_for_right.append("Better aligned with the stated conditions.")

    if left_fit.score.ability_fit > right_fit.score.ability_fit:
        better_for_left.append("Better aligned with current ability.")
    elif right_fit.score.ability_fit > left_fit.score.ability_fit:
        better_for_right.append("Better aligned with current ability.")

    if left_fit.size_match.size and right_fit.size_match.size:
        left_volume = left_fit.size_match.size.volume_litres
        right_volume = right_fit.size_match.size.volume_litres
        if left_volume is not None and right_volume is not None and left_volume != right_volume:
            differences.append(
                f"Best matched size lands around {left_volume:g}L for {left.brand} {left.model} "
                f"versus {right_volume:g}L for {right.brand} {right.model}."
            )

    if left.lane and right.lane and left.lane != right.lane:
        differences.append(
            f"{left.brand} {left.model} sits in the {left.lane.replace('_', ' ')} lane while "
            f"{right.brand} {right.model} leans {right.lane.replace('_', ' ')}."
        )
    differences.extend(dna_tradeoffs)

    ordered = tuple(
        row[0]
        for row in sorted(
            [(left, left_fit), (right, right_fit)],
            key=lambda item: (
                bool(item[1].hard_exclusions),
                -item[1].score.total,
                item[0].brand.lower(),
                item[0].model.lower(),
            ),
        )
    )
    top = ordered[0]
    rider_specific = f"For this rider brief, {top.brand} {top.model} is the cleaner overall fit."

    comparison = BoardComparison(
        board_a=BoardReference(brand=left.brand, model=left.model),
        board_b=BoardReference(brand=right.brand, model=right.model),
        similarities=similarities,
        differences=differences,
        better_for_board_a=better_for_left,
        better_for_board_b=better_for_right,
        rider_specific_conclusion=rider_specific,
        evidence_confidence=round((left_fit.score.evidence_quality + right_fit.score.evidence_quality) / 2, 2),
        board_a_dna=_dna_summary(left_dna, profile.ability),
        board_b_dna=_dna_summary(right_dna, profile.ability),
        dna_tradeoffs=dna_tradeoffs,
    )
    return ComparisonEngineResult(
        comparison=comparison,
        left_fit=left_fit,
        right_fit=right_fit,
        ordered_boards=ordered,
    )
