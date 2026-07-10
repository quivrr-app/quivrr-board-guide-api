from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "app/knowledge/generated/board_expert_matrix.json"
OVERRIDES_PATH = ROOT / "app/knowledge/curated/board_relationship_overrides.json"
FIRST_CLASS_PATH = ROOT / "app/knowledge/board_relationships.json"
OUTPUT_PATH = ROOT / "app/knowledge/generated/board_relationship_graph.json"
AUDIT_JSON_PATH = ROOT / "app/knowledge/audits/phase9_relationship_graph_audit.json"
AUDIT_CSV_PATH = ROOT / "app/knowledge/audits/phase9_relationship_graph_audit.csv"

RELATIONSHIPS = [
    "similarBoards", "upgradeBoards", "downgradeBoards", "moreForgivingBoards",
    "morePerformanceBoards", "morePaddleBoards", "stepUpFromBoards", "stepDownFromBoards",
    "fishAlternativeBoards", "shortboardAlternativeBoards",
    "betterSmallWaveBoards", "betterGoodWaveBoards",
    "betterPointBreakBoards", "betterBeachBreakBoards", "betterReefBoards",
    "closestFishAlternatives", "closestDailyDriverAlternatives",
    "closestStepUpAlternatives", "closestGrovellerAlternatives",
]
SCORES = {
    "moreForgivingBoards": "forgivenessScore", "morePerformanceBoards": "performanceScore",
    "betterSmallWaveBoards": "smallWaveScore", "betterGoodWaveBoards": "goodWaveScore",
    "betterPointBreakBoards": "holdScore", "betterBeachBreakBoards": "speedGenerationScore",
    "betterReefBoards": "holdScore", "upgradeBoards": "performanceScore",
    "downgradeBoards": "forgivenessScore",
    "morePaddleBoards": "paddleEaseScore", "stepUpFromBoards": "performanceScore",
    "stepDownFromBoards": "forgivenessScore",
}


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def identity(board: dict) -> tuple[str, str]:
    return key(board.get("brand")), key(board.get("model"))


def lanes(board: dict) -> set[str]:
    return {board.get("primaryLane"), *board.get("secondaryLanes", []), *board.get("boardLanes", [])} - {None}


def similarity(left: dict, right: dict) -> tuple[float, set[str]]:
    shared = lanes(left) & lanes(right)
    score = len(shared) * 18
    if left.get("primaryLane") == right.get("primaryLane"):
        score += 30
    for field in ("performanceScore", "forgivenessScore", "paddleEaseScore", "fishScore", "dailyDriverScore"):
        score += max(0, 8 - abs(float(left.get(field, 50)) - float(right.get(field, 50))) / 5)
    return min(score, 100), shared


def edge(target: dict, candidate: dict, relation: str, score: float, shared: set[str], curated: bool = False, reason: str | None = None) -> dict:
    confidence = "high" if curated else "medium" if score >= 65 else "low"
    different = sorted(lanes(candidate) - lanes(target))
    reason = reason or (
        "Quivrr-reviewed relationship; " if curated else "Deterministic expert-matrix relationship; "
    ) + (f"shared lanes: {', '.join(sorted(shared))}" if shared else f"stronger {relation.replace('Boards', '').replace('better', '').lower()} profile")
    return {
        "brand": candidate["brand"], "model": candidate["model"], "relationshipType": relation,
        "reason": reason, "confidence": confidence,
        "source": "quivrr_curated_override" if curated else "board_expert_matrix_v2",
        "sharedLanes": sorted(shared), "differentLanes": different[:5],
    }


def family_match(board: dict, family: str) -> bool:
    return any(family in lane for lane in lanes(board))


def generated_relationships(target: dict, candidates: list[dict], limit: int = 6) -> dict[str, list[dict]]:
    ranked = {relation: [] for relation in RELATIONSHIPS}
    target_lanes = lanes(target)
    for candidate in candidates:
        if identity(candidate) == identity(target):
            continue
        score, shared = similarity(target, candidate)
        candidate_lanes = lanes(candidate)
        conditions = {
            "similarBoards": bool(shared) and score >= 45,
            "upgradeBoards": candidate.get("performanceScore", 0) >= target.get("performanceScore", 0) + 8,
            "downgradeBoards": candidate.get("forgivenessScore", 0) >= target.get("forgivenessScore", 0) + 8,
            "moreForgivingBoards": candidate.get("forgivenessScore", 0) >= target.get("forgivenessScore", 0) + 8,
            "morePerformanceBoards": candidate.get("performanceScore", 0) >= target.get("performanceScore", 0) + 8,
            "morePaddleBoards": candidate.get("paddleEaseScore", 0) >= target.get("paddleEaseScore", 0) + 8,
            "stepUpFromBoards": (family_match(candidate, "step_up") or family_match(candidate, "powerful_wave")) and candidate.get("holdScore", 0) >= target.get("holdScore", 0),
            "stepDownFromBoards": (family_match(candidate, "daily_driver") or family_match(candidate, "groveller")) and candidate.get("forgivenessScore", 0) >= target.get("forgivenessScore", 0),
            "fishAlternativeBoards": family_match(candidate, "fish") or any("twin_fin" in lane for lane in candidate_lanes),
            "shortboardAlternativeBoards": family_match(candidate, "daily_driver") or family_match(candidate, "high_performance"),
            "betterPointBreakBoards": "point_break_fish" in candidate_lanes or candidate.get("holdScore", 0) >= target.get("holdScore", 0) + 10,
            "betterSmallWaveBoards": candidate.get("smallWaveScore", 0) >= target.get("smallWaveScore", 0) + 10,
            "betterGoodWaveBoards": candidate.get("goodWaveScore", 0) >= target.get("goodWaveScore", 0) + 10,
            "betterBeachBreakBoards": "small_wave_fish" in candidate_lanes or candidate.get("manoeuvrabilityScore", 0) >= target.get("manoeuvrabilityScore", 0) + 10,
            "betterReefBoards": candidate.get("holdScore", 0) >= target.get("holdScore", 0) + 10,
            "closestFishAlternatives": family_match(candidate, "fish") or any("twin_fin" in lane for lane in candidate_lanes),
            "closestDailyDriverAlternatives": family_match(candidate, "daily_driver"),
            "closestStepUpAlternatives": family_match(candidate, "step_up"),
            "closestGrovellerAlternatives": family_match(candidate, "groveller"),
        }
        for relation, include in conditions.items():
            if include:
                directional = SCORES.get(relation)
                boost = float(candidate.get(directional, 0)) * .25 if directional else 0
                ranked[relation].append((score + boost, candidate, shared))
    output = {}
    for relation, rows in ranked.items():
        rows.sort(key=lambda row: (-row[0], row[1]["brand"], row[1]["model"]))
        output[relation] = [edge(target, candidate, relation, score, shared) for score, candidate, shared in rows[:limit]]
    return output


