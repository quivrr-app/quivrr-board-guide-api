from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/board-taxonomy-review-v1/output/board-taxonomy-owner-review-v1.json"
SUPPLEMENT = ROOT / "app/knowledge/curated/christenson_taxonomy_supplement.json"
OUTPUT = ROOT / "app/knowledge/board_taxonomy_v2.json"

PRIMARY_CATEGORIES = {
    "traditional_fish", "performance_fish", "twin_pin", "performance_twin", "groveller",
    "small_wave_shortboard", "hybrid_shortboard", "daily_driver", "performance_daily_driver",
    "performance_shortboard", "step_up", "gun", "mid_length", "performance_mid_length",
    "longboard", "softboard", "alternative",
}
LANES = PRIMARY_CATEGORIES | {
    "beginner", "big_wave", "competition", "everyday", "fish", "flow", "forgiving_shortboard",
    "good_wave", "hollow_wave", "paddle_support", "point_break", "powerful_wave", "small_wave",
    "weak_wave",
}
CHRISTENSON_MODELS = {
    "Acid Phish", "Cafe Racer", "Carrera", "Easy Wind", "Fish", "Flat Tracker V2", "Lane Splitter",
    "Lane Splitter Swallow", "Long Phish II", "OP2", "OP3", "OP4", "Osprey", "The Wolverine",
}


def key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalise_fin(value: str) -> str:
    return key(value).replace("-", "_")


def record_from_review(row: dict) -> dict:
    return {
        "brand": row["manufacturer"],
        "model": row["model"],
        "canonical_model_id": str(row["canonical_id"]),
        "canonical_key": f"{key(row['manufacturer'])}::{key(row['model'])}",
        "aliases": [],
        "primary_category": row["proposed_primary_category"],
        "secondary_categories": row.get("secondary_categories", []),
        "recommendation_lanes": row.get("recommendation_lanes", []),
        "excluded_lanes": row.get("excluded_lanes", []),
        "fin_configuration": [normalise_fin(item) for item in row.get("fin_configuration", [])],
        "wave_power": row.get("wave_power", []),
        "wave_types": row.get("wave_types", []),
        "ability_range": row.get("ability_range", []),
        "paddle_profile": row.get("paddle_profile"),
        "performance_profile": row.get("performance_profile"),
        "source_url": row.get("official_product_url"),
        "manufacturer_evidence": row.get("manufacturer_evidence"),
        "source_confidence": row.get("source_confidence", "medium"),
        "classification_confidence": row.get("classification_confidence", "medium"),
        "classification_status": "approved",
    }


def validate(records: list[dict]) -> None:
    identities: set[str] = set()
    keys: set[str] = set()
    aliases: dict[tuple[str, str], str] = {}
    for row in records:
        if not row.get("canonical_key"):
            raise ValueError(f"Missing canonical key: {row}")
        if row["canonical_model_id"] in identities:
            raise ValueError(f"Duplicate canonical identity: {row['canonical_model_id']}")
        identities.add(row["canonical_model_id"])
        if row["canonical_key"] in keys:
            raise ValueError(f"Duplicate canonical key: {row['canonical_key']}")
        keys.add(row["canonical_key"])
        categories = {row["primary_category"], *row.get("secondary_categories", [])}
        if unknown := categories - PRIMARY_CATEGORIES:
            raise ValueError(f"Unknown category for {row['canonical_key']}: {sorted(unknown)}")
        included, excluded = set(row["recommendation_lanes"]), set(row["excluded_lanes"])
        if unknown := (included | excluded) - LANES:
            raise ValueError(f"Unknown lane for {row['canonical_key']}: {sorted(unknown)}")
        if overlap := included & excluded:
            raise ValueError(f"Included/excluded lane overlap for {row['canonical_key']}: {sorted(overlap)}")
        if not row.get("source_url", "").startswith("https://"):
            raise ValueError(f"Missing official HTTPS source: {row['canonical_key']}")
        for alias in row.get("aliases", []):
            alias_key = (key(row["brand"]), key(alias))
            if alias_key in aliases and aliases[alias_key] != row["canonical_key"]:
                raise ValueError(f"Alias collision: {row['brand']} {alias}")
            aliases[alias_key] = row["canonical_key"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    supplement = json.loads(SUPPLEMENT.read_text(encoding="utf-8-sig"))["models"]
    records = [record_from_review(row) for row in source["models"] if row["manufacturer"] != "Christenson"]
    for item in supplement:
        base = {
            "brand": "Christenson", "canonical_key": f"christenson::{key(item['model'])}",
            "excluded_lanes": sorted(LANES - set(item["recommendation_lanes"])),
            "wave_power": [], "wave_types": [], "ability_range": ["intermediate", "advanced", "expert"],
            "paddle_profile": "moderate", "performance_profile": "high",
            "source_confidence": "high", "classification_confidence": "high",
            "classification_status": "approved", "manufacturer_evidence": None,
        }
        records.append({**base, **item})
    records.sort(key=lambda row: (row["brand"].lower(), row["model"].lower()))
    validate(records)
    christenson = {row["model"] for row in records if row["brand"] == "Christenson"}
    if christenson != CHRISTENSON_MODELS:
        raise ValueError(f"Christenson coverage mismatch: {sorted(christenson)}")
    payload = {
        "schema_version": "board_taxonomy_v2",
        "source": "approved_owner_review_pr_1_plus_christenson_supplement_v1",
        "model_count": len(records),
        "manufacturer_count": len({row["brand"] for row in records}),
        "models": records,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(records), "manufacturers": payload["manufacturer_count"], "christenson": len(christenson)}, indent=2))


if __name__ == "__main__":
    main()
