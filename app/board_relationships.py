from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.board_intelligence import board_key


GRAPH_PATH = Path(__file__).parent / "knowledge" / "generated" / "board_relationship_graph_v3.json"

RELATIONSHIP_TYPE_MAP = {
    "similar": "similarBoards",
    "similarBoards": "similarBoards",
    "similar_boards": "similarBoards",
    "more_performance": "morePerformanceBoards",
    "morePerformanceBoards": "morePerformanceBoards",
    "more_forgiving": "moreForgivingBoards",
    "moreForgivingBoards": "moreForgivingBoards",
    "more_paddle": "morePaddleBoards",
    "morePaddleBoards": "morePaddleBoards",
    "more_hold": "moreHoldBoards",
    "moreHoldBoards": "moreHoldBoards",
    "more_release": "moreReleaseBoards",
    "moreReleaseBoards": "moreReleaseBoards",
    "step_up_from": "stepUpFromBoards",
    "stepUpFromBoards": "stepUpFromBoards",
    "step_down_from": "stepDownFromBoards",
    "stepDownFromBoards": "stepDownFromBoards",
    "fish_alternative": "fishAlternativeBoards",
    "fishAlternativeBoards": "fishAlternativeBoards",
    "shortboard_alternative": "shortboardAlternativeBoards",
    "shortboardAlternativeBoards": "shortboardAlternativeBoards",
    "better_small_wave": "betterSmallWaveBoards",
    "betterSmallWaveBoards": "betterSmallWaveBoards",
    "better_good_wave": "betterGoodWaveBoards",
    "betterGoodWaveBoards": "betterGoodWaveBoards",
    "better_beach_break": "betterBeachBreakBoards",
    "betterBeachBreakBoards": "betterBeachBreakBoards",
    "better_reef": "betterReefBoards",
    "betterReefBoards": "betterReefBoards",
    "better_point_break": "betterPointBreakBoards",
    "betterPointBreakBoards": "betterPointBreakBoards",
    "mid_length_alternative": "midLengthAlternativeBoards",
    "midLengthAlternativeBoards": "midLengthAlternativeBoards",
    "upgrade": "upgradeBoards",
    "upgradeBoards": "upgradeBoards",
    "downgrade": "downgradeBoards",
    "downgradeBoards": "downgradeBoards",
}


def normalize_relationship_type(value: str | None) -> str | None:
    if value is None:
        return None
    return RELATIONSHIP_TYPE_MAP.get(value)


@lru_cache(maxsize=1)
def load_relationship_records() -> list[dict]:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8-sig")).get("boards", [])


def relationship_lookup() -> dict[str, dict]:
    return {
        board_key(row.get("brand"), row.get("model")): row
        for row in load_relationship_records()
        if row.get("brand") and row.get("model")
    }


def relationship_validation_counts() -> dict[str, int]:
    rows = load_relationship_records()
    valid_keys = {
        board_key(row.get("brand"), row.get("model"))
        for row in rows
        if row.get("brand") and row.get("model")
    }
    invalid_references = 0
    self_references = 0
    edges = 0
    typed_edges: dict[str, int] = {}

    for row in rows:
        source_key = board_key(row.get("brand"), row.get("model"))
        for relation, related_rows in (row.get("relationships") or {}).items():
            typed_edges[relation] = typed_edges.get(relation, 0) + len(related_rows or [])
            for related in related_rows or []:
                edges += 1
                target_key = board_key(related.get("brand"), related.get("model"))
                if target_key == source_key:
                    self_references += 1
                if target_key not in valid_keys:
                    invalid_references += 1

    counts = {
        "boards": len(rows),
        "edges": edges,
        "invalid_references": invalid_references,
        "self_references": self_references,
        "relationship_types": len(typed_edges),
    }
    for relation in sorted(typed_edges):
        counts[f"type::{relation}"] = typed_edges[relation]
    return counts
