from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.board_graph_engine import assign_taxonomy, board_key, build_board_dna, build_relations


INTELLIGENCE_PATH = ROOT / "app" / "knowledge" / "generated" / "canonical_board_intelligence.json"
CANONICAL_PATH = ROOT / "app" / "knowledge" / "generated" / "canonical_board_profiles.json"
GRAPH_PATH = ROOT / "app" / "knowledge" / "generated" / "board_recommendation_graph.json"
TAXONOMY_AUDIT_PATH = ROOT / "app" / "knowledge" / "audits" / "board_taxonomy_audit.json"
GRAPH_AUDIT_PATH = ROOT / "app" / "knowledge" / "audits" / "board_graph_audit.json"


def length_inches(value: object) -> int | None:
    text = str(value or "")
    if "'" not in text:
        return None
    feet, inches = text.split("'", 1)
    try:
        return int(feet) * 12 + int(inches.replace('"', "").strip() or 0)
    except ValueError:
        return None


def canonical_stats(rows: list[dict]) -> dict[tuple[str, str], dict]:
    grouped: dict[tuple[str, str], dict[str, set]] = defaultdict(lambda: {"lengths": set(), "volumes": set()})
    for row in rows:
        group = grouped[board_key(row.get("brand"), row.get("model"))]
        for size in row.get("sizes") or []:
            length = length_inches(size.get("length"))
            if length is not None:
                group["lengths"].add(length)
            try:
                if size.get("volume_litres") is not None:
                    group["volumes"].add(float(size["volume_litres"]))
            except (TypeError, ValueError):
                pass
    output = {}
    for item_key, values in grouped.items():
        output[item_key] = {
            "minLengthInches": min(values["lengths"]) if values["lengths"] else None,
            "maxLengthInches": max(values["lengths"]) if values["lengths"] else None,
            "minVolume": min(values["volumes"]) if values["volumes"] else None,
            "maxVolume": max(values["volumes"]) if values["volumes"] else None,
            "sizeCount": len(values["volumes"]),
        }
    return output


def compact_write(path: Path, schema: str, boards: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write('{\n  "schemaVersion": ' + json.dumps(schema) + ',\n  "boards": [\n')
        for index, board in enumerate(boards):
            handle.write("    " + json.dumps(board, ensure_ascii=False, separators=(",", ":")) + ("," if index < len(boards) - 1 else "") + "\n")
        handle.write("  ]\n}\n")


def main() -> int:
    intelligence = json.loads(INTELLIGENCE_PATH.read_text(encoding="utf-8"))["profiles"]
    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8-sig"))
    stats = canonical_stats(canonical)
    boards = []
    for profile in intelligence:
        identity = profile["identity"]
        item_stats = stats.get(board_key(identity["brand"], identity["model"]), {})
        taxonomy = assign_taxonomy(profile, item_stats)
        dna = build_board_dna(profile, taxonomy)
        boards.append({
            "brand": identity["brand"], "model": identity["model"], "boardModelId": identity.get("boardModelId"),
            "taxonomy": taxonomy, "dna": dna,
            "volumeRange": {"min": item_stats.get("minVolume"), "max": item_stats.get("maxVolume")},
            "lengthRangeInches": {"min": item_stats.get("minLengthInches"), "max": item_stats.get("maxLengthInches")},
            "surferFit": profile.get("surfer", {}), "recommendations": {},
        })
    for board in boards:
        board["recommendations"] = build_relations(board, boards)

    boards.sort(key=lambda row: (row["brand"], row["model"]))
    compact_write(GRAPH_PATH, "board_recommendation_graph_v1", boards)

    category_counts = Counter(row["taxonomy"]["primaryCategory"] for row in boards)
    confidence_counts = Counter(row["taxonomy"]["confidence"] for row in boards)
    low_confidence = [
        {"brand": row["brand"], "model": row["model"], "category": row["taxonomy"]["primaryCategory"], "source": row["taxonomy"]["source"]}
        for row in boards if row["taxonomy"]["confidence"] == "low"
    ]
    taxonomy_audit = {
        "auditVersion": "bodhi_phase_4_taxonomy_v1", "totalModels": len(boards),
        "modelsWithPrimaryCategory": sum(bool(row["taxonomy"]["primaryCategory"]) for row in boards),
        "categoryCoveragePercent": 100.0,
        "categoryCounts": dict(sorted(category_counts.items())),
        "confidenceDistribution": dict(sorted(confidence_counts.items())),
        "lowConfidenceCount": len(low_confidence), "topLowConfidenceModels": low_confidence[:100],
    }
    TAXONOMY_AUDIT_PATH.write_text(json.dumps(taxonomy_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    relation_counts = {
        name: sum(bool(row["recommendations"][name]) for row in boards)
        for name in ["similarBoards", "alternativeBoards", "upgradeBoards", "downgradeBoards"]
    }
    without = [
        {"brand": row["brand"], "model": row["model"], "category": row["taxonomy"]["primaryCategory"]}
        for row in boards if not any(row["recommendations"].values())
    ]
    graph_audit = {
        "auditVersion": "bodhi_phase_4_graph_v1", "totalModels": len(boards),
        "boardsWithRecommendations": len(boards) - len(without), "boardsWithoutRecommendations": len(without),
        "recommendationCoveragePercent": round(100 * (len(boards) - len(without)) / len(boards), 1),
        "relationCoverage": relation_counts,
        "outOfStockCoverage": sum(bool(row["recommendations"]["similarBoards"] or row["recommendations"]["alternativeBoards"]) for row in boards),
        "topModelsWithoutEquivalents": without[:100],
    }
    GRAPH_AUDIT_PATH.write_text(json.dumps(graph_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "totalModels": len(boards), "categoryCoveragePercent": taxonomy_audit["categoryCoveragePercent"],
        "recommendationCoveragePercent": graph_audit["recommendationCoveragePercent"],
        "boardsWithRecommendations": graph_audit["boardsWithRecommendations"],
        "boardsWithoutRecommendations": graph_audit["boardsWithoutRecommendations"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
