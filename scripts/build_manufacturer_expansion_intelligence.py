"""Build the deployable Phase 3 manufacturer-intelligence snapshot.

The canonical builder is the authority for these rows.  This script deliberately
does not classify a board into a public family: the Phase 3 family audit marked
every new model as unknown because the official sources did not publish a
governed public-family field.  It is safe to run again whenever the canonical
dry-run evidence is refreshed.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_ROOT = (
    ROOT.parents[1]
    / "quivrr.app"
    / "quivrr-backend"
    / "docs"
    / "operations"
    / "outputs"
    / "manufacturer-expansion-2026-07-21"
    / "canonical"
    / "dry-run"
)
OUTPUT = ROOT / "app" / "knowledge" / "generated" / "manufacturer_expansion_catalogue.json"

# Canonical rows are intentionally empty until the corrected AIPA and Timmy
# official-model reconciliations pass owner review. Reusable deferred adapters
# remain in the backend but do not feed Board Guide staging.
SOURCES = ()


def load_rows(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def model_record(rows: list[dict]) -> dict:
    first = rows[0]
    sizes = []
    constructions = []
    for row in rows:
        construction = row["construction"]
        if construction not in constructions:
            constructions.append(construction)
        size = {
            "construction": construction,
            "length": row["length"],
            "width": row["width"],
            "thickness": row["thickness"],
            "volume_litres": row["volume_litres"],
        }
        if size not in sizes:
            sizes.append(size)
    return {
        "manufacturer": first["brand"],
        "model": first["model"],
        "canonical_key": f"{first['brand'].lower()}::{first['model'].lower()}",
        "canonical_state": "staged_sql_pending",
        "official_product_url": first["official_product_url"],
        "official_image_url": first["official_image_url"],
        "official_description": first["description"],
        "constructions": constructions,
        "sizes": sizes,
        "public_family": None,
        "family_evidence_status": "missing_official_public_family_evidence",
        "editorial_review_status": "official_evidence_only",
        "editorial_review": (
            "Official model wording, construction labels and standard sizes are available. "
            "Quivrr has not assigned a public family or behavioural Board DNA because "
            "the official source lacks governed public-family evidence."
        ),
        "relationship_status": "no_editorial_relationships_published",
        "comparison_status": "evidence_only_no_performance_ranking",
        "source": first["source"],
        "scraped_at_utc": first["scraped_at_utc"],
    }


def build(canonical_root: Path) -> dict:
    manufacturers: list[dict] = []
    models: list[dict] = []
    for filename, brand, lifecycle, source_note in SOURCES:
        rows = load_rows(canonical_root / filename)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row["model"]].append(row)
        brand_models = [model_record(grouped[name]) for name in sorted(grouped, key=str.lower)]
        models.extend(brand_models)
        manufacturers.append({
            "manufacturer": brand,
            "lifecycle_state": lifecycle,
            "model_count": len(brand_models),
            "standard_size_count": sum(len(row["sizes"]) for row in brand_models),
            "constructions": sorted({construction for row in brand_models for construction in row["constructions"]}),
            "source_authority": source_note,
            "editorial_summary": (
                "The staged canonical catalogue is available to Bodhi as official evidence only. "
                "Public-family classification, performance ranking and model-to-model relationships "
                "remain intentionally unpublished until governed official family evidence is captured."
            ),
        })
    for manufacturer, authority in (
        ("AIPA Surf", "Official AIPA model directory reconciliation in progress"),
        ("Timmy Patterson Surfboards", "Official Timmy Patterson model directory reconciliation in progress"),
    ):
        manufacturers.append({
            "manufacturer": manufacturer,
            "lifecycle_state": "canonical_pending",
            "model_count": 0,
            "standard_size_count": 0,
            "constructions": [],
            "source_authority": authority,
            "editorial_summary": (
                "Manufacturer-level awareness only. No model, size, construction or review is published "
                "until the complete official directory is reconciled and owner-approved."
            ),
        })
    return {
        "schema_version": 1,
        "authority": "Quivrr Phase 3 canonical dry-run evidence; official manufacturer source wording only",
        "catalogue_state": "staged_sql_pending",
        "family_policy": "Unknown is retained where official public-family evidence is absent; model names are never used to infer a family.",
        "manufacturers": manufacturers,
        "models": models,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build(args.canonical_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(payload['models'])} models).")


if __name__ == "__main__":
    main()
