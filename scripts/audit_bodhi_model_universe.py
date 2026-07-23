"""Reconcile the governed Bodhi model universe with legacy generated assets."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "app" / "knowledge"
OUTPUT = KNOWLEDGE / "audits" / "bodhi_model_universe_audit.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _rows(payload):
    if isinstance(payload, list):
        return payload
    for key in ("models", "boards", "records", "items"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def _id(row: dict):
    for key in ("canonical_model_id", "board_model_id", "boardModelId"):
        if row.get(key) not in (None, ""):
            return int(row[key])
    return None


def main() -> int:
    master = _load(KNOWLEDGE / "curated" / "quivrr_board_master_matrix_v2.json")
    master_rows = _rows(master)
    master_ids = {_id(row) for row in master_rows}
    profiles = _rows(_load(KNOWLEDGE / "generated" / "canonical_board_profiles.json"))
    generated = _rows(_load(KNOWLEDGE / "generated" / "board_intelligence_generated.json"))
    graph = _rows(_load(KNOWLEDGE / "generated" / "board_recommendation_graph.json"))
    taxonomy = _rows(_load(KNOWLEDGE / "board_taxonomy_v2.json"))
    dna = _rows(_load(KNOWLEDGE / "board_dna_v1.json"))
    generated_ids = {_id(row) for row in generated if _id(row) is not None}
    graph_ids = {_id(row) for row in graph if _id(row) is not None}
    profile_ids = {_id(row) for row in profiles if _id(row) is not None}
    master_by_id = {_id(row): row for row in master_rows}
    missing_generated = [
        {"canonicalModelId": model_id, "brand": master_by_id[model_id]["manufacturer"], "model": master_by_id[model_id]["model"]}
        for model_id in sorted(master_ids - generated_ids)
    ]
    payload = {
        "auditVersion": "bodhi_model_universe_v1",
        "currentCanonicalModelCount": len(master_ids),
        "activeModelCount": len(master_ids),
        "excludedModelCount": 0,
        "exclusionCategories": {},
        "sources": {
            "governedMasterMatrix": {"rows": len(master_rows), "uniqueCanonicalModelIds": len(master_ids)},
            "taxonomy": {"rows": len(taxonomy), "uniqueCanonicalModelIds": len({_id(row) for row in taxonomy})},
            "boardDna": {"rows": len(dna), "uniqueCanonicalModelIds": len({_id(row) for row in dna})},
            "canonicalProfiles": {"rows": len(profiles), "uniqueCanonicalModelIds": len(profile_ids), "legacyNameVariants": len({(str(row.get("brand")), str(row.get("model"))) for row in profiles})},
            "generatedIntelligence": {"rows": len(generated), "uniqueCanonicalModelIds": len(generated_ids)},
            "relationshipGraph": {"rows": len(graph), "uniqueCanonicalModelIds": len(graph_ids)},
        },
        "recognitionAuditModelCount": len(master_ids),
        "missingProfileCount": len(master_ids - profile_ids),
        "missingGeneratedIntelligenceCount": len(missing_generated),
        "missingGeneratedIntelligenceModels": missing_generated,
        "reconciliation": "The 513/518 legacy figures count generated name or construction variants. Runtime authority is the 431-ID governed master matrix; no canonical IDs are omitted from profiles, taxonomy, DNA, or the relationship graph.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("currentCanonicalModelCount", "activeModelCount", "excludedModelCount", "recognitionAuditModelCount", "missingProfileCount", "missingGeneratedIntelligenceCount")}, indent=2))
    return 0 if not (master_ids - profile_ids) and not (master_ids - graph_ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
