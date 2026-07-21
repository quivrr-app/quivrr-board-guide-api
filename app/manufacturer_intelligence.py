"""Evidence-limited manufacturer intelligence for the Phase 3 expansion.

This module is deliberately separate from the governed Board Master.  The
staged manufacturers have canonical model identities and standard sizes, but
their official sources have not supplied enough public-family evidence for a
Quivrr classification.  Keeping this boundary explicit makes the information
useful to Bodhi without promoting an inference into editorial fact.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


CATALOGUE_PATH = Path(__file__).parent / "knowledge" / "generated" / "manufacturer_expansion_catalogue.json"


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


@lru_cache(maxsize=1)
def load_manufacturer_expansion_catalogue() -> dict:
    """Load the deployable Phase 3 snapshot, or a safe empty snapshot."""
    if not CATALOGUE_PATH.exists():
        return {"manufacturers": [], "models": [], "catalogue_state": "unavailable"}
    return json.loads(CATALOGUE_PATH.read_text(encoding="utf-8-sig"))


def list_manufacturers() -> list[dict]:
    return list(load_manufacturer_expansion_catalogue().get("manufacturers") or [])


def find_manufacturer(manufacturer: str | None) -> dict | None:
    wanted = _normalise(manufacturer)
    return next((row for row in list_manufacturers() if _normalise(row.get("manufacturer")) == wanted), None)


def staged_models() -> list[dict]:
    return list(load_manufacturer_expansion_catalogue().get("models") or [])


def find_staged_model(manufacturer: str | None, model: str | None) -> dict | None:
    wanted = (_normalise(manufacturer), _normalise(model))
    return next((
        row for row in staged_models()
        if (_normalise(row.get("manufacturer")), _normalise(row.get("model"))) == wanted
    ), None)


def models_for_manufacturer(manufacturer: str | None) -> list[dict]:
    wanted = _normalise(manufacturer)
    return [row for row in staged_models() if _normalise(row.get("manufacturer")) == wanted]


def _volume_range(model: dict) -> dict[str, float] | None:
    volumes = [row.get("volume_litres") for row in model.get("sizes") or [] if isinstance(row.get("volume_litres"), (int, float))]
    return {"minimum_litres": min(volumes), "maximum_litres": max(volumes)} if volumes else None


def model_summary(model: dict) -> dict:
    """Return safe public data plus SEO metadata for a staged model.

    `indexable` remains false until SQL canonical import confirms the public
    identity.  The official product URL is intentionally retained as the
    authority instead of inventing a Quivrr canonical route.
    """
    return {
        "manufacturer": model["manufacturer"],
        "model": model["model"],
        "canonical_state": model["canonical_state"],
        "official_product_url": model["official_product_url"],
        "official_image_url": model["official_image_url"],
        "constructions": list(model.get("constructions") or []),
        "standard_size_count": len(model.get("sizes") or []),
        "volume_range": _volume_range(model),
        "public_family": None,
        "family_evidence_status": model["family_evidence_status"],
        "editorial_review_status": model["editorial_review_status"],
        "relationship_status": model["relationship_status"],
        "comparison_status": model["comparison_status"],
        "seo": {
            "title": f"{model['manufacturer']} {model['model']} official model information | Quivrr",
            "canonical_url": model["official_product_url"],
            "indexable": False,
            "reason": "Staged canonical identity awaits production SQL import.",
        },
    }


def construction_summaries() -> list[dict]:
    summaries = []
    for manufacturer in list_manufacturers():
        constructions = manufacturer.get("constructions") or []
        summaries.append({
            "manufacturer": manufacturer["manufacturer"],
            "constructions": constructions,
            "summary": (
                "Official construction labels are preserved exactly as published. "
                "No cross-manufacturer equivalence or performance hierarchy is asserted."
                if constructions else
                "No construction summary is published while canonical evidence is pending."
            ),
        })
    return summaries


def compare_staged_models(left: dict, right: dict) -> dict:
    """Compare only recorded catalogue attributes; never rank performance."""
    left_range = _volume_range(left)
    right_range = _volume_range(right)
    left_constructions = set(left.get("constructions") or [])
    right_constructions = set(right.get("constructions") or [])
    return {
        "left": model_summary(left),
        "right": model_summary(right),
        "same_manufacturer": left["manufacturer"] == right["manufacturer"],
        "shared_constructions": sorted(left_constructions.intersection(right_constructions)),
        "standard_size_comparison": {
            "left": left_range,
            "right": right_range,
        },
        "comparison_status": "evidence_only_no_performance_ranking",
        "constraints": [
            "Official sources did not provide governed public-family evidence for these models.",
            "Bodhi therefore does not publish a performance winner, family comparison or inferred relationship.",
        ],
    }
