from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "app" / "knowledge" / "generated"
AUDIT_DIR = ROOT / "app" / "knowledge" / "audits"

CANONICAL_PATH = GENERATED / "canonical_board_profiles.json"
INTELLIGENCE_PATH = GENERATED / "board_intelligence_generated.json"
CLASSIFIER_AUDIT_PATH = GENERATED / "board_intelligence_audit.json"
CATALOGUE_PATH = GENERATED / "catalogue_boards.json"

SUPPORTED_BRANDS = [
    "Album", "Channel Islands", "Chemistry Surfboards", "Chilli", "Christenson",
    "DHD", "DMS Surfboards", "Firewire", "Haydenshapes", "JS Industries", "Lost",
    "Misfit Shapes", "Pukas", "Pyzel", "Rusty", "Sharp Eye", "Simon Anderson",
]

BRAND_IMPORTANCE = {
    "Channel Islands": 5, "Firewire": 5, "Haydenshapes": 5, "JS Industries": 5,
    "Lost": 5, "Pyzel": 5, "Sharp Eye": 5, "Chilli": 4, "DHD": 4,
    "Rusty": 4, "Pukas": 4, "Album": 3, "Christenson": 3, "DMS Surfboards": 3,
    "Misfit Shapes": 3, "Simon Anderson": 3, "Chemistry Surfboards": 2,
}

COMMON_RECOMMENDATION_MODELS = {
    ("Channel Islands", "Happy Everyday"), ("Channel Islands", "CI Mid"),
    ("Channel Islands", "Twin Pin"), ("Firewire", "Dominator 2.0"),
    ("Firewire", "Seaside"), ("Firewire", "Mashup"),
    ("Haydenshapes", "Hypto Krypto"), ("JS Industries", "Monsta"),
    ("JS Industries", "Xero"), ("JS Industries", "Black Baron"),
    ("Lost", "RNF 96"), ("Lost", "Puddle Jumper"), ("Lost", "Rad Ripper"),
    ("Pyzel", "Ghost"), ("Pyzel", "Phantom"), ("Pyzel", "Gremlin"),
    ("Sharp Eye", "Inferno 72"), ("DHD", "DNA"), ("Chilli", "Volume II"),
    ("Rusty", "Dwart"),
}

SOURCE_ENHANCEMENTS = {
    "Sharp Eye": "Capture labelled outline, rail, entry/exit rocker, wave-height, wave-type and ability scales as structured fields.",
    "Pyzel": "Persist manufacturer collection taxonomy (High Performance, Daily Drivers, Funformance, Mid Length/Gun) and explicit model guidance.",
    "Lost": "Persist manufacturer families (Performance, Something Fishy, Grovellers, Recreational Vehicles, Mid Lengths, Step Ups) separately from construction names.",
    "JS Industries": "Persist manufacturer series (Charger, Performer, Daily, Fun, Youth, Foil and Softboard) and structured design labels.",
    "Rusty": "Extract practical wave-type, rider-volume and extra-litres guidance from model narratives without converting it into regional data.",
    "Firewire": "Capture model family, intended wave range, ability guidance and construction notes from the official model pages.",
    "Haydenshapes": "Capture intended conditions, surfer fit, outline/rocker/rail notes and official model relationships.",
    "DHD": "Add structured extraction for model range, intended conditions, rocker, rail, tail and fin guidance.",
    "Channel Islands": "Capture model family, wave range, ability guidance and design characteristics from official model detail pages.",
    "Album": "Repair missing manufacturer descriptions first, then curate category and alternative-board relationships.",
    "Chemistry Surfboards": "Repair canonical model/source URLs and collect manufacturer descriptions before classification.",
    "Chilli": "Capture official category, wave range, surfer level and design metadata from model pages.",
    "Christenson": "Repair description coverage and distinguish fish, mid-length, longboard and performance families.",
    "DMS Surfboards": "Capture official model descriptions, intended waves and design notes; retain DMS as a canonical brand alias only.",
    "Misfit Shapes": "Capture official category, wave fit and construction-independent model descriptions.",
    "Pukas": "Capture manufacturer model narratives and shaper/series metadata independently of Pukas retailer inventory.",
    "Simon Anderson": "Capture official model descriptions, wave fit and design metadata before deterministic classification.",
}

