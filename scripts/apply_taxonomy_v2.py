from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "app/knowledge/board_taxonomy_v2.json"
SUPPLEMENT = ROOT / "app/knowledge/curated/christenson_taxonomy_supplement.json"
PROFILES = ROOT / "app/knowledge/generated/canonical_board_profiles.json"
MATRIX = ROOT / "app/knowledge/generated/board_expert_matrix.json"


DISPLAY = {
    "traditional_fish": "Fish", "performance_fish": "Performance Fish", "twin_pin": "Twin Pin",
    "performance_twin": "Performance Twin", "groveller": "Groveller",
    "small_wave_shortboard": "Small Wave Shortboard", "hybrid_shortboard": "Hybrid Shortboard",
    "daily_driver": "Daily Driver", "performance_daily_driver": "Performance Daily Driver",
    "performance_shortboard": "Performance Shortboard", "step_up": "Step Up", "gun": "Gun",
    "mid_length": "Mid Length", "performance_mid_length": "Performance Mid Length",
    "longboard": "Longboard", "softboard": "Softboard", "alternative": "Alternative Performance",
}


def key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def profile_from(item: dict) -> dict:
    return {
        "brand": "Christenson", "model": item["model"], "model_family": item["model"],
        "construction": "PU", "category": DISPLAY[item["primary_category"]],
        "fin_system": ", ".join(item["fin_configuration"]), "tail_shape": None,
        "official_product_url": item["source_url"], "official_image_url": None,
        "description": item.get("manufacturer_evidence"), "recommended_wave_range": None,
        "recommended_surfer_weight": None, "source": item["source_url"],
        "sizes": [{"length": size[0], "width": size[1], "thickness": size[2], "volume_litres": size[3]} for size in item.get("sizes", [])],
        "board_model_id": int(item["canonical_model_id"]), "description_source_type": "manufacturer",
        "description_source_url": item["source_url"], "description_last_scraped_utc": "2026-07-16T00:00:00Z",
    }


def matrix_from(row: dict, profile: dict | None) -> dict:
    sizes = profile.get("sizes", []) if profile else []
    volumes = [float(size["volume_litres"]) for size in sizes if size.get("volume_litres") is not None]
    family = DISPLAY[row["primary_category"]]
    return {
        "brand": row["brand"], "model": row["model"], "boardModelId": int(row["canonical_model_id"]),
        "primaryLane": row["primary_category"], "secondaryLanes": row["secondary_categories"],
        "boardLanes": row["recommendation_lanes"], "excludedLanes": row["excluded_lanes"],
        "taxonomyAliases": row["aliases"], "boardFamily": row["model"], "boardCategory": row["primary_category"],
        "primaryFamily": family, "broadFamily": "Fish" if "fish" in row["primary_category"] else "Surfboard",
        "designSubtype": family, "variantType": "standard", "baseModel": row["model"],
        "finSetup": [value.replace("_", " ").title() for value in row["fin_configuration"]],
        "wavePower": row["wave_power"], "waveTypes": row["wave_types"],
        "abilityPreferred": [value.title() for value in row["ability_range"]],
        "abilityMin": row["ability_range"][0].title() if row["ability_range"] else None,
        "abilityMax": row["ability_range"][-1].title() if row["ability_range"] else None,
        "paddleSupport": row["paddle_profile"], "performanceStyle": row["performance_profile"],
        "manufacturerDescription": row.get("manufacturer_evidence") or (profile or {}).get("description"),
        "sourceUrls": [row["source_url"]], "confidence": row["classification_confidence"],
        "volumeRange": {"min": min(volumes), "max": max(volumes)} if volumes else {},
        "lengthRangeInches": {}, "missingFields": [], "keyTradeOffs": [], "secondaryTags": row["secondary_categories"],
        "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "ageModifier": "neutral",
        "xlVariant": False,
    }


