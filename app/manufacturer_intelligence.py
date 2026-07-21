"""Governed manufacturer intelligence exposed from the Board Master.

The Phase 3 raw snapshot is retained only as import evidence.  Bodhi consumes
the Board Master records below, so there is one editorial authority for model
identity, taxonomy, DNA, constructions and standard sizes.
"""

from __future__ import annotations

import re

from app.board_master import load_board_master


GOVERNED_MANUFACTURERS = ("Aloha Surfboards", "AIPA Surf", "Torq Surfboards")
TIMMY_PENDING = {
    "manufacturer": "Timmy Patterson Surfboards",
    "lifecycle_state": "canonical_pending",
    "model_count": 0,
    "standard_size_count": 0,
    "constructions": [],
    "source_authority": "Official Timmy Patterson model pages retained during Phase 3",
    "editorial_summary": "Manufacturer-level awareness only: official model pages did not provide model-specific standard-size evidence, so no model catalogue is published.",
}


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _models() -> list[dict]:
    return [
        row for row in load_board_master()["models"]
        if row["manufacturer"] in GOVERNED_MANUFACTURERS
    ]


def _model_row(master: dict) -> dict:
    return {
        "manufacturer": master["manufacturer"], "model": master["model"],
        "canonical_key": master["canonical_key"],
        "canonical_state": master.get("canonical_state", "accepted_sql_pending"),
        "official_product_url": master["official_url"],
        "official_image_url": master.get("official_image_url"),
        "official_description": master["manufacturer_intent"],
        "constructions": list(master.get("official_constructions") or []),
        "sizes": list(master.get("official_standard_sizes") or []),
        "public_family": master["public_family"],
        "detailed_category": master["detailed_category"],
        "family_evidence_status": "governed_official_source_review",
        "editorial_review_status": "governed_board_master",
        "editorial_review": list(master.get("editorial_notes") or []),
        "relationship_status": "governed_board_dna_relationship_graph",
        "comparison_status": "governed_board_dna_comparison",
        "source": master["official_url"],
        "scraped_at_utc": (master.get("official_evidence") or {}).get("retrieved_at_utc"),
    }


def list_manufacturers() -> list[dict]:
    output = []
    for manufacturer in GOVERNED_MANUFACTURERS:
        rows = [_model_row(row) for row in _models() if row["manufacturer"] == manufacturer]
        output.append({
            "manufacturer": manufacturer,
            "lifecycle_state": "accepted_sql_pending",
            "model_count": len(rows),
            "standard_size_count": sum(len(row["sizes"]) for row in rows),
            "constructions": sorted({value for row in rows for value in row["constructions"]}),
            "source_authority": "Governed Quivrr Board Master from official Phase 3 canonical evidence",
            "editorial_summary": "Public family, Board DNA and relationships are governed by documented official-source evidence; not by first-hand review claims.",
        })
    return output + [TIMMY_PENDING]


def find_manufacturer(manufacturer: str | None) -> dict | None:
    wanted = _normalise(manufacturer)
    return next((row for row in list_manufacturers() if _normalise(row["manufacturer"]) == wanted), None)


def staged_models() -> list[dict]:
    """Backward-compatible name; rows now originate in the governed master."""
    return [_model_row(row) for row in _models()]


def find_staged_model(manufacturer: str | None, model: str | None) -> dict | None:
    wanted = (_normalise(manufacturer), _normalise(model))
    return next((row for row in staged_models() if (_normalise(row["manufacturer"]), _normalise(row["model"])) == wanted), None)


def models_for_manufacturer(manufacturer: str | None) -> list[dict]:
    wanted = _normalise(manufacturer)
    return [row for row in staged_models() if _normalise(row["manufacturer"]) == wanted]


def _volume_range(model: dict) -> dict[str, float] | None:
    volumes = [row.get("volume_litres") for row in model["sizes"] if isinstance(row.get("volume_litres"), (int, float))]
    return {"minimum_litres": min(volumes), "maximum_litres": max(volumes)} if volumes else None


def model_summary(model: dict) -> dict:
    return {
        "manufacturer": model["manufacturer"], "model": model["model"],
        "canonical_state": model["canonical_state"],
        "official_product_url": model["official_product_url"],
        "official_image_url": model["official_image_url"],
        "constructions": model["constructions"], "standard_size_count": len(model["sizes"]),
        "volume_range": _volume_range(model), "public_family": model["public_family"],
        "detailed_category": model["detailed_category"],
        "family_evidence_status": model["family_evidence_status"],
        "editorial_review_status": model["editorial_review_status"],
        "relationship_status": model["relationship_status"],
        "comparison_status": model["comparison_status"],
        "seo": {
            "title": f"{model['manufacturer']} {model['model']} official model information | Quivrr",
            "canonical_url": model["official_product_url"], "indexable": False,
            "reason": "Production SQL canonical identifier is pending.",
        },
    }


def construction_summaries() -> list[dict]:
    return [{
        "manufacturer": row["manufacturer"], "constructions": row["constructions"],
        "summary": "Official construction labels are preserved exactly as published. No cross-manufacturer material equivalence is asserted." if row["constructions"] else "No construction summary is published while canonical evidence is pending.",
    } for row in list_manufacturers()]


def compare_staged_models(left: dict, right: dict) -> dict:
    left_constructions, right_constructions = set(left["constructions"]), set(right["constructions"])
    return {
        "left": model_summary(left), "right": model_summary(right),
        "same_manufacturer": left["manufacturer"] == right["manufacturer"],
        "shared_constructions": sorted(left_constructions.intersection(right_constructions)),
        "standard_size_comparison": {"left": _volume_range(left), "right": _volume_range(right)},
        "comparison_status": "governed_board_dna_comparison",
        "constraints": ["Model guidance is governed from official-source evidence and does not claim a first-hand Quivrr ride test."],
    }
