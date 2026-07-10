from __future__ import annotations

from dataclasses import dataclass

from app.board_fit_engine import BoardFitResult, score_board_fit
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
    left_fit = score_board_fit(left, profile)
    right_fit = score_board_fit(right, profile)

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
        if left_fit.size_match.size.volume_litres != right_fit.size_match.size.volume_litres:
            differences.append(
                f"Best matched size lands around {left_fit.size_match.size.volume_litres:g}L for {left.brand} {left.model} "
                f"versus {right_fit.size_match.size.volume_litres:g}L for {right.brand} {right.model}."
            )

    if left.lane and right.lane and left.lane != right.lane:
        differences.append(
            f"{left.brand} {left.model} sits in the {left.lane.replace('_', ' ')} lane while "
            f"{right.brand} {right.model} leans {right.lane.replace('_', ' ')}."
        )

    ordered = tuple(
        row[0]
        for row in sorted(
            [(left, left_fit.score.total), (right, right_fit.score.total)],
            key=lambda item: (-item[1], item[0].brand.lower(), item[0].model.lower()),
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
    )
    return ComparisonEngineResult(
        comparison=comparison,
        left_fit=left_fit,
        right_fit=right_fit,
        ordered_boards=ordered,
    )
