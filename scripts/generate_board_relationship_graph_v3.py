from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.board_dna import dna_similarity


DNA_PATH = ROOT / "app" / "knowledge" / "board_dna_v1.json"
OUTPUT_PATH = ROOT / "app" / "knowledge" / "generated" / "board_relationship_graph_v3.json"
CURATED_BASE_PATH = ROOT / "app" / "knowledge" / "generated" / "board_relationship_graph.json"

RELATIONS = {
    "similarBoards": "closest_match",
    "morePaddleBoards": "more_paddle",
    "moreForgivingBoards": "more_forgiving",
    "morePerformanceBoards": "more_performance",
    "moreHoldBoards": "more_hold",
    "moreReleaseBoards": "more_release",
    "betterSmallWaveBoards": "better_weak_waves",
    "betterGoodWaveBoards": "better_powerful_waves",
    "betterPointBreakBoards": "better_point_break",
    "betterReefBoards": "better_reef",
    "stepUpFromBoards": "step_up_from",
    "stepDownFromBoards": "step_down_from",
    "fishAlternativeBoards": "fish_alternative",
    "midLengthAlternativeBoards": "mid_length_alternative",
}


def _delta(source: dict, target: dict, section: str, metric: str) -> int:
    return target[section][metric] - source[section][metric]


def _eligible(relation: str, source: dict, target: dict) -> bool:
    if source["canonical_model_id"] == target["canonical_model_id"]:
        return False
    if relation == "closest_match": return source["public_family"] == target["public_family"]
    if relation == "more_paddle": return _delta(source, target, "behaviour", "paddle") >= 1
    if relation == "more_forgiving": return _delta(source, target, "behaviour", "forgiveness") >= 1
    if relation == "more_performance": return _delta(source, target, "behaviour", "sensitivity") >= 1 and _delta(source, target, "behaviour", "projection") >= 0
    if relation == "more_hold": return _delta(source, target, "behaviour", "hold") >= 1
    if relation == "more_release": return _delta(source, target, "behaviour", "release") >= 1
    if relation == "better_weak_waves": return _delta(source, target, "conditions", "weak_waves") >= 1
    if relation == "better_powerful_waves": return _delta(source, target, "conditions", "powerful_waves") >= 1
    if relation == "better_point_break": return _delta(source, target, "conditions", "point_break") >= 1
    if relation == "better_reef": return _delta(source, target, "conditions", "reef_break") >= 1
    if relation == "step_up_from": return target["public_family"] == "step_up" and source["public_family"] != "step_up"
    if relation == "step_down_from": return source["public_family"] in {"step_up", "performance_shortboard"} and target["public_family"] in {"daily_driver", "groveller"}
    if relation == "fish_alternative": return target["public_family"] == "fish" and source["public_family"] != "fish"
    if relation == "mid_length_alternative": return target["public_family"] == "mid_length" and source["public_family"] != "mid_length"
    return False


def _edge(source: dict, target: dict, relation: str) -> dict:
    differences = {
        "paddle": _delta(source, target, "behaviour", "paddle"),
        "stability": _delta(source, target, "behaviour", "stability"),
        "sensitivity": _delta(source, target, "behaviour", "sensitivity"),
        "hold": _delta(source, target, "behaviour", "hold"),
        "release": _delta(source, target, "behaviour", "release"),
    }
    changed = sorted(((name, value) for name, value in differences.items() if value), key=lambda item: -abs(item[1]))[:3]
    reason = ", ".join(f"{name.replace('_', ' ')} {'+' if value > 0 else ''}{value}" for name, value in changed) or "Very similar governed behaviour profile"
    confidence = target["evidence"]["behaviour_confidence"]
    return {
        "brand": target["brand"], "model": target["model"],
        "canonical_model_id": target["canonical_model_id"],
        "relationship_type": relation,
        "relationshipType": relation,
        "similarity": dna_similarity(source, target),
        "reason": reason.capitalize() + ".",
        "dna_differences": differences,
        "confidence": confidence,
        "source": "board_dna_v1",
    }


def main() -> None:
    models = json.loads(DNA_PATH.read_text(encoding="utf-8"))["models"]
    model_by_key = {(row["brand"].lower(), row["model"].lower()): row for row in models}
    curated_payload = json.loads(CURATED_BASE_PATH.read_text(encoding="utf-8")) if CURATED_BASE_PATH.exists() else {"boards": []}
    curated_by_key = {(row["brand"].lower(), row["model"].lower()): row for row in curated_payload.get("boards", [])}
    boards = []
    for source in models:
        relationships = {}
        for output_name, relation in RELATIONS.items():
            candidates = [target for target in models if _eligible(relation, source, target)]
            candidates.sort(key=lambda target: (-dna_similarity(source, target), target["brand"].lower(), target["model"].lower()))
            selected = []
            seen = set()
            curated_source = curated_by_key.get((source["brand"].lower(), source["model"].lower()), {})
            for existing in (curated_source.get("relationships") or {}).get(output_name, []):
                target = model_by_key.get((existing.get("brand", "").lower(), existing.get("model", "").lower()))
                if not target:
                    continue
                edge = _edge(source, target, relation)
                edge["reason"] = existing.get("reason") or edge["reason"]
                edge["source"] = "curated_relationship_preserved_with_board_dna_v1"
                selected.append(edge)
                seen.add(target["canonical_model_id"])
            for target in candidates:
                if target["canonical_model_id"] in seen:
                    continue
                selected.append(_edge(source, target, relation))
                seen.add(target["canonical_model_id"])
                if len(selected) >= 8:
                    break
            relationships[output_name] = selected[:8]
        boards.append({
            "brand": source["brand"], "model": source["model"],
            "boardModelId": source["canonical_model_id"],
            "publicFamily": source["public_family"],
            "relationships": relationships,
        })
    payload = {"schemaVersion": 3, "generatedAtUtc": datetime.now(timezone.utc).isoformat(), "boardCount": len(boards), "boards": boards}
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"board_count": len(boards), "relationship_types": len(RELATIONS)}, indent=2))


if __name__ == "__main__":
    main()
