from __future__ import annotations

import re
from dataclasses import dataclass

from app.board_intelligence import BoardIntelligenceRecord, BoardSize
from app.models import RiderProfile
from app.rider_fit import recommend_rider_fit


@dataclass(frozen=True)
class SizeMatchResult:
    size: BoardSize | None
    score: float
    rationale: str | None


def _length_to_inches(length: str | None) -> float | None:
    text = str(length or "").strip().lower().replace('"', "")
    match = re.fullmatch(r"(\d+)\s*'\s*(\d+(?:\.\d+)?)?", text)
    if not match:
        return None
    feet = float(match.group(1))
    inches = float(match.group(2) or 0)
    return feet * 12 + inches


def _target_volume(profile: RiderProfile) -> float | None:
    if profile.target_volume_litres is not None:
        return profile.target_volume_litres
    if profile.current_board_volume_litres is not None:
        return profile.current_board_volume_litres
    if profile.current_volume_litres is not None:
        return profile.current_volume_litres
    fit = recommend_rider_fit(profile)
    if fit:
        return round((fit.volume_low + fit.volume_high) / 2, 1)
    return None


def _score_size(size: BoardSize, profile: RiderProfile) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    target_volume = _target_volume(profile)
    requested_length = _length_to_inches(profile.requested_length)
    size_length = _length_to_inches(size.length)

    if target_volume is not None and size.volume_litres is not None:
        distance = abs(size.volume_litres - target_volume)
        if distance <= 0.6:
            score += 4.0
            reasons.append("volume is right on target")
        elif distance <= 1.5:
            score += 3.0
            reasons.append("volume is very close to target")
        elif distance <= 2.5:
            score += 1.5
            reasons.append("volume stays near target")

    if requested_length is not None and size_length is not None:
        distance = abs(size_length - requested_length)
        if distance == 0:
            score += 3.0
            reasons.append("requested length matches exactly")
        elif distance <= 1.0:
            score += 1.5
            reasons.append("requested length is close")

    if score == 0.0 and size.volume_litres is not None:
        score = 0.5
        reasons.append("valid catalogue size")

    return score, ", ".join(reasons) if reasons else None


def match_board_size(board: BoardIntelligenceRecord, profile: RiderProfile) -> SizeMatchResult:
    if not board.sizes:
        return SizeMatchResult(size=None, score=0.0, rationale=None)

    ranked = []
    for size in board.sizes:
        score, rationale = _score_size(size, profile)
        ranked.append((score, rationale or "", size))

    ranked.sort(
        key=lambda row: (
            -row[0],
            abs((row[2].volume_litres or 0.0) - (_target_volume(profile) or row[2].volume_litres or 0.0)),
            abs((_length_to_inches(row[2].length) or 0.0) - (_length_to_inches(profile.requested_length) or _length_to_inches(row[2].length) or 0.0)),
            row[2].length or "",
        )
    )
    top = ranked[0]
    return SizeMatchResult(size=top[2], score=top[0], rationale=top[1] or None)
