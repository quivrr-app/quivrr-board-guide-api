from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.board_master import load_board_master
KNOWLEDGE = ROOT / "app" / "knowledge"
TAXONOMY_PATH = KNOWLEDGE / "board_taxonomy_v2.json"
PROFILES_PATH = KNOWLEDGE / "generated" / "canonical_board_profiles.json"
MATRIX_PATH = KNOWLEDGE / "generated" / "board_expert_matrix.json"
ARCHETYPES_PATH = KNOWLEDGE / "curated" / "board_dna_archetypes.json"
PUBLIC_FAMILY_OVERRIDES_PATH = KNOWLEDGE / "curated" / "public_family_overrides.json"
DNA_PATH = KNOWLEDGE / "board_dna_v1.json"
AUDIT_DIR = KNOWLEDGE / "audits"

LEGACY_PUBLIC_FAMILY = {
    "traditional_fish": "fish", "performance_fish": "fish", "twin_pin": "fish",
    "groveller": "groveller", "small_wave_shortboard": "groveller", "softboard": "groveller",
    "hybrid_shortboard": "daily_driver", "daily_driver": "daily_driver",
    "performance_daily_driver": "daily_driver", "alternative": "daily_driver",
    "performance_shortboard": "performance_shortboard", "performance_twin": "fish",
    "step_up": "step_up", "gun": "step_up",
    "mid_length": "mid_length", "performance_mid_length": "mid_length",
    "longboard": "longboard",
}

# Public family describes the manufacturer's intended design role. It is not a
# proxy for how often a surfer might ride the board, and Daily Driver is never
# used as a fallback for unknown or ambiguous categories.
PUBLIC_FAMILY = {
    "traditional_fish": "fish", "performance_fish": "fish",
    "groveller": "groveller", "small_wave_shortboard": "groveller", "softboard": "groveller",
    "hybrid_shortboard": "daily_driver", "daily_driver": "daily_driver",
    "performance_daily_driver": "daily_driver",
    "performance_shortboard": "performance_shortboard", "performance_twin": "performance_shortboard",
    "twin_pin": "performance_shortboard",
    "step_up": "step_up", "gun": "step_up",
    "mid_length": "mid_length", "performance_mid_length": "mid_length",
    "longboard": "longboard",
}

PUBLIC_FAMILIES = {
    "fish", "groveller", "daily_driver", "performance_shortboard",
    "step_up", "mid_length", "longboard",
}

MATRIX_METRICS = {
    "paddle": "paddleEaseScore", "wave_entry": "paddleEaseScore",
    "speed_generation": "speedGenerationScore", "drive": "performanceScore",
    "release": "manoeuvrabilityScore", "hold": "holdScore",
    "forgiveness": "forgivenessScore", "stability": "stabilityScore",
    "sensitivity": "performanceScore", "projection": "performanceScore",
    "pivot": "manoeuvrabilityScore", "carve": "manoeuvrabilityScore",
    "glide": "paddleEaseScore", "turning_radius": "stabilityScore",
}

CONDITION_MATRIX = {
    "weak_waves": "smallWaveScore", "average_waves": "dailyDriverScore",
    "powerful_waves": "goodWaveScore", "beach_break": "dailyDriverScore",
    "point_break": "goodWaveScore", "reef_break": "goodWaveScore",
    "hollow_waves": "stepUpScore", "open_face": "goodWaveScore",
}