def main() -> int:
    boards = json.loads(MATRIX_PATH.read_text(encoding="utf-8-sig"))["boards"]
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8-sig"))["relationships"]
    first_class = json.loads(FIRST_CLASS_PATH.read_text(encoding="utf-8-sig"))
    public_names = {
        "similar": "similarBoards", "more_performance": "morePerformanceBoards",
        "more_forgiving": "moreForgivingBoards", "more_paddle": "morePaddleBoards",
        "better_for_points": "betterPointBreakBoards", "better_for_beach_breaks": "betterBeachBreakBoards",
        "better_for_small_waves": "betterSmallWaveBoards", "better_for_good_waves": "betterGoodWaveBoards",
        "step_up_from": "stepUpFromBoards", "step_down_from": "stepDownFromBoards",
        "fish_alternative": "fishAlternativeBoards", "shortboard_alternative": "shortboardAlternativeBoards",
    }
    for row in first_class["boards"]:
        normalized = {"brand": row["brand"], "model": row["model"]}
        normalized.update({public_names[name]: values for name, values in row.get("relationships", {}).items()})
        overrides = [old for old in overrides if identity(old) != identity(normalized)] + [normalized]
    board_map = {identity(board): board for board in boards}
    override_map = {(key(row["brand"]), key(row["model"])): row for row in overrides}
    unmatched = []
    output = []
    for board in boards:
        relations = generated_relationships(board, boards)
        override = override_map.get(identity(board))
        if override:
            for relation in RELATIONSHIPS:
                additions = []
                for item in override.get(relation, []):
                    brand, model = item[:2] if isinstance(item, list) else (item["brand"], item["model"])
                    candidate = board_map.get((key(brand), key(model)))
                    if not candidate:
                        continue
                    score, shared = similarity(board, candidate)
                    custom_reason = item.get("reason") if isinstance(item, dict) else None
                    additions.append(edge(board, candidate, relation, max(score, 85), shared, curated=True, reason=custom_reason))
                added = {identity(item) for item in additions}
                if additions:
                    relations[relation] = additions[:8]
        output.append({"brand": board["brand"], "model": board["model"], "boardModelId": board.get("boardModelId"), "relationships": relations})
    for requested in overrides:
        if (key(requested["brand"]), key(requested["model"])) not in board_map:
            unmatched.append({"brand": requested["brand"], "model": requested["model"], "reason": "not in canonical matrix"})
    lines = ['{', '  "schemaVersion": "board_relationship_graph_v2",', '  "boards": [']
    for index, row in enumerate(output):
        lines.append("    " + json.dumps(row, ensure_ascii=False, separators=(",", ":")) + ("," if index < len(output) - 1 else ""))
    lines.extend(["  ]", "}"])
    temp_path = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    try:
        temp_path.replace(OUTPUT_PATH)
    except PermissionError:
        with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        temp_path.unlink(missing_ok=True)
    counts = {relation: sum(bool(row["relationships"][relation]) for row in output) for relation in RELATIONSHIPS}
    confidence = Counter(edge_row["confidence"] for row in output for edges in row["relationships"].values() for edge_row in edges)
    needing_review = [
        {"brand": row["brand"], "model": row["model"], "relationshipCount": sum(len(value) for value in row["relationships"].values())}
        for row in output if identity(row) not in override_map
    ]
    needing_review.sort(key=lambda row: (row["relationshipCount"], row["brand"], row["model"]))
    audit = {
        "totalModels": len(output), "modelsWithSimilarBoards": counts["similarBoards"],
        "modelsWithUpgradeBoards": counts["upgradeBoards"], "modelsWithMoreForgivingBoards": counts["moreForgivingBoards"],
        "modelsWithMorePerformanceBoards": counts["morePerformanceBoards"],
        "modelsWithWaveSpecificRelationships": sum(any(row["relationships"][name] for name in ("betterSmallWaveBoards","betterGoodWaveBoards","betterPointBreakBoards","betterBeachBreakBoards","betterReefBoards")) for row in output),
        "confidenceDistribution": dict(sorted(confidence.items())), "relationshipCoverage": counts,
        "curatedSourceBoardsMatched": sum(identity(row) in override_map for row in output),
        "unmatchedCuratedSourceBoards": unmatched, "top50ModelsNeedingCuratedRelationshipReview": needing_review[:50],
    }
    AUDIT_JSON_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with AUDIT_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["brand","model","relationshipCount"])
        writer.writeheader(); writer.writerows(needing_review[:50])
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