def main() -> None:
    taxonomy = json.loads(TAXONOMY.read_text(encoding="utf-8-sig"))["models"]
    taxonomy_by_id = {int(row["canonical_model_id"]): row for row in taxonomy}
    supplement = json.loads(SUPPLEMENT.read_text(encoding="utf-8-sig"))["models"]
    profile_rows = json.loads(PROFILES.read_text(encoding="utf-8-sig"))
    profile_by_id = {int(row["board_model_id"]): row for row in profile_rows if row.get("board_model_id")}
    profile_by_name = {(key(row.get("brand")), key(row.get("model"))): row for row in profile_rows}

    for item in supplement:
        model_id = int(item["canonical_model_id"])
        existing = profile_by_id.get(model_id)
        if not existing:
            existing = next((profile_by_name.get(("christenson", key(name))) for name in [item["model"], *item.get("aliases", [])] if profile_by_name.get(("christenson", key(name)))), None)
        if existing:
            existing.update({"model": item["model"], "model_family": item["model"], "board_model_id": model_id, "official_product_url": item["source_url"], "source": item["source_url"]})
            if item.get("manufacturer_evidence"):
                existing["description"] = item["manufacturer_evidence"]
        else:
            existing = profile_from(item)
            profile_rows.append(existing)
        profile_by_id[model_id] = existing
    # Aliases and casing must not survive as duplicate publication records.
    governed_ids = {int(item["canonical_model_id"]) for item in supplement}
    governed_aliases = {("christenson", key(alias)) for item in supplement for alias in item.get("aliases", [])}
    profile_rows = [row for row in profile_rows if int(row.get("board_model_id") or -1) in governed_ids or (key(row.get("brand")), key(row.get("model"))) not in governed_aliases]
    unique_profiles: list[dict] = []
    seen_profile_ids: set[int] = set()
    for row in profile_rows:
        model_id = int(row.get("board_model_id") or -1)
        governed_christenson = key(row.get("brand")) == "christenson" and model_id in governed_ids
        if governed_christenson and model_id in seen_profile_ids:
            continue
        if governed_christenson:
            seen_profile_ids.add(model_id)
        unique_profiles.append(row)
    profile_rows = unique_profiles
    PROFILES.write_text(json.dumps(profile_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    matrix_doc = json.loads(MATRIX.read_text(encoding="utf-8-sig"))
    matrix_rows = matrix_doc["boards"]
    by_id = {int(row["boardModelId"]): row for row in matrix_rows if row.get("boardModelId")}
    for model_id, taxonomy_row in taxonomy_by_id.items():
        profile = profile_by_id.get(model_id)
        replacement = matrix_from(taxonomy_row, profile)
        if model_id in by_id:
            existing = by_id[model_id]
            existing.update({
                "model": taxonomy_row["model"],
                "boardModelId": model_id,
                "governedPrimaryCategory": taxonomy_row["primary_category"],
                "governedSecondaryCategories": taxonomy_row["secondary_categories"],
                "recommendationLanes": taxonomy_row["recommendation_lanes"],
                "excludedLanes": taxonomy_row["excluded_lanes"],
                "taxonomyAliases": taxonomy_row["aliases"],
                "finSetup": replacement["finSetup"] or existing.get("finSetup", []),
                "sourceUrls": list(dict.fromkeys([*existing.get("sourceUrls", []), taxonomy_row["source_url"]])),
            })
        else:
            matrix_rows.append(replacement)
    matrix_rows.sort(key=lambda row: (row["brand"].lower(), row["model"].lower()))
    matrix_doc.update({"schemaVersion": "board_expert_matrix_v2", "taxonomyVersion": "board_taxonomy_v2", "boards": matrix_rows})
    MATRIX.write_text(json.dumps(matrix_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"taxonomy": len(taxonomy), "profiles": len(profile_rows), "matrix": len(matrix_rows)}, indent=2))


if __name__ == "__main__":
    main()
