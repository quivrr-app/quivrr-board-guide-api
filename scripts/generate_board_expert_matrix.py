from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "app/knowledge/generated/board_recommendation_graph.json"
INTELLIGENCE_PATH = ROOT / "app/knowledge/generated/canonical_board_intelligence.json"
GENERATED_PATH = ROOT / "app/knowledge/generated/board_intelligence_generated.json"
OVERRIDES_PATH = ROOT / "app/knowledge/curated/board_expert_overrides.json"
OUTPUT_PATH = ROOT / "app/knowledge/generated/board_expert_matrix.json"
AUDIT_JSON_PATH = ROOT / "app/knowledge/audits/board_expert_matrix_audit.json"
AUDIT_CSV_PATH = ROOT / "app/knowledge/audits/board_expert_matrix_audit.csv"
PHASE8_AUDIT_JSON_PATH = ROOT / "app/knowledge/audits/phase8_expert_override_audit.json"
PHASE8_AUDIT_CSV_PATH = ROOT / "app/knowledge/audits/phase8_expert_override_audit.csv"

SCORE_FIELDS = [
    "paddleEaseScore", "forgivenessScore", "performanceScore", "speedGenerationScore",
    "holdScore", "manoeuvrabilityScore", "stabilityScore", "smallWaveScore", "goodWaveScore",
    "stepUpScore", "dailyDriverScore", "grovellerScore", "fishScore", "midLengthScore",
    "oneBoardQuiverScore",
]

PRIMARY_FAMILY_BY_LANE = {
    "high_performance_shortboard": "High Performance Shortboard",
    "competition_shortboard": "High Performance Shortboard",
    "performance_daily_driver": "Performance Daily Driver",
    "forgiving_daily_driver": "Daily Driver",
    "hybrid_daily_driver": "Hybrid Shortboard",
    "user_friendly_shortboard": "Daily Driver",
    "small_wave_daily_driver": "Small Wave Shortboard",
    "step_down_shortboard": "Small Wave Shortboard",
    "groveller": "Groveller",
    "performance_groveller": "Groveller",
    "forgiving_groveller": "Groveller",
    "high_volume_groveller": "Groveller",
    "small_wave_speed_board": "Groveller",
    "traditional_fish": "Fish",
    "modern_fish": "Performance Fish",
    "performance_fish": "Performance Fish",
    "small_wave_fish": "Fish",
    "cruisy_fish": "Fish",
    "point_break_fish": "Performance Fish",
    "keel_fish": "Fish",
    "fish_hybrid": "Performance Fish",
    "twin_fin_performance": "Performance Twin",
    "twin_fin_cruiser": "Twin Fin",
    "mid_length": "Mid Length",
    "performance_mid_length": "Mid Length",
    "cruisy_mid_length": "Mid Length",
    "mid_length_twin": "Mid Length",
    "mid_length_single_fin": "Mid Length",
    "step_up": "Step Up",
    "performance_step_up": "Step Up",
    "travel_step_up": "Step Up",
    "big_wave_step_up": "Semi Gun",
    "barrel_board": "Step Up",
    "longboard": "Longboard",
    "performance_longboard": "Longboard",
    "cruisy_longboard": "Longboard",
    "noserider": "Longboard",
    "mini_mal": "Longboard",
    "softboard": "Softboard",
    "gun": "Semi Gun",
}