PHYSICAL_TERMS = {
    "outline": [("parallel", "parallel"), ("wide point forward", "wide_forward"), ("wide nose", "wide_forward"), ("wide outline", "wide_centre"), ("curvy", "curvy"), ("narrow outline", "narrow")],
    "nose": [("pointed nose", "pointed"), ("refined nose", "refined"), ("full nose", "full"), ("wide nose", "full")],
    "rocker_entry": [("high entry rocker", "high"), ("increased entry rocker", "medium_high"), ("medium entry rocker", "medium"), ("low entry rocker", "low"), ("flat entry", "low")],
    "rocker_tail": [("high tail rocker", "high"), ("increased tail rocker", "medium_high"), ("medium tail rocker", "medium"), ("low tail rocker", "low"), ("flat tail", "low")],
    "rails": [("refined rails", "refined"), ("low rails", "low_performance"), ("thin rails", "low_performance"), ("full rails", "full"), ("soft rails", "soft")],
    "foil": [("forward foil", "forward"), ("rear foil", "rear"), ("refined foil", "refined")],
    "volume_distribution": [("foam under the chest", "forward"), ("volume forward", "forward"), ("rear volume", "rear"), ("central volume", "central")],
}

TAIL_TERMS = ["round pin", "swallow", "squash", "square", "diamond", "pin", "round", "thumb", "asym"]
BOTTOM_TERMS = ["single", "double", "vee", "v out", "channels", "channel", "concave", "rolled", "flat"]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    return payload.get("models") or payload.get("boards") or []


def _key(brand: str, model: str) -> str:
    normalise = lambda value: re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return f"{normalise(brand)}::{normalise(model)}"


def _clamp(value: float) -> int:
    return max(1, min(10, int(round(value))))


def _matrix_value(matrix: dict, field: str) -> int | None:
    value = matrix.get(field)
    if value is None:
        value = (matrix.get("scores") or {}).get(field)
    if value is None:
        return None
    number = float(value)
    return _clamp(1 + number * 0.09) if number > 10 else _clamp(number)


def _metric_vector(names: list[str], baseline: list[int], matrix: dict, mapping: dict[str, str]) -> dict[str, int]:
    vector = dict(zip(names, baseline, strict=True))
    for metric, matrix_field in mapping.items():
        observed = _matrix_value(matrix, matrix_field)
        if observed is not None:
            vector[metric] = _clamp(vector[metric] * 0.65 + observed * 0.35)
    return vector


def _physical(archetype: dict, evidence: str, taxonomy: dict, matrix: dict) -> tuple[dict, int]:
    values = archetype["physical"]
    physical = {
        "outline": values[0], "nose": values[1], "tail": [values[2]],
        "rocker_entry": values[3], "rocker_tail": values[4], "rails": values[5],
        "foil": values[6], "volume_distribution": values[7],
        "bottom_contours": values[8].split(","),
        "fin_configurations": taxonomy.get("fin_configuration") or values[9].split(","),
    }
    explicit = 0
    for field, matches in PHYSICAL_TERMS.items():
        for phrase, result in matches:
            if phrase in evidence:
                physical[field] = result
                explicit += 1
                break
    tails = [term.replace(" ", "_") for term in TAIL_TERMS if re.search(rf"\b{re.escape(term)}(?: tail)?\b", evidence)]
    if tails:
        physical["tail"] = list(dict.fromkeys(tails))
        explicit += 1
    bottoms = []
    for term in BOTTOM_TERMS:
        if term in evidence:
            normalised = {"v out": "vee", "channel": "channels", "concave": "single"}.get(term, term)
            bottoms.append(normalised)
    if bottoms:
        physical["bottom_contours"] = list(dict.fromkeys(bottoms))
        explicit += 1
    for source, target in (("outlineProfile", "outline"), ("rockerProfile", "rocker_entry"), ("railProfile", "rails")):
        if matrix.get(source) and explicit < 2:
            raw = str(matrix[source]).lower().replace(" ", "_")
            allowed = {
                "outline": {"parallel", "curvy", "balanced", "wide_forward", "wide_centre", "narrow"},
                "rocker_entry": {"low", "medium_low", "medium", "medium_high", "high"},
                "rails": {"soft", "full", "medium", "refined", "low_performance"},
            }[target]
            if raw in allowed:
                physical[target] = raw
    return physical, explicit


