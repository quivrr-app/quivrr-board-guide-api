from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re


MASTER_PATH = Path(__file__).resolve().parent / "knowledge" / "curated" / "quivrr_board_master_matrix_v2.json"
LEGACY_DNA_PATH = Path(__file__).resolve().parent / "knowledge" / "board_dna_v1.json"
LEGACY_TAXONOMY_PATH = Path(__file__).resolve().parent / "knowledge" / "board_taxonomy_v2.json"
EXPECTED_MODEL_COUNT = 458
PUBLIC_FAMILIES = {
    "fish", "groveller", "daily_driver", "performance_shortboard",
    "step_up", "mid_length", "longboard",
}


def normalise(value: object) -> str:
    text = str(value or "").lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def category_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def ranking_family(master: dict) -> str:
    category = normalise(master.get("detailed_category"))
    if "performance twin" in category or "twin pin" in category:
        return "Performance Twin"
    if "performance fish" in category:
        return "Performance Fish"
    if "traditional fish" in category or "retro fish" in category or "twin fin fish" in category:
        return "Fish"
    if "performance daily driver" in category:
        return "Performance Daily Driver"
    if "daily driver" in category or "one board quiver" in category:
        return "Daily Driver"
    if "hybrid shortboard" in category:
        return "Hybrid Shortboard"
    if "high performance shortboard" in category or "hpsb" in category or "competition" in category:
        return "High Performance Shortboard"
    if "performance shortboard" in category:
        return "Performance Shortboard"
    if "groveller" in category or "small wave shortboard" in category:
        return "Groveller"
    if "step up" in category or "semi gun" in category:
        return "Step Up"
    if "performance mid length" in category:
        return "Performance Mid Length"
    if "mid length" in category:
        return "Mid Length"
    if "longboard" in category:
        return "Longboard"
    return master["public_family_label"]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_board_master() -> dict:
    payload = _load_json(MASTER_PATH)
    rows = payload.get("models") or []
    if payload.get("model_count") != EXPECTED_MODEL_COUNT or len(rows) != EXPECTED_MODEL_COUNT:
        raise ValueError("Board Intelligence v2 must contain exactly 458 models")

    ids = [int(row["canonical_model_id"]) for row in rows]
    keys = [row["canonical_key"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Board Intelligence v2 contains duplicate canonical model IDs")
    if len(set(keys)) != len(keys):
        raise ValueError("Board Intelligence v2 contains duplicate canonical keys")
    for row in rows:
        if row.get("public_family") not in PUBLIC_FAMILIES:
            raise ValueError(f"Invalid public family for {row.get('canonical_key')}")
        for field in ("detailed_category", "board_type", "primary_fin_setup", "official_url", "board_dna"):
            if not row.get(field):
                raise ValueError(f"Missing {field} for {row.get('canonical_key')}")
    return payload


@lru_cache(maxsize=1)
def _legacy_aliases() -> dict[int, tuple[str, ...]]:
    aliases: dict[int, list[str]] = {}
    for path in (LEGACY_DNA_PATH, LEGACY_TAXONOMY_PATH):
        for row in _load_json(path).get("models", []):
            model_id = int(row["canonical_model_id"])
            values = aliases.setdefault(model_id, [])
            for alias in row.get("aliases", []):
                if alias and alias not in values:
                    values.append(alias)
    return {model_id: tuple(values) for model_id, values in aliases.items()}


@lru_cache(maxsize=1)
def board_master_indexes() -> tuple[dict[int, dict], dict[tuple[str, str], dict]]:
    by_id: dict[int, dict] = {}
    by_name: dict[tuple[str, str], dict] = {}
    aliases = _legacy_aliases()
    for row in load_board_master()["models"]:
        model_id = int(row["canonical_model_id"])
        by_id[model_id] = row
        names = [row["model"], *aliases.get(model_id, ())]
        for name in names:
            key = (normalise(row["manufacturer"]), normalise(name))
            existing = by_name.get(key)
            if existing and int(existing["canonical_model_id"]) != model_id:
                raise ValueError(f"Ambiguous Board Intelligence alias: {key}")
            by_name[key] = row
    return by_id, by_name


def find_master_board(manufacturer: str, model: str) -> dict | None:
    return board_master_indexes()[1].get((normalise(manufacturer), normalise(model)))


def find_master_board_by_id(canonical_model_id: int | str | None) -> dict | None:
    try:
        return board_master_indexes()[0].get(int(canonical_model_id))
    except (TypeError, ValueError):
        return None


def master_dna_record(master: dict, legacy: dict | None = None) -> dict:
    row = deepcopy(legacy or {})
    dna = master["board_dna"]
    row.update({
        "canonical_model_id": row.get("canonical_model_id", master["canonical_model_id"]),
        "canonical_key": master["canonical_key"],
        "brand": master["manufacturer"],
        "model": master["model"],
        "public_family": master["public_family"],
        "primary_category": category_key(master["detailed_category"]),
        "secondary_categories": list(master.get("secondary_categories") or []),
        "physical_design": deepcopy(dna["physical_design"]),
        "behaviour": deepcopy(dna["behaviour"]),
        "conditions": deepcopy(dna["conditions"]),
        "rider_fit": deepcopy(dna["rider_fit"]),
        "style_tags": list(dna.get("style_tags") or []),
        "quiver_roles": list(dna.get("quiver_roles") or []),
        "recommendation_lanes": list(master.get("recommendation_lanes") or []),
        "excluded_recommendation_lanes": list(master.get("excluded_recommendation_lanes") or []),
        "primary_fin_setup": master["primary_fin_setup"],
        "alternative_fin_setup": list(master.get("alternative_fin_setup") or []),
        "authority": "quivrr_board_master_matrix_v2",
    })
    evidence = dict(row.get("evidence") or {})
    evidence["behaviour_confidence"] = master.get("confidence") or evidence.get("behaviour_confidence") or "medium"
    evidence["classification_authority"] = "quivrr_board_master_matrix_v2"
    row["evidence"] = evidence
    return row


def master_taxonomy_record(master: dict, legacy: dict | None = None) -> dict:
    row = deepcopy(legacy or {})
    row.update({
        "canonical_model_id": row.get("canonical_model_id", master["canonical_model_id"]),
        "canonical_key": master["canonical_key"],
        "brand": master["manufacturer"],
        "model": master["model"],
        "public_family": master["public_family"],
        "primary_category": category_key(master["detailed_category"]),
        "secondary_categories": list(master.get("secondary_categories") or []),
        "recommendation_lanes": list(master.get("recommendation_lanes") or []),
        "excluded_lanes": list(master.get("excluded_recommendation_lanes") or []),
        "primary_fin_setup": master["primary_fin_setup"],
        "alternative_fin_setup": list(master.get("alternative_fin_setup") or []),
        "fin_setup": [master["primary_fin_setup"], *master.get("alternative_fin_setup", [])],
        "wave_size": deepcopy(master.get("wave_size") or {}),
        "wave_power": list(master.get("wave_power") or []),
        "wave_types": list(master.get("wave_type") or []),
        "ability_range": list(master.get("ability_range") or []),
        "strengths": list(master.get("strengths") or []),
        "weaknesses": list(master.get("weaknesses") or []),
        "typical_customer": master.get("typical_customer"),
        "authority": "quivrr_board_master_matrix_v2",
    })
    return row


def overlay_expert_board(row: dict) -> dict:
    master = find_master_board_by_id(row.get("boardModelId")) or find_master_board(row.get("brand", ""), row.get("model", ""))
    if not master:
        return row

    enriched = deepcopy(row)
    category = master["detailed_category"]
    lanes = list(master.get("recommendation_lanes") or [])
    excluded = list(master.get("excluded_recommendation_lanes") or [])
    fins = [master["primary_fin_setup"], *master.get("alternative_fin_setup", [])]
    abilities = list(master.get("ability_range") or [])
    wave_size = master.get("wave_size") or {}
    enriched.update({
        "publicFamily": master["public_family"],
        "primaryFamily": ranking_family(master),
        "detailedCategory": category,
        "designSubtype": category,
        "category": master["board_type"],
        "primaryLane": lanes[0] if lanes else category_key(category),
        "secondaryLanes": lanes[1:],
        "boardLanes": lanes,
        "excludedLanes": excluded,
        "recommendationLanes": lanes,
        "excludedRecommendationLanes": excluded,
        "finSetup": fins,
        "abilityMin": abilities[0] if abilities else None,
        "abilityMax": abilities[-1] if abilities else None,
        "abilityPreferred": abilities,
        "waveTypes": list(master.get("wave_type") or []),
        "wavePowers": list(master.get("wave_power") or []),
        "wavePower": list(master.get("wave_power") or []),
        "waveRangeMinFt": wave_size.get("minimum_ft"),
        "waveRangeMaxFt": wave_size.get("maximum_ft"),
        "strengths": list(master.get("strengths") or []),
        "tradeOffs": list(master.get("weaknesses") or []),
        "manufacturerDescription": master.get("manufacturer_intent"),
        "officialProductUrl": master.get("official_url"),
        "boardMasterAuthority": "quivrr_board_master_matrix_v2",
    })
    return enriched
