"""Audit the current governed Bodhi intelligence record, not legacy variant rows."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "app" / "knowledge" / "curated" / "quivrr_board_master_matrix_v2.json"
OUTPUT = ROOT / "app" / "knowledge" / "audits" / "bodhi_intelligence_coverage_audit.json"
REQUIRED = ("detailed_category", "manufacturer_intent", "ability_range", "wave_type", "strengths", "weaknesses", "board_dna", "official_url")


def main() -> int:
    rows = json.loads(MASTER.read_text(encoding="utf-8-sig"))["models"]
    weak, gaps, source_types = [], [], Counter()
    by_brand = defaultdict(lambda: {"models": 0, "weak": 0, "gaps": 0})
    for row in rows:
        brand = row["manufacturer"]
        by_brand[brand]["models"] += 1
        missing = [field for field in REQUIRED if not row.get(field)]
        dna = row.get("board_dna") or {}
        field_sources = {
            "summary": "source_backed" if row.get("manufacturer_intent") else "unknown",
            "category": "curated" if row.get("detailed_category") else "unknown",
            "ability": "generated_from_canonical_evidence" if row.get("ability_range") else "unknown",
            "wave_suitability": "generated_from_canonical_evidence" if row.get("wave_type") else "unknown",
            "strengths": "generated_from_canonical_evidence" if row.get("strengths") else "unknown",
            "trade_offs": "generated_from_canonical_evidence" if row.get("weaknesses") else "unknown",
            "behaviour": "generated_from_canonical_evidence" if dna.get("behaviour") else "unknown",
            "relationship_context": "curated" if row.get("recommendation_lanes") else "unknown",
        }
        source_types.update(field_sources.values())
        is_weak = bool(missing) or row.get("confidence") == "low" or bool(row.get("review_required"))
        if is_weak:
            weak.append({"canonicalModelId": row["canonical_model_id"], "brand": brand, "model": row["model"], "missingFields": missing, "confidence": row.get("confidence"), "reviewRequired": bool(row.get("review_required"))})
            by_brand[brand]["weak"] += 1
        if missing:
            by_brand[brand]["gaps"] += 1
            gaps.append({"canonicalModelId": row["canonical_model_id"], "brand": brand, "model": row["model"], "missingFields": missing})
    payload = {
        "auditVersion": "bodhi_governed_intelligence_v1",
        "canonicalModelCount": len(rows),
        "structuredUsableCount": len(rows) - len(weak),
        "structuredUsableCoveragePercent": round(100 * (len(rows) - len(weak)) / len(rows), 2),
        "weakIntelligenceCount": len(weak),
        "weakIntelligencePercent": round(100 * len(weak) / len(rows), 2),
        "sourceTypeFieldCounts": dict(sorted(source_types.items())),
        "missingStructuredFieldCount": len(gaps),
        "weakModels": weak,
        "brandGaps": [{"brand": brand, **values} for brand, values in sorted(by_brand.items())],
        "definition": "Weak means a required controlled field is missing, confidence is low, or editorial review is required. Medium and high records retain source-backed or generated-from-canonical-evidence labels; no generic prose is counted as strong intelligence.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("canonicalModelCount", "structuredUsableCoveragePercent", "weakIntelligenceCount", "weakIntelligencePercent", "missingStructuredFieldCount")}, indent=2))
    return 0 if payload["structuredUsableCoveragePercent"] >= 95 and payload["weakIntelligencePercent"] < 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