PATTERNS = {
    "category": r"\b(daily driver|performance shortboard|high performance|grovell?er|fish|hybrid|step[- ]?up|mid[- ]?length|longboard|gun|softboard|foil|youth)\b",
    "wave_range": r"\b\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?\s*(?:ft|foot|feet)\b",
    "wave_type": r"\b(beach ?break|point ?break|reef ?break|wave pool)\b",
    "wave_power": r"\b(weak|soft|gutless|mushy|average|everyday|powerful|hollow|heavy|serious)\s+(?:waves?|surf|conditions)\b",
    "ability": r"\b(beginner|novice|intermediate|advanced|expert|professional|pro[- ]level|experienced surfer)\b",
    "outline": r"\boutline\b",
    "entry_rocker": r"\bentry rocker\b",
    "exit_rocker": r"\bexit rocker\b",
    "rail": r"\brails?\b",
    "tail": r"\b(?:squash|swallow|pin|round|diamond|moon|thumb)\s+tail\b|\btail shape\b",
    "fin": r"\b(?:fin setup|fin set[- ]?up|thruster|quad|twin fin|five fin|5[- ]fin|2\+1)\b",
    "construction": r"\b(?:construction|carbon|fiberglass|fibreglass|eps|epoxy|polyurethane|\bpu\b)\b",
    "related": r"\b(?:alternative to|companion to|based on|evolution of|replaces|between an?)\b",
    "rider_guidance": r"\b(?:volume calculator|extra litres?|extra liters?|rider weight|your height|ride this|recommended to order)\b",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def model_key(row: dict) -> tuple[str, str]:
    return key(row.get("brand")), key(row.get("model"))


def text(row: dict) -> str:
    values = [
        row.get("model_description"), row.get("description"), row.get("short_description"),
        row.get("surfer_profile"), row.get("construction_notes"), row.get("fin_setup_notes"),
        row.get("tail_notes"), row.get("rocker_notes"),
    ]
    return re.sub(r"\s+", " ", " ".join(str(value or "") for value in values)).strip()


def best_rows(rows: list[dict]) -> dict[tuple[str, str], dict]:
    output: dict[tuple[str, str], dict] = {}
    for row in rows:
        row_key = model_key(row)
        if not all(row_key):
            continue
        current = output.get(row_key)
        score = (bool(text(row)), len(text(row)), float(row.get("classificationConfidence") or 0))
        current_score = (
            bool(text(current)), len(text(current)), float(current.get("classificationConfidence") or 0)
        ) if current else (-1, -1, -1)
        if score > current_score:
            output[row_key] = row
    return output


def all_sizes(rows: list[dict]) -> dict[tuple[str, str], int]:
    sizes: dict[tuple[str, str], set[tuple]] = {}
    for row in rows:
        row_key = model_key(row)
        bucket = sizes.setdefault(row_key, set())
        for size in row.get("sizes") or []:
            bucket.add((size.get("length"), size.get("width"), size.get("thickness"), size.get("volume_litres")))
    return {row_key: len(values) for row_key, values in sizes.items()}


def has_pattern(blob: str, name: str) -> bool:
    return bool(re.search(PATTERNS[name], blob, flags=re.IGNORECASE))


def source_quality(description: bool, source_type: object, source_url: object) -> str:
    if description and str(source_type or "").lower() == "manufacturer" and source_url:
        return "manufacturer_primary"
    if description and source_url:
        return "source_url_present_unverified_type"
    if description:
        return "description_present_source_incomplete"
    return "missing"


def confidence_band(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.5:
        return "medium"
    if value > 0:
        return "low"
    return "none"


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    canonical_rows = load_json(CANONICAL_PATH)
    intelligence_rows = load_json(INTELLIGENCE_PATH).get("boards", [])
    classifier_audit = load_json(CLASSIFIER_AUDIT_PATH)
    catalogue = load_json(CATALOGUE_PATH)
    canonical = best_rows(canonical_rows)
    intelligence = best_rows(intelligence_rows)
    size_counts = all_sizes(canonical_rows)

    model_rows = []
    for row_key, canonical_row in sorted(canonical.items(), key=lambda item: (item[1].get("brand", ""), item[1].get("model", ""))):
        generated = intelligence.get(row_key, {})
        blob = text(generated) or text(canonical_row)
        description = bool(generated.get("model_description") or canonical_row.get("description"))
        category = generated.get("boardCategory") not in {None, "", "unclassified"}
        wave_range = generated.get("waveRangeMinFt") is not None or has_pattern(blob, "wave_range")
        wave_type = bool(generated.get("waveType")) or has_pattern(blob, "wave_type")
        wave_power = bool(generated.get("wavePower")) or has_pattern(blob, "wave_power")
        ability = bool(generated.get("surferLevel")) or has_pattern(blob, "ability")
        design_fields = [name for name in ("outline", "entry_rocker", "exit_rocker", "rail", "tail", "fin", "construction") if has_pattern(blob, name)]
        tags = generated.get("tags") or []
        confidence = float(generated.get("classificationConfidence") or 0)
        missing = []
        for field, present in [
            ("manufacturerDescription", description), ("primaryCategory", category),
            ("waveRange", wave_range), ("waveType", wave_type), ("wavePower", wave_power),
            ("surferAbility", ability), ("designMetadata", bool(design_fields)),
            ("recommendationTags", bool(tags)), ("equivalency", has_pattern(blob, "related")),
        ]:
            if not present:
                missing.append(field)
        model_rows.append({
            "brand": canonical_row.get("brand"), "model": canonical_row.get("model"),
            "boardModelId": canonical_row.get("board_model_id") or generated.get("board_model_id"),
            "descriptionPresent": description, "classificationPresent": category,
            "categoryPresent": category, "waveRangePresent": wave_range,
            "waveTypePresent": wave_type, "wavePowerPresent": wave_power,
            "abilityPresent": ability, "designMetadataPresent": bool(design_fields),
            "designFields": "|".join(design_fields), "recommendationTagsPresent": bool(tags),
            "equivalencyEvidencePresent": has_pattern(blob, "related"),
            "riderGuidancePresent": has_pattern(blob, "rider_guidance"),
            "sourceQuality": source_quality(description, generated.get("source_type"), generated.get("source_url")),
            "confidence": confidence, "confidenceBand": confidence_band(confidence),
            "canonicalSizeCount": size_counts.get(row_key, 0), "missingFields": "|".join(missing),
        })

    brand_rows = []
    for brand in SUPPORTED_BRANDS:
        rows = [row for row in model_rows if row["brand"] == brand]
        total = len(rows)
        count = lambda field: sum(bool(row[field]) for row in rows)
        gaps = sorted(
            ((label, total - count(field)) for label, field in [
                ("description", "descriptionPresent"), ("category", "categoryPresent"),
                ("wave range", "waveRangePresent"), ("wave type", "waveTypePresent"),
                ("ability", "abilityPresent"), ("design metadata", "designMetadataPresent"),
                ("recommendation tags", "recommendationTagsPresent"),
            ]), key=lambda item: (-item[1], item[0]),
        )
        manufacturer_primary = sum(row["sourceQuality"] == "manufacturer_primary" for row in rows)
        brand_rows.append({
            "brand": brand, "totalModels": total, "modelsWithDescription": count("descriptionPresent"),
            "modelsWithCategory": count("categoryPresent"), "modelsWithWaveRange": count("waveRangePresent"),
            "modelsWithWaveType": count("waveTypePresent"), "modelsWithWavePower": count("wavePowerPresent"),
            "modelsWithAbility": count("abilityPresent"), "modelsWithDesignMetadata": count("designMetadataPresent"),
            "modelsWithRecommendationTags": count("recommendationTagsPresent"),
            "modelsWithRelatedBoardEvidence": count("equivalencyEvidencePresent"),
            "modelsWithRiderGuidance": count("riderGuidancePresent"),
            "manufacturerPrimaryDescriptions": manufacturer_primary,
            "metadataSourceQuality": "high" if total and manufacturer_primary / total >= 0.8 else "mixed" if manufacturer_primary else "low",
            "topGaps": "; ".join(f"{name}: {value}" for name, value in gaps[:3]),
            "recommendedNextEnhancement": SOURCE_ENHANCEMENTS[brand],
        })

    for row in model_rows:
        missing_count = len(str(row["missingFields"]).split("|")) if row["missingFields"] else 0
        score = BRAND_IMPORTANCE.get(str(row["brand"]), 1) * 20
        score += min(int(row["canonicalSizeCount"]), 20)
        score += 12 if row["descriptionPresent"] else 22
        score += 10 if not row["categoryPresent"] else 0
        score += min(missing_count, 8) * 2
        if (row["brand"], row["model"]) in COMMON_RECOMMENDATION_MODELS:
            score += 30
        row["priorityScore"] = score
        row["recommendedNextAction"] = (
            "Recover manufacturer description" if not row["descriptionPresent"]
            else "Extract structured manufacturer metadata" if not row["designMetadataPresent"] or not row["waveRangePresent"]
            else "Review deterministic classification" if not row["classificationPresent"]
            else "Curate equivalency only with explicit evidence"
        )
    priority = sorted(model_rows, key=lambda row: (-row["priorityScore"], str(row["brand"]), str(row["model"])))[:100]

    classifier_summary = {
        name: classifier_audit.get(name) for name in [
            "totalModels", "modelsClassified", "classificationCoveragePercent",
            "confidenceDistribution", "missingDescriptionCount", "unclassifiedCount",
        ]
    }
    priority_summary_fields = [
        "priorityScore", "brand", "model", "boardModelId", "canonicalSizeCount",
        "descriptionPresent", "classificationPresent", "missingFields", "recommendedNextAction",
    ]
    priority_summary = [
        {name: row.get(name) for name in priority_summary_fields} for row in priority
    ]

    source_audit = {
        "auditVersion": "bodhi_phase_2_v1",
        "scope": "global canonical board intelligence; no regional inventory mutation",
        "method": "deterministic read-only analysis of committed generated knowledge files",
        "distinctModels": len(model_rows),
        "canonicalProfileRows": len(canonical_rows),
        "constructionVariantRowsCollapsed": len(canonical_rows) - len(model_rows),
        "existingClassifierAudit": classifier_summary,
        "descriptionCoverageReconciliation": {
            "modelsWithDescriptionAfterVariantMerge": sum(row["descriptionPresent"] for row in model_rows),
            "modelsMissingDescriptionAfterVariantMerge": sum(not row["descriptionPresent"] for row in model_rows),
            "legacyAuditMissingDescriptionCount": classifier_audit.get("missingDescriptionCount"),
            "legacyVariantSelectionFalseMissing": ["Lost Puddle Jumper HP"],
        },
        "knowledgeSources": [
            {"path": str(CANONICAL_PATH.relative_to(ROOT)), "purpose": "Canonical model, construction, sizes and manufacturer description profiles", "ownership": "generated", "sourceOfTruth": "global canonical catalogue plus manufacturer pages", "safeForBodhi": "yes for identity/sizes and sourced descriptions; null metadata is not evidence", "gaps": "construction variants duplicate model identity; many design fields remain embedded in prose"},
            {"path": str(INTELLIGENCE_PATH.relative_to(ROOT)), "purpose": "Deterministic recommendation metadata derived from canonical profiles", "ownership": "generated", "sourceOfTruth": "derived, never canonical identity", "safeForBodhi": "yes when confidence and evidence fields are honoured", "gaps": "legacy and Phase 3 field shapes coexist; coverage is incomplete"},
            {"path": str(CATALOGUE_PATH.relative_to(ROOT)), "purpose": "Reserved catalogue export", "ownership": "generated placeholder", "sourceOfTruth": "none", "safeForBodhi": "no", "gaps": f"contains {len(catalogue.get('boards', []))} boards and remains a placeholder"},
            {"path": str(CLASSIFIER_AUDIT_PATH.relative_to(ROOT)), "purpose": "Coverage and confidence summary for deterministic classification", "ownership": "generated", "sourceOfTruth": "derived audit", "safeForBodhi": "diagnostics only", "gaps": "does not explain per-field manufacturer source coverage"},
            {"path": "app/knowledge/board_intelligence_overrides.json", "purpose": "Quivrr-reviewed deterministic overrides", "ownership": "hand-authored", "sourceOfTruth": "curated intelligence only", "safeForBodhi": "yes after review", "gaps": "small by design and must not become an unsourced shadow catalogue"},
            {"path": "app/knowledge/board_intelligence.json", "purpose": "Legacy curated recommendation seed", "ownership": "hand-authored", "sourceOfTruth": "curated recommendation hints", "safeForBodhi": "with explicit provenance", "gaps": "older schema and limited coverage"},
        ],
        "brandCoverage": brand_rows,
        "top100PriorityModels": priority_summary,
        "limitations": [
            "Live regional inventory counts were not queried because this audit must remain deterministic and region-independent.",
            "Canonical size breadth and brand importance are used as priority signals; availability remains a separate runtime concern.",
            "Keyword evidence identifies metadata present in prose but does not claim that the value has been safely normalised.",
            "Default legacy ability tags are excluded unless explicit manufacturer-text or classifier evidence exists.",
            "The legacy audit counts Lost Puddle Jumper HP as missing because it selects one construction variant; another canonical variant contains the description.",
        ],
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "board_intelligence_source_audit.json").write_text(
        json.dumps(source_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    model_fields = list(model_rows[0].keys())
    write_csv(AUDIT_DIR / "board_intelligence_matrix_gap_report.csv", model_rows, model_fields)
    write_csv(AUDIT_DIR / "brand_metadata_coverage.csv", brand_rows, list(brand_rows[0].keys()))
    priority_fields = ["priorityScore", "brand", "model", "boardModelId", "canonicalSizeCount", "descriptionPresent", "classificationPresent", "missingFields", "recommendedNextAction"]
    write_csv(AUDIT_DIR / "board_intelligence_priority_models.csv", priority, priority_fields)

    print(f"Distinct models audited: {len(model_rows)}")
    print(f"Brands audited: {len(brand_rows)}")
    print(f"Priority models ranked: {len(priority)}")
    print(f"Output directory: {AUDIT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
