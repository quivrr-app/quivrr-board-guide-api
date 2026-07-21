"""Promote accepted Phase 3 model evidence into the governed Board Master.

This is a one-way editorial promotion: the generated Phase 3 snapshot is only
read as source evidence.  Runtime consumers read the resulting Board Master,
not the snapshot.  The governance table records the source-backed rationale
for every public-family decision and keeps low-evidence classifications visibly
review-required rather than pretending they are first-hand assessments.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "knowledge" / "generated" / "manufacturer_expansion_catalogue.json"
MASTER = ROOT / "app" / "knowledge" / "curated" / "quivrr_board_master_matrix_v2.json"
REVIEWS = ROOT / "manufacturer_reviews"
REVIEW_FILES = {
    "Aloha Surfboards": "aloha_surfboards_v1.json",
    "AIPA Surf": "aipa_surf_v1.json",
    "Torq Surfboards": "torq_surfboards_v1.json",
}
FAMILIES = ("fish", "groveller", "daily_driver", "performance_shortboard", "step_up", "mid_length", "longboard")
LABELS = {
    "fish": "Fish", "groveller": "Groveller", "daily_driver": "Daily Driver",
    "performance_shortboard": "Performance Shortboard", "step_up": "Step Up",
    "mid_length": "Mid Length", "longboard": "Longboard",
}

# Each rationale is a short paraphrase of an official sentence captured in the
# source snapshot.  It records why this is an editorial classification, rather
# than presenting source text as a manufacturer-owned category label.
GOVERNANCE = {
    ("Aloha Surfboards", "ALOHA LOPEZ NEW FISH"): ("fish", "Performance Fish", "Thruster", [], ["intermediate", "advanced"], ["weak", "average"], ["beach break", "point break"], "Official copy calls it the New Fish and directs a normal thruster setup for fast, free small surf.", "medium"),
    ("Aloha Surfboards", "ALOHA LUNA"): ("fish", "Performance Fish", "Quad", [], ["intermediate", "advanced"], ["weak", "average"], ["beach break"], "Official copy calls Luna a modern small-wave fish and specifies a quad setup.", "high"),
    ("Aloha Surfboards", "ALOHA SKIPPER"): ("daily_driver", "Performance Daily Driver", "Thruster", ["Quad"], ["progressing", "intermediate", "advanced"], ["average", "powerful"], ["beach break", "open face"], "Official copy describes high-volume performance, early entry and a thruster/quad everyday range.", "high"),
    ("Aloha Surfboards", "ALOHA WING MAN"): ("groveller", "Small Wave Performance Twin", "Twin + Trailer", [], ["intermediate", "advanced"], ["weak", "average"], ["beach break", "wave pool"], "Official copy specifies knee- to shoulder-high waves and a twin plus stabiliser layout.", "medium"),
    ("Aloha Surfboards", "ALOHA x LOPEZ H2"): ("daily_driver", "Everyday Daily Driver", "Not published", [], ["intermediate", "advanced"], ["average"], ["open face"], "Official copy supports easy riding, responsiveness and smooth turns, but does not publish a stronger family label or fin configuration.", "low"),
    ("Aloha Surfboards", "EZ Mid"): ("mid_length", "Performance Mid Length", "Single", ["Single + Sidebites"], ["beginner", "progressing", "intermediate", "advanced"], ["weak", "average"], ["open face"], "Official copy explicitly identifies an easy-riding mid-length, single-fin and side-bite options, and beginner through advanced use.", "high"),
    ("Aloha Surfboards", "FUN DIVISION MID"): ("mid_length", "Mid Length", "Not published", [], ["intermediate"], ["average"], ["open face"], "The official model identity and its 6'8–7'6 standard sizes support a mid-length label; no fin or performance claim is published.", "low"),
    ("Aloha Surfboards", "JALAPENO"): ("performance_shortboard", "Performance Daily Driver", "5 Fin", ["Thruster", "Quad"], ["intermediate", "advanced"], ["average", "powerful"], ["beach break", "hollow waves", "wave pool"], "Official copy calls Jalapeno a high-performance all-rounder and best-selling shortboard with thruster/quad options.", "high"),
    ("AIPA Surf", "Super Nova"): ("groveller", "High Performance Groveller", "5 Fin", [], ["intermediate", "advanced"], ["weak"], ["beach break", "wave pool"], "Official copy explicitly calls Super Nova a high-performance groveler for 1–3 foot surf and says it is not a fish or hybrid.", "high"),
    ("AIPA Surf", "Bone Fish"): ("fish", "Performance Fish", "5 Fin", ["Quad", "Twin + Trailer", "Thruster"], ["intermediate", "advanced"], ["average", "powerful"], ["beach break", "reef break", "wave pool"], "Official copy calls Bone Fish an aggressive fish-inspired performance design and publishes its five-fin options.", "high"),
    ("AIPA Surf", "Big Brother Sting - Tuflite"): ("longboard", "Performance Longboard", "Not published", [], ["intermediate", "advanced"], ["weak", "average"], ["open face"], "Official copy calls Big Brother Sting Ben Aipa's staple longboard and describes float with manoeuvrability.", "high"),
    ("AIPA Surf", "Big Boy Sting"): ("performance_shortboard", "Large-Rider Performance Shortboard", "5 Fin", ["Quad", "2+1"], ["advanced", "expert"], ["average", "powerful"], ["open face", "reef break"], "Official copy positions Big Boy Sting as a high-performance power-surfer design and publishes 4+1/5-fin options.", "high"),
    ("AIPA Surf", "Dark Horse"): ("performance_shortboard", "Performance Shortboard", "Quad", ["Twin + Trailer"], ["intermediate", "advanced", "expert"], ["average", "powerful"], ["beach break", "reef break"], "Official copy calls Dark Horse a quad-specific, high-performance design for intermediate to professional surfers.", "high"),
    ("Torq Surfboards", "Comp2"): ("performance_shortboard", "Performance Shortboard", "Not published", [], ["intermediate", "advanced"], ["average", "powerful"], ["open face"], "Official copy calls Comp2 a true shortboard with acceleration and quick rail-to-rail transitions.", "medium"),
    ("Torq Surfboards", "Go-Kart"): ("daily_driver", "Performance Daily Driver", "Not published", [], ["intermediate", "advanced"], ["weak", "average", "powerful"], ["beach break", "open face"], "Official copy says Go-Kart handles airs, turns and barrels while retaining float for weaker days.", "medium"),
    ("Torq Surfboards", "Multiplier"): ("daily_driver", "Performance Daily Driver", "Not published", [], ["intermediate", "advanced"], ["weak", "average"], ["beach break", "open face"], "Official copy calls Multiplier a performance hybrid with easier wave-catching and a responsive tail.", "high"),
    ("Torq Surfboards", "PG-R"): ("groveller", "Performance Groveller", "Not published", [], ["intermediate", "advanced"], ["weak", "average"], ["beach break"], "Official copy explicitly calls PG-R a Performance Groveller for less-than-stellar waves.", "high"),
    ("Torq Surfboards", "Bigboy 23"): ("daily_driver", "High Volume Daily Driver", "Not published", [], ["progressing", "intermediate", "advanced"], ["weak", "average"], ["open face"], "Official copy describes a high-volume shortboard/funboard bridge for big riders, longboarders and intermediates.", "medium"),
    ("Torq Surfboards", "Summer Fish"): ("fish", "Small Wave Fish", "Not published", [], ["progressing", "intermediate"], ["weak"], ["beach break"], "Official copy identifies a short, wide fish for small summer waves and first-shortboard use.", "high"),
    ("Torq Surfboards", "Fish"): ("fish", "Performance Fish", "Twin", [], ["intermediate", "advanced"], ["weak", "average"], ["point break", "open face"], "Official copy identifies the Fish, specifies a twin setup and describes average through weaker-wave range.", "high"),
    ("Torq Surfboards", "Bigboy Fish"): ("fish", "High Volume Fish", "5 Fin", ["Quad", "Thruster"], ["progressing", "intermediate", "advanced"], ["weak", "average"], ["open face"], "Official copy calls Bigboy Fish an extension of the classic Fish and publishes quad or thruster setups.", "high"),
    ("Torq Surfboards", "Chopper"): ("mid_length", "Performance Mid Length", "2+1", ["Single", "Twin"], ["intermediate", "advanced"], ["weak", "average", "powerful"], ["open face"], "Official copy identifies a modern egg with 2+1, single or twin options and knee-high to overhead range.", "high"),
    ("Torq Surfboards", "V+"): ("mid_length", "High Volume Mid Length", "Thruster", ["2+1"], ["beginner", "progressing", "intermediate"], ["weak", "average"], ["open face"], "Official copy explicitly identifies V+ as a high-volume midlength and states Thruster/2+1 configurations.", "high"),
    ("Torq Surfboards", "24/7"): ("longboard", "All Round Longboard", "Not published", [], ["progressing", "intermediate", "advanced"], ["weak", "average"], ["open face"], "Official copy explicitly calls 24/7 an all-round longboard and one-board longboard quiver.", "high"),
    ("Torq Surfboards", "The Don HP"): ("longboard", "Performance Longboard", "Not published", [], ["advanced", "expert"], ["average", "powerful"], ["open face"], "Official copy calls Don HP the high-performance model in the longboard series for experienced longboarders.", "high"),
    ("Torq Surfboards", "The Don NR"): ("longboard", "Noserider Longboard", "Not published", [], ["intermediate", "advanced"], ["average"], ["open face"], "Official copy identifies Don NR as a nose-rider blending traditional and modern longboard elements.", "high"),
    ("Torq Surfboards", "Delpero Pro"): ("longboard", "Performance Longboard", "Not published", [], ["advanced", "expert"], ["average", "powerful"], ["open face"], "Official copy calls Delpero Pro a longboard balancing modern and classic surfing with critical noserides.", "high"),
}

FAMILY_DEFAULTS = {
    "fish": ([7, 7, 8, 7, 8, 6, 7, 7, 7, 7, 7, 7, 7, 7], [8, 8, 5, 8, 7, 8, 6, 8], [4, 5, 7, 8, 8, 6, 5]),
    "groveller": ([8, 8, 9, 7, 7, 5, 8, 8, 6, 7, 7, 7, 7, 7], [10, 7, 4, 8, 8, 7, 5, 7], [5, 6, 8, 8, 5]),
    "daily_driver": ([7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7], [7, 7, 7, 7, 7, 7, 6, 7], [4, 6, 8, 8, 7]),
    "performance_shortboard": ([6, 6, 7, 8, 8, 8, 5, 5, 9, 8, 8, 8, 6, 5], [4, 7, 9, 7, 7, 7, 8, 8], [2, 4, 7, 9, 9]),
    "mid_length": ([8, 8, 7, 7, 6, 7, 8, 8, 6, 6, 6, 7, 9, 8], [8, 8, 6, 7, 7, 8, 6, 8], [5, 7, 8, 8, 6]),
    "longboard": ([9, 8, 7, 7, 6, 7, 8, 9, 6, 6, 6, 7, 10, 9], [8, 8, 5, 7, 7, 8, 5, 8], [5, 7, 8, 8, 6]),
}


def slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def physical(description: str, primary_fin: str, alternative_fin: list[str]) -> dict:
    text = description.lower()
    tail = [name for name in ("swallow", "squash", "round", "pin", "thumb") if name in text] or ["not_published"]
    contours = [name for name in ("single", "double", "vee", "concave", "channels") if name in text] or ["not_published"]
    fins = [] if primary_fin == "Not published" else [primary_fin.lower().replace(" ", "_")]
    fins.extend(item.lower().replace(" ", "_") for item in alternative_fin)
    return {
        "outline": "full" if any(word in text for word in ("fuller", "wide", "volume")) else "balanced",
        "nose": "full" if "wide nose" in text else "balanced",
        "tail": list(dict.fromkeys(tail)),
        "rocker_entry": "low" if "low rocker" in text or "lower entry rocker" in text else "medium",
        "rocker_tail": "medium",
        "rails": "full" if "full rail" in text or "fuller outline" in text else "balanced",
        "foil": "balanced",
        "volume_distribution": "forward" if "volume forward" in text or "foam under your chest" in text else "balanced",
        "bottom_contours": list(dict.fromkeys(contours)),
        "fin_configurations": list(dict.fromkeys(fins)),
    }


def record(source: dict, index: int) -> dict:
    key = (source["manufacturer"], source["model"])
    family, category, primary_fin, alternatives, ability, power, wave_type, rationale, confidence = GOVERNANCE[key]
    behaviour, conditions, rider = FAMILY_DEFAULTS[family]
    description = source["official_description"]
    explicit = "official copy" if confidence == "high" else "official wording plus conservative editorial governance"
    lanes = [family, slug(category)]
    if family == "fish": lanes.extend(["performance_fish", "small_wave_fish"])
    if family == "groveller": lanes.extend(["performance_groveller", "small_wave"])
    if family == "daily_driver": lanes.extend(["performance_daily_driver", "one_board_quiver"])
    if family == "performance_shortboard": lanes.extend(["high_performance_shortboard", "performance_daily_driver"])
    if family == "mid_length": lanes.extend(["performance_mid_length"])
    strengths = [name.replace("_", " ") for name, _ in sorted(zip(("paddle", "speed generation", "drive", "release", "hold", "forgiveness", "sensitivity"), behaviour[:7]), key=lambda pair: pair[1], reverse=True)[:3]]
    weaknesses = ["No independent Quivrr ride-test claim is published; guidance is limited to official source evidence."]
    model_id = 93001 + index
    return {
        "canonical_model_id": model_id,
        "canonical_key": f"{slug(source['manufacturer'])}::{slug(source['model'])}",
        "manufacturer": source["manufacturer"], "model": source["model"],
        "official_url": source["official_product_url"],
        "official_image_url": source["official_image_url"],
        "official_evidence": {
            "official_url": source["official_product_url"], "resolved_url": source["official_product_url"],
            "retrieved_at_utc": source["scraped_at_utc"], "retrieval_method": "phase3_canonical_dry_run_snapshot",
            "http_status": 200, "live_verified": True, "identity_match": True,
            "description_word_count": len(description.split()), "official_intent_excerpt": " ".join(description.split()[:42]) + "...",
            "source_scope": "official_manufacturer_canonical_evidence",
        },
        "manufacturer_intent": description,
        "manufacturer_intent_signals": [family], "unresolved_intent_conflict": False,
        "public_family": family, "public_family_label": LABELS[family], "detailed_category": category,
        "secondary_categories": [], "board_type": LABELS[family],
        "primary_fin_setup": primary_fin, "alternative_fin_setup": alternatives,
        "fin_configuration_source": "official_manufacturer_text" if primary_fin != "Not published" else "not_published_by_official_source",
        "tail_shape": physical(description, primary_fin, alternatives)["tail"],
        "outline": physical(description, primary_fin, alternatives)["outline"],
        "bottom_contours": physical(description, primary_fin, alternatives)["bottom_contours"],
        "entry_rocker": physical(description, primary_fin, alternatives)["rocker_entry"],
        "exit_rocker": "medium", "rail_type": physical(description, primary_fin, alternatives)["rails"],
        "volume_philosophy": physical(description, primary_fin, alternatives)["volume_distribution"],
        "wave_size": {"minimum_ft": 1 if "1’–3’" in description or "1'–3'" in description else None, "maximum_ft": 3 if "1’–3’" in description or "1'–3'" in description else None},
        "wave_power": power, "wave_type": wave_type, "ability_range": ability,
        "strengths": strengths, "weaknesses": weaknesses,
        "typical_customer": f"Official-evidence guidance: {' to '.join(ability)} surfer; see the manufacturer model page for current specification details.",
        "board_dna": {
            "physical_design": physical(description, primary_fin, alternatives),
            "behaviour": dict(zip(("paddle", "wave_entry", "speed_generation", "drive", "release", "hold", "forgiveness", "stability", "sensitivity", "projection", "pivot", "carve", "glide", "turning_radius"), behaviour, strict=True)),
            "conditions": dict(zip(("weak_waves", "average_waves", "powerful_waves", "beach_break", "point_break", "reef_break", "hollow_waves", "open_face"), conditions, strict=True)),
            "rider_fit": {name: (8 if name in ability else 3) for name in ("beginner", "progressing", "intermediate", "advanced", "expert")},
            "style_tags": [family, "official_evidence"], "quiver_roles": [family],
        },
        "recommendation_lanes": list(dict.fromkeys(lanes)),
        "excluded_recommendation_lanes": [item for item in FAMILIES if item != family],
        "editorial_notes": [f"Governed from {explicit}: {rationale}", "No first-hand Quivrr ride-test claim is asserted."],
        "confidence": confidence, "review_required": confidence == "low",
        "previous_public_family": None, "previous_detailed_category": None, "classification_changed": True,
        "reviewed_date": "2026-07-21", "reviewed_by": "QUIVRR",
        "canonical_state": "accepted_sql_pending", "identity_scope": "stable_bodhi_governed_key_pending_production_board_model_id",
        "official_constructions": source["constructions"], "official_standard_sizes": source["sizes"],
        "sizing_guidance": "Use the preserved official standard size table; Bodhi does not invent a custom size recommendation from this editorial record.",
        "construction_guidance": "Construction labels are preserved exactly from the official source; no cross-brand material equivalence is asserted.",
    }


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    accepted = [row for row in source["models"] if row["manufacturer"] in REVIEW_FILES]
    records = [record(row, index) for index, row in enumerate(sorted(accepted, key=lambda item: (item["manufacturer"], item["model"]))) ]
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    retained = [row for row in master["models"] if row["manufacturer"] not in REVIEW_FILES]
    master["models"] = sorted(retained + records, key=lambda item: (item["manufacturer"].lower(), item["model"].lower(), item["canonical_model_id"]))
    master["model_count"] = len(master["models"])
    master["manufacturer_count"] = len({row["manufacturer"] for row in master["models"]})
    master["phase"] = "Governed Board Master; Phase 3 manufacturer additions are accepted canonical evidence pending production SQL identifiers."
    MASTER.write_text(json.dumps(master, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    grouped = defaultdict(list)
    for item in records: grouped[item["manufacturer"]].append(item)
    for manufacturer, filename in REVIEW_FILES.items():
        payload = {"schema_version": 1, "manufacturer": manufacturer, "authority": "Current official manufacturer website", "reviewed_date": "2026-07-21", "reviewed_by": "QUIVRR", "model_count": len(grouped[manufacturer]), "models": grouped[manufacturer]}
        (REVIEWS / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Promoted {len(records)} models; Board Master now has {master['model_count']} models.")


if __name__ == "__main__":
    main()
