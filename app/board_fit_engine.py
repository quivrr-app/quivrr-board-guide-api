from __future__ import annotations

from dataclasses import dataclass

from app.board_intelligence import BoardIntelligenceRecord
from app.board_size_matcher import SizeMatchResult, match_board_size
from app.models import RecommendationScore, RiderProfile


@dataclass(frozen=True)
class BoardFitResult:
    board: BoardIntelligenceRecord
    score: RecommendationScore
    reasons: tuple[str, ...]
    hard_exclusions: tuple[str, ...]
    size_match: SizeMatchResult


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _contains_any(values: tuple[str, ...], tokens: set[str]) -> bool:
    haystack = " ".join(_normalise(value) for value in values)
    return any(token in haystack for token in tokens)


def _preferred_type_matches(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[float, str | None]:
    preferred = _normalise(profile.preferred_board_type)
    category = _normalise(board.category)
    primary = _normalise(board.primary_category)
    lane = _normalise(board.lane)

    if not preferred:
        return 0.4, None
    if "daily driver" in preferred and any(token in " ".join([category, primary, lane]) for token in ["daily_driver", "everyday", "hybrid_daily_driver", "performance_daily_driver", "forgiving_daily_driver", "small_wave_daily_driver"]):
        return 1.0, "matches the daily-driver lane"
    if "daily driver" in preferred and any(token in " ".join([category, primary, lane]) for token in ["hybrid shortboard", "performance shortboard"]):
        return 0.65, "sits close to the daily-driver lane"
    if "fish" in preferred and "fish" in category:
        return 1.0, "stays in the fish lane"
    if "step" in preferred and "step" in f"{category} {primary}":
        return 1.0, "matches the step-up lane"
    if "shortboard" in preferred and any(token in f"{category} {primary}" for token in ["shortboard", "daily_driver"]):
        return 0.85, "sits in a shortboard lane"
    return 0.1, None


def _ability_fit(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[float, str | None]:
    ability = _normalise(profile.ability)
    if not ability:
        return 0.45, None

    tags = {_normalise(value) for value in board.ability_tags}
    if not tags:
        if "performance_daily_driver" in _normalise(board.lane) and ability in {"beginner", "intermediate"}:
            return 0.35, "leans performance-focused"
        return 0.55, None

    if ability in tags:
        return 1.0, f"suits a {profile.ability.lower()} surfer"
    if ability == "advanced" and "intermediate" in tags:
        return 0.8, "sits close to your ability range"
    if ability == "intermediate" and "advanced" in tags:
        return 0.7, "gives room to grow without being wildly off-brief"
    return 0.2, None


def _condition_fit(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[float, str | None]:
    wave_type = _normalise(profile.wave_type)
    wave_power = _normalise(profile.wave_power)
    category = _normalise(board.category)
    tags = " ".join(_normalise(value) for value in (board.wave_tags + board.wave_types + board.feel_tags))

    score = 0.45
    reasons: list[str] = []

    if wave_type:
        if any(token in wave_type and token in tags for token in ["beach", "reef", "point"]):
            score += 0.35
            reasons.append(f"fits {profile.wave_type.lower()}")
        elif "beach" in wave_type and any(token in category for token in ["fish", "groveller", "daily"]):
            score += 0.2
            reasons.append("fits beach-break everyday surf")

    if wave_power:
        if wave_power == "weak" and any(token in f"{category} {tags}" for token in ["fish", "groveller", "small wave", "easy speed"]):
            score += 0.2
            reasons.append("supports weaker surf")
        if wave_power in {"average to powerful", "powerful"} and any(token in f"{category} {tags}" for token in ["performance", "reef", "point", "hold", "drive"]):
            score += 0.2
            reasons.append("holds up in stronger surf")

    return min(score, 1.0), reasons[0] if reasons else None


def _goal_fit(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[float, str | None]:
    goal_text = " ".join(
        _normalise(value)
        for value in [profile.goal, profile.desired_feel, profile.current_board_feedback]
        if value
    )
    if not goal_text:
        return 0.45, None

    tags = " ".join(_normalise(value) for value in board.feel_tags)
    category = _normalise(board.category)
    if any(token in goal_text for token in ["paddle", "easy", "forgiving", "catch more"]):
        if any(token in f"{tags} {category}" for token in ["paddle", "forgiving", "easy speed", "fish", "hybrid"]):
            return 1.0, "supports paddle help and easier wave entry"
        return 0.25, None
    if any(token in goal_text for token in ["performance", "responsive", "turn", "hold", "drive"]):
        if any(token in f"{tags} {category}" for token in ["responsive", "drive", "hold", "performance"]):
            return 1.0, "keeps a stronger performance ceiling"
        return 0.3, None
    return 0.45, None


def _transition_fit(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[float, str | None]:
    if not profile.current_board:
        return 0.45, None
    current = _normalise(profile.current_board)
    board_name = _normalise(f"{board.brand} {board.model}")
    if board_name in current:
        return 0.15, "is the same board you already ride"
    if profile.current_volume_litres and board.volume_min_litres and board.volume_max_litres:
        midpoint = (board.volume_min_litres + board.volume_max_litres) / 2
        if abs(midpoint - profile.current_volume_litres) <= 2.5:
            return 0.8, "keeps sizing close to your current board"
    return 0.5, None


def _hard_exclusions(board: BoardIntelligenceRecord, profile: RiderProfile) -> tuple[str, ...]:
    exclusions: list[str] = []
    preferred = _normalise(profile.preferred_board_type)
    ability = _normalise(profile.ability)
    wave_power = _normalise(profile.wave_power)
    category_blob = " ".join([_normalise(board.category), _normalise(board.primary_category), _normalise(board.lane)])

    if "daily driver" in preferred and any(token in category_blob for token in ["step_up", "step up", "longboard", "mid_length", "mid length"]):
        exclusions.append("outside the daily-driver lane")
    if "daily driver" in preferred and any(token in category_blob for token in ["groveller", "longboard"]) and wave_power in {"average to powerful", "powerful"}:
        exclusions.append("too small-wave biased for the stated daily-driver brief")
    if "daily driver" in preferred and "fish" in category_blob and wave_power in {"average to powerful", "powerful"}:
        exclusions.append("fish lane does not match the stated daily-driver brief")
    if ability == "beginner" and any(token in category_blob for token in ["performance_daily_driver", "high performance", "step_up"]):
        exclusions.append("too demanding for a beginner brief")
    if wave_power == "weak" and "step_up" in category_blob:
        exclusions.append("step-up boards are out of scope for weak surf")
    return tuple(exclusions)


def score_board_fit(board: BoardIntelligenceRecord, profile: RiderProfile) -> BoardFitResult:
    ability_fit, ability_reason = _ability_fit(board, profile)
    condition_fit, condition_reason = _condition_fit(board, profile)
    goal_fit, goal_reason = _goal_fit(board, profile)
    transition_fit, transition_reason = _transition_fit(board, profile)
    type_fit, type_reason = _preferred_type_matches(board, profile)
    size_match = match_board_size(board, profile)

    volume_fit = min(size_match.score / 4.0, 1.0) if size_match.size else 0.35
    evidence_quality = min(
        1.0,
        board.source_confidence
        + (0.1 if board.curated else 0.0)
        + (0.05 if board.graph_eligible else 0.0)
        - (0.1 if board.unclassified else 0.0),
    )
    hard_exclusions = _hard_exclusions(board, profile)
    lane = _normalise(board.lane)
    ability = _normalise(profile.ability)
    wave_power = _normalise(profile.wave_power)
    performance_daily_driver_brief = (
        "daily driver" in _normalise(profile.preferred_board_type)
        and ability in {"advanced", "expert"}
        and wave_power in {"average to powerful", "powerful"}
    )

    penalties = list(hard_exclusions)
    if board.unclassified:
        penalties.append("classification coverage is unverified for this model")
    if not board.description:
        penalties.append("missing manufacturer description")

    total = (
        ability_fit * 1.7
        + condition_fit * 1.6
        + volume_fit * 1.4
        + goal_fit * 1.5
        + transition_fit * 0.8
        + type_fit * 2.2
        + evidence_quality * 1.0
    )
    if performance_daily_driver_brief and lane == "performance_daily_driver":
        total += 1.2
    elif performance_daily_driver_brief and lane == "hybrid_daily_driver":
        total -= 0.8
    if hard_exclusions:
        total -= 4.0

    reasons = tuple(
        reason
        for reason in [
            type_reason,
            ability_reason,
            condition_reason,
            goal_reason,
            transition_reason,
            size_match.rationale,
        ]
        if reason
    )

    return BoardFitResult(
        board=board,
        score=RecommendationScore(
            total=round(total, 3),
            ability_fit=round(ability_fit, 3),
            condition_fit=round(condition_fit, 3),
            volume_fit=round(volume_fit, 3),
            goal_fit=round(goal_fit, 3),
            transition_fit=round(transition_fit, 3),
            evidence_quality=round(evidence_quality, 3),
            penalties=penalties,
        ),
        reasons=reasons,
        hard_exclusions=hard_exclusions,
        size_match=size_match,
    )