FAMILY_DEFAULTS = {
    "High Performance Shortboard": {"abilityPreferred": ["Advanced", "Expert"], "fitnessRequirement": "high", "surfFrequencyRequirement": "regular", "paddleSupport": "low", "ageModifier": "neutral", "finSetup": ["Thruster"]},
    "Performance Shortboard": {"abilityPreferred": ["Intermediate", "Advanced", "Expert"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "regular", "paddleSupport": "low_to_moderate", "ageModifier": "neutral", "finSetup": ["Thruster"]},
    "Performance Daily Driver": {"abilityPreferred": ["Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Thruster", "Five Fin"]},
    "Daily Driver": {"abilityPreferred": ["Progressing", "Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate_to_high", "ageModifier": "supportive", "finSetup": ["Thruster", "Five Fin"]},
    "Hybrid Shortboard": {"abilityPreferred": ["Progressing", "Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Thruster", "Five Fin"]},
    "Small Wave Shortboard": {"abilityPreferred": ["Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "supportive", "finSetup": ["Thruster", "Five Fin"]},
    "Groveller": {"abilityPreferred": ["Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Thruster", "Five Fin"]},
    "Fish": {"abilityPreferred": ["Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Twin"]},
    "Performance Fish": {"abilityPreferred": ["Intermediate", "Advanced", "Expert"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Twin", "Quad"]},
    "Twin Fin": {"abilityPreferred": ["Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Twin"]},
    "Performance Twin": {"abilityPreferred": ["Intermediate", "Advanced", "Expert"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Twin"]},
    "Step Up": {"abilityPreferred": ["Advanced", "Expert"], "fitnessRequirement": "high", "surfFrequencyRequirement": "regular", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Thruster"]},
    "Semi Gun": {"abilityPreferred": ["Advanced", "Expert"], "fitnessRequirement": "high", "surfFrequencyRequirement": "regular", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Thruster"]},
    "Mid Length": {"abilityPreferred": ["Progressing", "Intermediate", "Advanced"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Single", "Two Plus One", "Twin"]},
    "Alternative Performance": {"abilityPreferred": ["Intermediate", "Advanced", "Expert"], "fitnessRequirement": "medium", "surfFrequencyRequirement": "moderate", "paddleSupport": "moderate", "ageModifier": "neutral", "finSetup": ["Twin", "Quad"]},
    "Softboard": {"abilityPreferred": ["Beginner", "Progressing"], "fitnessRequirement": "low", "surfFrequencyRequirement": "casual", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Thruster"]},
    "Longboard": {"abilityPreferred": ["Beginner", "Progressing", "Intermediate", "Advanced"], "fitnessRequirement": "low", "surfFrequencyRequirement": "casual", "paddleSupport": "high", "ageModifier": "supportive", "finSetup": ["Single", "Two Plus One"]},
}


def key(brand: str | None, model: str | None) -> tuple[str, str]:
    clean = lambda value: re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return clean(brand), clean(model)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def score(label: str | None) -> int:
    return {"low": 35, "medium": 60, "high": 85}.get(str(label or "").lower(), 50)


def lane_from_graph(board: dict) -> tuple[str, list[str]]:
    category = board.get("taxonomy", {}).get("primaryCategory") or "general_surfboard"
    dna = board.get("dna", {})
    mapping = {
        "performance_shortboard": "high_performance_shortboard", "hybrid": "hybrid_daily_driver",
        "groveller": "groveller", "fish": "fish", "step_up": "step_up", "mid_length": "mid_length",
        "longboard": "longboard", "softboard": "softboard", "foil": "foil", "gun": "gun",
    }
    if category == "daily_driver":
        if dna.get("performanceBias") == "high":
            primary = "performance_daily_driver"
        elif dna.get("forgiveness") == "high":
            primary = "forgiving_daily_driver"
        else:
            primary = "hybrid_daily_driver"
    else:
        primary = mapping.get(category, category if category != "surfboard" else "general_surfboard")
    secondary = []
    for value in board.get("taxonomy", {}).get("secondaryCategories", []):
        mapped = mapping.get(value, value)
        if mapped != primary and mapped not in secondary:
            secondary.append(mapped)
    text = f"{board.get('model','')} {category}".lower()
    if "twin" in text and "twin_fin" not in secondary and primary != "twin_fin":
        secondary.append("twin_fin")
    if primary in {"performance_daily_driver", "forgiving_daily_driver", "hybrid_daily_driver"}:
        secondary.append("one_board_quiver")
    if primary in {"groveller", "fish"}:
        secondary.append("weak_wave_board")
    if primary in {"step_up", "gun", "high_performance_shortboard"}:
        secondary.append("powerful_wave_board")
    ability_min = str(board.get("surferFit", {}).get("abilityMin") or "").lower()
    if primary == "softboard" or ability_min == "beginner":
        secondary.append("beginner_progression")
    if primary in {"step_up", "gun"} or "travel" in text:
        secondary.append("travel_board")
    return primary, list(dict.fromkeys(secondary))


def sublanes_from_board(board: dict, primary: str) -> list[str]:
    text = " ".join(filter(None, [board.get("brand"), board.get("model"), board.get("dna", {}).get("boardPersonality")])).lower()
    dna = board.get("dna", {})
    lanes = []
    if primary == "fish":
        lanes.append("modern_fish")
        lanes.append("performance_fish" if dna.get("performanceBias") == "high" else "cruisy_fish")
        if dna.get("paddlingBias") == "high": lanes.append("small_wave_fish")
        if "keel" in text: lanes.append("keel_fish")
        if "twin" in text: lanes.append("twin_fin_performance" if dna.get("performanceBias") == "high" else "twin_fin_cruiser")
    elif primary == "groveller":
        lanes.extend(["performance_groveller" if dna.get("performanceBias") == "high" else "forgiving_groveller", "small_wave_speed_board"])
    elif primary == "mid_length":
        lanes.append("performance_mid_length" if dna.get("performanceBias") == "high" else "cruisy_mid_length")
        if "twin" in text: lanes.append("mid_length_twin")
        if "single" in text: lanes.append("mid_length_single_fin")
    elif primary == "step_up":
        lanes.extend(["performance_step_up", "barrel_board"])
    elif primary == "longboard":
        lanes.append("performance_longboard" if dna.get("performanceBias") == "high" else "cruisy_longboard")
    elif primary == "high_performance_shortboard":
        lanes.append("high_performance_shortboard")
    elif primary in {"performance_daily_driver", "forgiving_daily_driver", "hybrid_daily_driver"}:
        lanes.append(primary)
    return list(dict.fromkeys(lanes))


def infer_primary_family(primary: str, secondary: list[str], board_lanes: list[str], override: dict | None) -> str:
    if override and override.get("primaryFamily"):
        return override["primaryFamily"]
    for lane in [primary, *secondary, *board_lanes]:
        if lane in PRIMARY_FAMILY_BY_LANE:
            return PRIMARY_FAMILY_BY_LANE[lane]
    return "Alternative Performance"


def infer_variant_metadata(model: str, override: dict | None) -> tuple[str, str, bool]:
    if override and override.get("variantType"):
        variant_type = override["variantType"]
        base_model = override.get("baseModel") or model
        return variant_type, base_model, bool(override.get("xlVariant"))

    lowered = (model or "").lower()
    variant_type = "standard"
    base_model = model
    if " xl" in lowered or lowered.endswith("xl"):
        variant_type = "xl"
        base_model = re.sub(r"\bxl\b", "", model, flags=re.IGNORECASE).replace("  ", " ").strip()
    elif " twin" in lowered and "twinsman" not in lowered:
        variant_type = "twin_variant"
        base_model = re.sub(r"\btwin\b", "", model, flags=re.IGNORECASE).replace("  ", " ").strip()
    elif re.search(r"\b(v\d+|[2-9]\.0|20[0-9]{2}|box)\b", lowered):
        variant_type = "updated_variant"
    return variant_type, base_model or model, variant_type == "xl"


def infer_secondary_tags(primary_family: str, board: dict, board_lanes: list[str], design: dict, wave: dict) -> list[str]:
    tags = []
    wave_types = wave.get("waveTypes") or []
    wave_power = wave.get("wavePower") or board.get("dna", {}).get("wavePower", [])
    if "reef_break" in wave_types:
        tags.append("Reef")
    if "point_break" in wave_types:
        tags.append("Point")
    if "beach_break" in wave_types:
        tags.append("Beach Break")
    if "powerful" in wave_power:
        tags.append("Hollow")
        tags.append("Hold")
    if "weak" in wave_power:
        tags.append("Weak Wave")
        tags.append("Paddle Support")
    if primary_family in {"High Performance Shortboard", "Performance Shortboard"}:
        tags.extend(["Technical", "Refined Rails"])
    if primary_family in {"Performance Twin", "Twin Fin"}:
        tags.extend(["Twin", "Release", "Drive"])
    if primary_family in {"Fish", "Performance Fish"}:
        tags.extend(["Wide Tail", "Drive"])
    if "performance_step_up" in board_lanes or primary_family == "Step Up":
        tags.append("Fast")
    if design.get("entryRocker"):
        tags.append("High Rocker" if "high" in str(design.get("entryRocker")).lower() else "Low Entry Rocker")
    return list(dict.fromkeys(tags))


def build_scores(primary: str, secondary: list[str], dna: dict) -> dict[str, int]:
    values = {field: 45 for field in SCORE_FIELDS}
    values.update({
        "paddleEaseScore": score(dna.get("paddlingBias")),
        "forgivenessScore": score(dna.get("forgiveness")),
        "performanceScore": score(dna.get("performanceBias")),
        "speedGenerationScore": score(dna.get("turningBias")),
        "manoeuvrabilityScore": score(dna.get("turningBias")),
        "holdScore": 75 if "powerful" in dna.get("wavePower", []) else 55,
        "stabilityScore": score(dna.get("forgiveness")),
    })
    lanes = {primary, *secondary}
    lane_scores = {
        "small_wave_daily_driver": ("smallWaveScore", 90), "weak_wave_board": ("smallWaveScore", 85),
        "performance_daily_driver": ("dailyDriverScore", 90), "forgiving_daily_driver": ("dailyDriverScore", 85),
        "hybrid_daily_driver": ("dailyDriverScore", 80), "groveller": ("grovellerScore", 95),
        "fish": ("fishScore", 95), "mid_length": ("midLengthScore", 95), "step_up": ("stepUpScore", 95),
        "one_board_quiver": ("oneBoardQuiverScore", 90), "high_performance_shortboard": ("goodWaveScore", 90),
        "powerful_wave_board": ("goodWaveScore", 90),
    }
    for lane in lanes:
        if lane in lane_scores:
            field, value = lane_scores[lane]
            values[field] = max(values[field], value)
    return values


def main() -> None:
    graph = load_json(GRAPH_PATH).get("boards", [])
    canonical = {key(row["identity"].get("brand"), row["identity"].get("model")): row for row in load_json(INTELLIGENCE_PATH).get("profiles", [])}
    generated_rows = load_json(GENERATED_PATH).get("boards", [])
    generated = {}
    for row in generated_rows:
        item_key = key(row.get("brand"), row.get("model"))
        current = generated.get(item_key)
        if current is None or float(row.get("classificationConfidence") or 0) > float(current.get("classificationConfidence") or 0):
            generated[item_key] = row
    override_payload = load_json(OVERRIDES_PATH)
    defaults = override_payload.get("defaults", {})
    overrides = {
        key(row.get("brand"), row.get("model")): {**defaults, **row}
        for row in override_payload.get("boards", [])
    }

    matrix = []
    for board in graph:
        item_key = key(board.get("brand"), board.get("model"))
        intel = canonical.get(item_key, {})
        gen = generated.get(item_key, {})
        override = overrides.get(item_key)
        primary, secondary = lane_from_graph(board)
        confidence = board.get("taxonomy", {}).get("confidence") or "low"
        source = board.get("taxonomy", {}).get("source") or "deterministic_board_graph"
        reason = f"Mapped from canonical taxonomy {board.get('taxonomy', {}).get('primaryCategory') or 'general surfboard'}."
        reviewed_by = reviewed_at = None
        if override:
            primary = override["primaryLane"]
            secondary = override.get("secondaryLanes", [])
            confidence = override.get("confidence", "high")
            source = "quivrr_curated_override"
            reason = override["reason"]
            reviewed_by = override.get("reviewedByQuivrr")
            reviewed_at = override.get("reviewedAtUtc")
        board_lanes = sublanes_from_board(board, primary)
        if override:
            board_lanes = list(dict.fromkeys(override.get("boardLanes", []) + board_lanes))
        dna = board.get("dna", {})
        scores = build_scores(primary, secondary, dna)
        evidence = {"primaryLane": {"source": source, "confidence": confidence, "reason": reason}}
        for field in SCORE_FIELDS:
            evidence[field] = {
                "source": "deterministic_canonical_dna", "confidence": confidence,
                "reason": f"Derived from the canonical lane and board DNA; value {scores[field]}.",
            }
        design = intel.get("design", {})
        wave = intel.get("wave", {})
        surfer = intel.get("surfer", {})
        description = intel.get("description", {})
        primary_family = infer_primary_family(primary, secondary, board_lanes, override)
        variant_type, base_model, xl_variant = infer_variant_metadata(board.get("model"), override)
        family_defaults = FAMILY_DEFAULTS.get(primary_family, FAMILY_DEFAULTS["Alternative Performance"])
        fin_setup = override.get("finSetup") if override and override.get("finSetup") is not None else family_defaults.get("finSetup", [])
        secondary_tags = override.get("secondaryTags") if override and override.get("secondaryTags") is not None else infer_secondary_tags(primary_family, board, board_lanes, design, wave)
        source_urls = list(dict.fromkeys(filter(None, [
            intel.get("identity", {}).get("sourceUrl"), description.get("descriptionSource"),
            gen.get("official_product_url"), gen.get("source_url"),
        ])))
        missing = []
        if wave.get("waveHeightMinFt") is None or wave.get("waveHeightMaxFt") is None:
            missing.append("waveRange")
        if not surfer.get("abilityMin") and not surfer.get("abilityMax"):
            missing.append("surferFit")
        if not any(design.get(name) for name in ["outline", "railType", "entryRocker", "exitRocker", "tailShape", "finSetup", "designNotes"]):
            missing.append("designData")
        item = {
            "brand": board["brand"], "model": board["model"], "boardModelId": board.get("boardModelId"),
            "primaryLane": primary, "secondaryLanes": secondary,
            "boardLanes": board_lanes,
            "boardFamily": gen.get("model_family") or board["model"],
            "boardCategory": board.get("taxonomy", {}).get("primaryCategory") or "general_surfboard",
            "subCategory": primary,
            "waveRangeMinFt": wave.get("waveHeightMinFt") if wave.get("waveHeightMinFt") is not None else dna.get("waveRange", {}).get("minFt"),
            "waveRangeMaxFt": wave.get("waveHeightMaxFt") if wave.get("waveHeightMaxFt") is not None else dna.get("waveRange", {}).get("maxFt"),
            "wavePower": wave.get("wavePower") or dna.get("wavePower", []),
            "waveTypes": wave.get("waveTypes") or gen.get("waveType", []),
            "abilityMin": surfer.get("abilityMin") or board.get("surferFit", {}).get("abilityMin"),
            "abilityMax": surfer.get("abilityMax") or board.get("surferFit", {}).get("abilityMax"),
            **scores,
            "constructionNotes": design.get("constructionNotes") or gen.get("construction_notes"),
            "finSetupNotes": design.get("finSetup") or gen.get("fin_setup_notes"),
            "rockerNotes": " / ".join(filter(None, [design.get("entryRocker"), design.get("exitRocker")])) or gen.get("rocker_notes"),
            "railNotes": design.get("railType"), "tailNotes": design.get("tailShape") or gen.get("tail_notes"),
            "sourceSummary": reason,
            "manufacturerDescription": description.get("manufacturerDescription") or gen.get("model_description"),
            "sourceUrls": source_urls, "confidence": confidence, "evidenceSources": evidence,
            "missingFields": missing, "reviewedByQuivrr": reviewed_by, "reviewedAtUtc": reviewed_at,
            "volumeRange": board.get("volumeRange", {}), "lengthRangeInches": board.get("lengthRangeInches", {}),
            "reputationSummary": None, "knownFor": [], "strengths": [], "weaknesses": [],
            "bestFor": [], "notIdealFor": [], "notes": None,
            "primaryFamily": primary_family,
            "secondaryTags": secondary_tags,
            "variantType": variant_type,
            "baseModel": base_model,
            "finSetup": fin_setup,
            "abilityPreferred": override.get("abilityPreferred") if override and override.get("abilityPreferred") is not None else family_defaults.get("abilityPreferred", []),
            "fitnessRequirement": override.get("fitnessRequirement") if override and override.get("fitnessRequirement") is not None else family_defaults.get("fitnessRequirement"),
            "surfFrequencyRequirement": override.get("surfFrequencyRequirement") if override and override.get("surfFrequencyRequirement") is not None else family_defaults.get("surfFrequencyRequirement"),
            "paddleSupport": override.get("paddleSupport") if override and override.get("paddleSupport") is not None else family_defaults.get("paddleSupport"),
            "ageModifier": override.get("ageModifier") if override and override.get("ageModifier") is not None else family_defaults.get("ageModifier"),
            "riderWeightMinKg": override.get("riderWeightMinKg") if override else None,
            "riderWeightMaxKg": override.get("riderWeightMaxKg") if override else None,
            "performanceStyle": override.get("performanceStyle") if override else None,
            "foamDistribution": override.get("foamDistribution") if override else None,
            "outlineProfile": override.get("outlineProfile") if override else None,
            "railProfile": override.get("railProfile") if override else None,
            "rockerProfile": override.get("rockerProfile") if override else None,
            "xlVariant": xl_variant,
            "keyTradeOffs": override.get("keyTradeOffs") if override and override.get("keyTradeOffs") is not None else [],
        }
        if override:
            for field in [
                "boardFamily", "reputationSummary", "knownFor", "strengths", "weaknesses", "bestFor",
                "notIdealFor", "waveRangeMinFt", "waveRangeMaxFt", "waveTypes", "wavePower",
                "abilityMin", "abilityMax", "notes", "primaryFamily", "secondaryTags", "variantType",
                "baseModel", "finSetup", "abilityPreferred", "fitnessRequirement",
                "surfFrequencyRequirement", "paddleSupport", "ageModifier", "riderWeightMinKg",
                "riderWeightMaxKg", "performanceStyle", "foamDistribution", "outlineProfile",
                "railProfile", "rockerProfile", "xlVariant", "keyTradeOffs",
            ] + SCORE_FIELDS:
                if override.get(field) is not None:
                    item[field] = override[field]
            item["evidenceSources"]["curatedOverride"] = {
                "source": "quivrr_curated_override", "confidence": confidence, "reason": reason,
                "references": override.get("evidenceSources", []),
            }
        matrix.append(item)

    matrix.sort(key=lambda row: (row["brand"].lower(), row["model"].lower()))
    OUTPUT_PATH.write_text(json.dumps({"schemaVersion": "board_expert_matrix_v1", "boards": matrix}, indent=2, ensure_ascii=False), encoding="utf-8")
    confidence_counts = Counter(row["confidence"] for row in matrix)
    lane_counts = Counter(row["primaryLane"] for row in matrix)
    review = sorted(matrix, key=lambda row: ({"low": 0, "medium": 1, "high": 2}.get(row["confidence"], 0), -len(row["missingFields"]), row["brand"], row["model"]))[:50]
    audit = {
        "totalModels": len(matrix), "modelsWithPrimaryLane": sum(bool(row["primaryLane"]) for row in matrix),
        "modelsWithSecondaryLanes": sum(bool(row["secondaryLanes"]) for row in matrix),
        "modelsWithPrimaryFamily": sum(bool(row.get("primaryFamily")) for row in matrix),
        "variantCoverage": sum(bool(row.get("variantType")) for row in matrix),
        "finSetupCoverage": sum(bool(row.get("finSetup")) for row in matrix),
        "ageSuitabilityCoverage": sum(row.get("ageModifier") is not None for row in matrix),
        "abilityCoverage": sum(bool(row.get("abilityMin") or row.get("abilityMax") or row.get("abilityPreferred")) for row in matrix),
        "confidenceDistribution": dict(sorted(confidence_counts.items())),
        "modelsMissingWaveRange": sum("waveRange" in row["missingFields"] for row in matrix),
        "modelsMissingSurferFit": sum("surferFit" in row["missingFields"] for row in matrix),
        "modelsMissingDesignData": sum("designData" in row["missingFields"] for row in matrix),
        "categoryDistribution": dict(sorted(lane_counts.items())),
        "top50LowConfidenceImportantModels": [{"brand": row["brand"], "model": row["model"], "primaryLane": row["primaryLane"], "missingFields": row["missingFields"]} for row in review],
        "top50ModelsNeedingCuratedReview": [{"brand": row["brand"], "model": row["model"], "reason": ", ".join(row["missingFields"]) or "low confidence lane"} for row in review],
    }
    AUDIT_JSON_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    with AUDIT_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["brand", "model", "boardModelId", "primaryLane", "secondaryLanes", "confidence", "missingFields"])
        writer.writeheader()
        for row in matrix:
            writer.writerow({name: "; ".join(row[name]) if isinstance(row.get(name), list) else row.get(name) for name in writer.fieldnames})
    override_rows = [row for row in matrix if row.get("reviewedByQuivrr")]
    all_lanes = Counter(lane for row in override_rows for lane in [row["primaryLane"], *row.get("secondaryLanes", []), *row.get("boardLanes", [])])
    phase8 = {
        "totalCuratedOverrides": len(override_rows),
        "highConfidenceOverrides": sum(row["confidence"] == "high" for row in override_rows),
        "mediumConfidenceOverrides": sum(row["confidence"] == "medium" for row in override_rows),
        "laneCoverageByCategory": dict(sorted(all_lanes.items())),
        "fishLaneCoverage": {lane: all_lanes.get(lane, 0) for lane in ["traditional_fish", "performance_fish", "cruisy_fish", "small_wave_fish", "point_break_fish", "twin_fin_performance", "twin_fin_cruiser", "fish_hybrid", "keel_fish", "modern_fish"]},
        "dailyDriverLaneCoverage": {lane: all_lanes.get(lane, 0) for lane in ["performance_daily_driver", "forgiving_daily_driver", "hybrid_daily_driver", "small_wave_daily_driver"]},
        "top50LowConfidenceImportantBoards": audit["top50LowConfidenceImportantModels"],
    }
    PHASE8_AUDIT_JSON_PATH.write_text(json.dumps(phase8, indent=2, ensure_ascii=False), encoding="utf-8")
    with PHASE8_AUDIT_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["brand", "model", "primaryLane", "boardLanes", "confidence", "notes"])
        writer.writeheader()
        for row in override_rows:
            writer.writerow({"brand": row["brand"], "model": row["model"], "primaryLane": row["primaryLane"], "boardLanes": "; ".join(row["boardLanes"]), "confidence": row["confidence"], "notes": row.get("notes")})
    print(json.dumps({
        "totalModels": audit["totalModels"],
        "modelsWithPrimaryLane": audit["modelsWithPrimaryLane"],
        "modelsWithSecondaryLanes": audit["modelsWithSecondaryLanes"],
        "confidenceDistribution": audit["confidenceDistribution"],
        "categoryDistribution": audit["categoryDistribution"],
    }, indent=2))


if __name__ == "__main__":
    main()
