from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REPUTATION_PATH = Path(__file__).parent / "knowledge/curated/board_reputation_overrides.json"

def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

@lru_cache(maxsize=1)
def load_reputations() -> dict[tuple[str, str], dict[str, Any]]:
    if not REPUTATION_PATH.exists():
        return {}
    data = json.loads(REPUTATION_PATH.read_text(encoding="utf-8-sig"))
    return {
        (_key(row.get("brand")), _key(row.get("model"))): row
        for row in data.get("boards", [])
    }

def get_reputation(brand: str, model: str) -> dict[str, Any] | None:
    return load_reputations().get((_key(brand), _key(model)))

def compact_reputation(brand: str, model: str) -> str:
    rep = get_reputation(brand, model)
    if not rep:
        return ""
    known = rep.get("knownFor") or []
    known_text = f" Known for {', '.join(known[:3])}." if known else ""
    return f"{brand} {model}: {rep.get('reputationSummary', '').rstrip('.')}.{known_text}"

def _board_name(board: object) -> str:
    return f"{getattr(board, 'brand', '')} {getattr(board, 'model', '')}".strip()

def recommendation_blurbs(boards: list[object], limit: int = 3) -> str:
    parts = []
    for board in boards[:limit]:
        rep = get_reputation(getattr(board, "brand", ""), getattr(board, "model", ""))
        if rep and rep.get("shortPosition"):
            parts.append(f"{_board_name(board)} is {rep['shortPosition']}")
    if not parts:
        return ""
    return "In surf-shop terms, " + "; ".join(parts) + "."

def relationship_expert_intro(source_brand: str, source_model: str, relation: str, canonical: list[object]) -> str | None:
    names = ", ".join(_board_name(row) for row in canonical[:5])
    if not names:
        return None

    source_rep = get_reputation(source_brand, source_model)
    has_candidate_rep = any(get_reputation(getattr(row, "brand", ""), getattr(row, "model", "")) for row in canonical[:5])
    if not source_rep and not has_candidate_rep:
        return None

    source_position = source_rep.get("shortPosition") if source_rep else "the board you asked about"

    if relation == "morePerformanceBoards":
        reply = (
            f"If you like the {source_brand} {source_model} but want something sharper, I’d look at {names}. "
            f"The {source_brand} {source_model} sits more as {source_position}, so the move is toward more hold, response and good-wave intent."
        )
    elif relation == "moreForgivingBoards":
        reply = (
            f"If the {source_brand} {source_model} feels too demanding, I’d make the next step easier with {names}. "
            "The trade-off is usually a little less knife-edge performance for more paddle, speed and forgiveness."
        )
    elif relation == "betterPointBreakBoards":
        reply = (
            f"For point breaks, I’d look past a generic category match and start with {names}. "
            "Those sit closer to the down-the-line, trim-and-flow lane surfers usually want on a running wall."
        )
    elif relation == "morePaddleBoards":
        reply = (
            f"For more paddle than the {source_brand} {source_model}, I’d start with {names}. "
            "Keep the litres close to your current board unless wave count is the priority; extra width and foam help early entry, "
            "but the trade-off is a little less sensitivity and rail precision."
        )
    else:
        reply = (
            f"The closest useful relatives to {source_brand} {source_model} are {names}. "
            "I’m treating this as board-fit advice first, not just a stock filter."
        )

    blurb = recommendation_blurbs(canonical)
    if blurb:
        reply += " " + blurb
    return reply