def _apply_rules(vectors: dict[str, dict[str, int]], evidence: str, rules: list[dict]) -> list[str]:
    notes = []
    for rule in rules:
        matched = next((phrase for phrase in rule["match"] if phrase in evidence), None)
        if not matched:
            continue
        for metric, delta in rule["effects"].items():
            for vector in vectors.values():
                if metric in vector:
                    vector[metric] = _clamp(vector[metric] + delta)
                    break
        notes.append(f"Applied governed evidence rule: {matched}.")
    return notes


def _rider_vector(names: list[str], baseline: list[int], taxonomy: dict) -> dict[str, int]:
    vector = dict(zip(names, baseline, strict=True))
    ability = [str(value).lower() for value in taxonomy.get("ability_range") or []]
    order = ["beginner", "progressing", "intermediate", "advanced", "expert"]
    for index, metric in enumerate(order):
        if metric in ability:
            vector[metric] = max(vector[metric], 6 + min(4, index))
    if ability == ["expert"]:
        vector["advanced"] = 3
    elif "advanced" not in ability:
        vector["advanced"] = min(vector["advanced"], 4)
    elif "beginner" in ability:
        vector["advanced"] = 7
    elif "progressing" in ability:
        vector["advanced"] = 8
    elif "intermediate" in ability:
        vector["advanced"] = 9
    else:
        vector["advanced"] = 10
    return vector


def _confidence(explicit: int, evidence: str, taxonomy: dict) -> tuple[str, str, bool]:
    official = bool(taxonomy.get("source_url"))
    if explicit >= 3 and len(evidence) >= 220 and official:
        return "high", "explicit_manufacturer", False
    if explicit or (len(evidence) >= 100 and official):
        return "medium", "manufacturer_inference", False
    return "low", "governed_archetype_with_modifiers", True


def _style_tags(archetype: dict, behaviour: dict) -> list[str]:
    tags = list(archetype["tags"])
    derived = {
        "fast": behaviour["speed_generation"] >= 8,
        "drivey": behaviour["drive"] >= 8,
        "forgiving": behaviour["forgiveness"] >= 8,
        "stable": behaviour["stability"] >= 8,
        "sensitive": behaviour["sensitivity"] >= 9,
        "glide": behaviour["glide"] >= 8,
    }
    return list(dict.fromkeys(tags + [tag for tag, applies in derived.items() if applies]))


def _minimum_ability(rider: dict) -> str:
    for ability in ("beginner", "progressing", "intermediate", "advanced", "expert"):
        if rider[ability] >= 6:
            return ability
    return "expert"


