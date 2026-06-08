import json
from pathlib import Path

from app.models import RiderProfile, SuggestedBoard


INTELLIGENCE_PATH = Path(__file__).parent / "knowledge" / "board_intelligence.json"


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


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _score_board(board: dict, profile: RiderProfile) -> tuple[float, list[str]]:
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


def recommend_models(profile: RiderProfile, limit: int = 4) -> list[SuggestedBoard]:
    boards = _load_board_intelligence()
    scored = []

    for board in boards:
        if not board.get("brand") or not board.get("model"):
            continue

        score, reasons = _score_board(board, profile)
        if score <= 0:
            continue

        scored.append((score, board, reasons))

    scored.sort(key=lambda row: row[0], reverse=True)

    suggestions = []
    for score, board, reasons in scored[:limit]:
        confidence = min(round(score / 7.0, 2), 0.95)
        why = "; ".join(dict.fromkeys(reasons[:3])) or board.get("quivrr_summary") or "Fits the selected rider profile."

        suggestions.append(
            SuggestedBoard(
                brand=board["brand"],
                model=board["model"],
                category=board.get("category", "Surfboard"),
                confidence=confidence,
                why_it_fits=why,
                trade_offs=board.get("trade_offs"),
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
            f"Trade offs: {board.trade_offs or 'Not specified.'}"
        )

    return "\n".join(lines)