def build() -> list[dict]:
    taxonomy_rows = _rows(_load(TAXONOMY_PATH))
    profiles = {_key(row.get("brand", ""), row.get("model", "")): row for row in _rows(_load(PROFILES_PATH))}
    matrix_rows = _rows(_load(MATRIX_PATH))
    matrix_by_id = {int(row["boardModelId"]): row for row in matrix_rows if row.get("boardModelId") is not None}
    config = _load(ARCHETYPES_PATH)
    family_governance = _load(PUBLIC_FAMILY_OVERRIDES_PATH)
    family_overrides = {int(row["canonical_model_id"]): row for row in family_governance["overrides"]}
    names = config["metric_order"]
    models = []

    for taxonomy in taxonomy_rows:
        category = taxonomy["primary_category"]
        archetype_key = category if category in config["archetypes"] else "alternative"
        archetype = config["archetypes"][archetype_key]
        model_id = int(taxonomy["canonical_model_id"])
        matrix = matrix_by_id.get(model_id, {})
        profile = profiles.get(_key(taxonomy["brand"], taxonomy["model"]), {})
        evidence_text = " ".join(filter(None, [
            taxonomy.get("manufacturer_evidence"), profile.get("manufacturerDescription"),
            matrix.get("manufacturerDescription"), matrix.get("designNotes"), matrix.get("outlineNotes"),
            matrix.get("rockerNotes"), matrix.get("railNotes"), matrix.get("bottomContourNotes"),
        ])).lower()
        physical, explicit = _physical(archetype, evidence_text, taxonomy, matrix)
        behaviour = _metric_vector(names["behaviour"], archetype["behaviour"], matrix, MATRIX_METRICS)
        conditions = _metric_vector(names["conditions"], archetype["conditions"], matrix, CONDITION_MATRIX)
        wave_power = taxonomy.get("wave_power") or []
        wave_power = [wave_power] if isinstance(wave_power, str) else wave_power
        normalised_power = {str(value).lower() for value in wave_power}
        if "weak" in normalised_power:
            conditions["average_waves"] = _clamp(conditions["average_waves"] - 1)
        if normalised_power.intersection({"powerful", "strong", "high"}):
            conditions["average_waves"] = _clamp(conditions["average_waves"] + 1)
        rider = _rider_vector(names["rider_fit"], archetype["rider_fit"], taxonomy)
        notes = _apply_rules({"behaviour": behaviour, "conditions": conditions, "rider": rider}, evidence_text, config["transformation_rules"])
        confidence, method, review_required = _confidence(explicit, evidence_text, taxonomy)
        legacy_override = config.get("model_overrides", {}).get(taxonomy["canonical_key"], {})
        legacy_public_family = legacy_override.get("public_family", LEGACY_PUBLIC_FAMILY[archetype_key])
        if archetype_key not in PUBLIC_FAMILY:
            raise ValueError(f"No governed public-family mapping for {taxonomy['canonical_key']}: {archetype_key}")
        base_public_family = PUBLIC_FAMILY[archetype_key]
        family_override = family_overrides.get(model_id)
        if family_override:
            if family_override["brand"].casefold() != taxonomy["brand"].casefold() or family_override["model"].casefold() != taxonomy["model"].casefold():
                raise ValueError(f"Public-family override identity mismatch for canonical model {model_id}")
            public_family = family_override["public_family"]
            family_reason = family_override["reason"]
            notes.append(f"Curated public-family authority: {family_reason}")
        else:
            public_family = base_public_family
            family_reason = f"Deterministic mapping from governed primary category {category}."
        if public_family not in PUBLIC_FAMILIES:
            raise ValueError(f"Unsupported public family for {taxonomy['canonical_key']}: {public_family}")
        notes.extend(legacy_override.get("notes", []))
        models.append({
            "canonical_model_id": model_id,
            "canonical_key": taxonomy["canonical_key"],
            "brand": taxonomy["brand"], "model": taxonomy["model"],
            "public_family": public_family,
            "primary_category": category,
            "secondary_categories": taxonomy.get("secondary_categories") or [],
            "aliases": taxonomy.get("aliases") or [],
            "physical_design": physical,
            "behaviour": behaviour, "conditions": conditions, "rider_fit": rider,
            "style_tags": _style_tags(archetype, behaviour),
            "quiver_roles": archetype["roles"],
            "family_governance": {
                "previous_public_family": legacy_public_family,
                "base_public_family": base_public_family,
                "override_applied": family_override is not None,
                "reason": family_reason,
            },
            "evidence": {
                "official_source_url": taxonomy.get("source_url"),
                "manufacturer_description": taxonomy.get("manufacturer_evidence"),
                "physical_design_confidence": confidence,
                "behaviour_confidence": confidence,
                "condition_confidence": confidence,
                "rider_fit_confidence": confidence,
                "source_method": method,
                "review_required": review_required,
                "notes": notes + (["Archetype-led record requires editorial review."] if review_required else []),
            },
        })
    # Phase 3 models are promoted directly from the governed Board Master.
    # They intentionally bypass the legacy research taxonomy input so a future
    # generation cannot silently drop accepted manufacturer evidence.
    generated_ids = {row["canonical_model_id"] for row in models}
    for master in load_board_master()["models"]:
        model_id = int(master["canonical_model_id"])
        if model_id in generated_ids:
            continue
        dna = master["board_dna"]
        models.append({
            "canonical_model_id": model_id,
            "canonical_key": master["canonical_key"],
            "brand": master["manufacturer"], "model": master["model"],
            "public_family": master["public_family"],
            "primary_category": re.sub(r"[^a-z0-9]+", "_", master["detailed_category"].lower()).strip("_"),
            "secondary_categories": list(master.get("secondary_categories") or []), "aliases": [],
            "physical_design": dna["physical_design"], "behaviour": dna["behaviour"],
            "conditions": dna["conditions"], "rider_fit": dna["rider_fit"],
            "style_tags": dna.get("style_tags") or [], "quiver_roles": dna.get("quiver_roles") or [],
            "family_governance": {
                "previous_public_family": master.get("previous_public_family"),
                "base_public_family": master["public_family"], "override_applied": True,
                "reason": "; ".join(master.get("editorial_notes") or []),
            },
            "evidence": {
                "official_source_url": master["official_url"],
                "manufacturer_description": master["manufacturer_intent"],
                "physical_design_confidence": master["confidence"],
                "behaviour_confidence": master["confidence"],
                "condition_confidence": master["confidence"],
                "rider_fit_confidence": master["confidence"],
                "source_method": "governed_board_master_phase3", "review_required": master["review_required"],
                "notes": list(master.get("editorial_notes") or []),
            },
        })
    generated_ids = {row["canonical_model_id"] for row in models}
    unused_overrides = sorted(set(family_overrides) - generated_ids)
    if unused_overrides:
        raise ValueError(f"Public-family overrides do not resolve to governed models: {unused_overrides}")
    return sorted(models, key=lambda row: (row["brand"].lower(), row["model"].lower()))


def _write_audits(models: list[dict]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["CanonicalModelId", "Brand", "Model", "PublicFamily", "PrimaryCategory", "Paddle", "SpeedGeneration", "Drive", "Release", "Hold", "Forgiveness", "Stability", "Sensitivity", "Glide", "WeakWaves", "PowerfulWaves", "BeachBreak", "PointBreak", "ReefBreak", "MinimumAbility", "SourceMethod", "PhysicalConfidence", "BehaviourConfidence", "ReviewRequired", "ReviewNotes"]
    rows = []
    for model in models:
        b, c, r, e = model["behaviour"], model["conditions"], model["rider_fit"], model["evidence"]
        rows.append(dict(zip(fields, [
            model["canonical_model_id"], model["brand"], model["model"], model["public_family"], model["primary_category"],
            b["paddle"], b["speed_generation"], b["drive"], b["release"], b["hold"], b["forgiveness"], b["stability"], b["sensitivity"], b["glide"],
            c["weak_waves"], c["powerful_waves"], c["beach_break"], c["point_break"], c["reef_break"], _minimum_ability(r),
            e["source_method"], e["physical_design_confidence"], e["behaviour_confidence"], e["review_required"], " ".join(e["notes"]),
        ], strict=True)))
    with (AUDIT_DIR / "board_dna_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with (AUDIT_DIR / "board_dna_review_required.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows([row for row in rows if row["ReviewRequired"]])

    def counts(field):
        output = {}
        for row in models:
            value = field(row)
            output[value] = output.get(value, 0) + 1
        return dict(sorted(output.items()))
    audit = {
        "model_count": len(models),
        "by_manufacturer": counts(lambda row: row["brand"]),
        "by_public_family": counts(lambda row: row["public_family"]),
        "by_primary_category": counts(lambda row: row["primary_category"]),
        "by_confidence": counts(lambda row: row["evidence"]["behaviour_confidence"]),
        "by_source_method": counts(lambda row: row["evidence"]["source_method"]),
        "by_review_required": counts(lambda row: str(row["evidence"]["review_required"]).lower()),
    }
    (AUDIT_DIR / "board_dna_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    family_review_fields = [
        "CanonicalModelId", "Brand", "Model", "CurrentPublicFamily", "ProposedPublicFamily",
        "PrimaryCategory", "SecondaryCategories", "ManufacturerIntent", "DNAEvidence", "WaveIntent",
        "Rocker", "Rails", "Outline", "PerformanceScore", "ForgivenessScore", "WeakWaveScore",
        "PowerfulWaveScore", "Changed", "ChangeReason", "Confidence", "ReviewRequired",
    ]
    family_review_rows = []
    for model in models:
        behaviour, conditions, physical = model["behaviour"], model["conditions"], model["physical_design"]
        governance, evidence = model["family_governance"], model["evidence"]
        manufacturer_intent = " ".join((evidence.get("manufacturer_description") or "").split())[:600]
        family_review_rows.append({
            "CanonicalModelId": model["canonical_model_id"],
            "Brand": model["brand"],
            "Model": model["model"],
            "CurrentPublicFamily": governance["previous_public_family"],
            "ProposedPublicFamily": model["public_family"],
            "PrimaryCategory": model["primary_category"],
            "SecondaryCategories": ",".join(model["secondary_categories"]),
            "ManufacturerIntent": manufacturer_intent,
            "DNAEvidence": f"method={evidence['source_method']}; style={','.join(model['style_tags'])}; roles={','.join(model['quiver_roles'])}",
            "WaveIntent": json.dumps(conditions, sort_keys=True, separators=(",", ":")),
            "Rocker": f"entry={physical['rocker_entry']};tail={physical['rocker_tail']}",
            "Rails": physical["rails"],
            "Outline": physical["outline"],
            "PerformanceScore": round(sum(behaviour[key] for key in ("drive", "release", "hold", "sensitivity")) / 4, 2),
            "ForgivenessScore": behaviour["forgiveness"],
            "WeakWaveScore": conditions["weak_waves"],
            "PowerfulWaveScore": conditions["powerful_waves"],
            "Changed": governance["previous_public_family"] != model["public_family"],
            "ChangeReason": governance["reason"],
            "Confidence": evidence["behaviour_confidence"],
            "ReviewRequired": evidence["review_required"],
        })
    with (AUDIT_DIR / "public_family_review_v2.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=family_review_fields)
        writer.writeheader()
        writer.writerows(family_review_rows)
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}
    for row in family_review_rows:
        before_counts[row["CurrentPublicFamily"]] = before_counts.get(row["CurrentPublicFamily"], 0) + 1
        after_counts[row["ProposedPublicFamily"]] = after_counts.get(row["ProposedPublicFamily"], 0) + 1
    family_review_payload = {
        "schema_version": 2,
        "model_count": len(models),
        "current_family_counts": dict(sorted(before_counts.items())),
        "proposed_family_counts": dict(sorted(after_counts.items())),
        "changed_count": sum(bool(row["Changed"]) for row in family_review_rows),
        "records": family_review_rows,
    }
    (AUDIT_DIR / "public_family_review_v2.json").write_text(
        json.dumps(family_review_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    distribution = {"model_count": len(models), "metrics": {}, "family_averages": {}}
    for section in ("behaviour", "conditions", "rider_fit"):
        for metric in models[0][section]:
            values = [row[section][metric] for row in models]
            distribution["metrics"][f"{section}.{metric}"] = {"minimum": min(values), "maximum": max(values), "distinct_values": sorted(set(values)), "average": round(sum(values) / len(values), 2)}
    for family in sorted(set(row["public_family"] for row in models)):
        family_rows = [row for row in models if row["public_family"] == family]
        distribution["family_averages"][family] = {
            metric: round(sum(row["behaviour"][metric] for row in family_rows) / len(family_rows), 2)
            for metric in models[0]["behaviour"]
        }
    (AUDIT_DIR / "board_dna_distribution.json").write_text(json.dumps(distribution, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    models = build()
    payload = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "model_count": len(models), "models": models}
    DNA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    _write_audits(models)
    print(json.dumps({"model_count": len(models), "manufacturers": len(set(row["brand"] for row in models)), "review_required": sum(row["evidence"]["review_required"] for row in models)}, indent=2))


if __name__ == "__main__":
    main()
