from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://quivrr.surf/seo-data/knowledge/board-reviews.json"
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output-v2"
OUTPUT.mkdir(parents=True, exist_ok=True)

CATEGORY_MAP = {
    "Fish": "traditional_fish",
    "Performance Fish": "performance_fish",
    "Performance Twin": "performance_twin",
    "Twin Pin": "twin_pin",
    "Groveller": "groveller",
    "Small Wave Shortboard": "small_wave_shortboard",
    "Hybrid Shortboard": "hybrid_shortboard",
    "Daily Driver": "daily_driver",
    "Performance Daily Driver": "performance_daily_driver",
    "High Performance Shortboard": "performance_shortboard",
    "Performance Shortboard": "performance_shortboard",
    "Step Up": "step_up",
    "Gun": "gun",
    "Mid Length": "mid_length",
    "Performance Mid Length": "performance_mid_length",
    "Longboard": "longboard",
    "Softboard": "softboard",
    "Alternative Performance": "alternative",
}

PRIMARY_CATEGORIES = tuple(dict.fromkeys(CATEGORY_MAP.values()))

LANES = {
    "traditional_fish": ["fish", "traditional_fish", "weak_wave", "flow"],
    "performance_fish": ["fish", "performance_fish", "small_wave", "daily_driver"],
    "performance_twin": ["performance_twin", "alternative", "daily_driver"],
    "twin_pin": ["twin_pin", "performance_twin", "point_break", "alternative"],
    "groveller": ["groveller", "small_wave", "weak_wave"],
    "small_wave_shortboard": ["small_wave_shortboard", "small_wave", "daily_driver"],
    "hybrid_shortboard": ["hybrid_shortboard", "daily_driver", "forgiving_shortboard"],
    "daily_driver": ["daily_driver", "everyday"],
    "performance_daily_driver": ["performance_daily_driver", "daily_driver", "performance_shortboard"],
    "performance_shortboard": ["performance_shortboard", "good_wave", "competition"],
    "step_up": ["step_up", "powerful_wave", "hollow_wave"],
    "gun": ["gun", "big_wave"],
    "mid_length": ["mid_length", "paddle_support", "flow"],
    "performance_mid_length": ["performance_mid_length", "mid_length", "point_break"],
    "longboard": ["longboard", "paddle_support", "small_wave"],
    "softboard": ["softboard", "beginner"],
    "alternative": ["alternative"],
}
ALL_LANES = sorted({lane for values in LANES.values() for lane in values})

PADDLE = {
    "traditional_fish": "high", "performance_fish": "moderate_high", "performance_twin": "moderate",
    "twin_pin": "moderate", "groveller": "high", "small_wave_shortboard": "moderate_high",
    "hybrid_shortboard": "moderate_high", "daily_driver": "moderate", "performance_daily_driver": "moderate",
    "performance_shortboard": "low_moderate", "step_up": "moderate", "gun": "moderate_high",
    "mid_length": "high", "performance_mid_length": "high", "longboard": "very_high",
    "softboard": "high", "alternative": "variable",
}
PERFORMANCE = {
    "traditional_fish": "flow_and_speed", "performance_fish": "moderate_high",
    "performance_twin": "high_alternative", "twin_pin": "high_clean_wave_control",
    "groveller": "moderate_small_wave", "small_wave_shortboard": "moderate_high_small_wave",
    "hybrid_shortboard": "moderate", "daily_driver": "moderate", "performance_daily_driver": "high_everyday",
    "performance_shortboard": "very_high", "step_up": "high_powerful_wave", "gun": "big_wave_control",
    "mid_length": "flow_and_trim", "performance_mid_length": "high_for_length",
    "longboard": "trim_glide_and_noseride", "softboard": "entry_level", "alternative": "variable",
}

# Explicit owner-validated or evidence-obvious corrections. These are still proposals for Nathan's review.
MANUAL_PROPOSALS = {
    ("Lost", "El Patron"): ("step_up", ["performance_shortboard"], "Owner identified El Patron as a larger-wave thruster; current fish family and Twin/Quad metadata conflict with that use."),
    ("Lost", "Big Rig Driver"): ("performance_shortboard", ["performance_daily_driver"], "Manufacturer evidence explicitly says Pro-Formance Series Shortboard and says it is for surfers who do not want hybrids, mids or fish."),
    ("Lost", "Cali Twin Pin"): ("twin_pin", ["performance_twin"], "Model name and manufacturer evidence explicitly identify a twin pin."),
    ("Lost", "Driver 3.0 Grom"): ("performance_shortboard", [], "Manufacturer evidence describes a top-tier performance board derived from the Driver competition line."),
    ("Lost", "Driver 3.0 Round"): ("performance_shortboard", [], "Manufacturer evidence describes an elite-team World Tour Driver design rather than a hybrid daily driver."),
    ("Lost", "Driver 3.0 Squash"): ("performance_shortboard", [], "Manufacturer evidence describes an elite-team World Tour Driver design rather than a hybrid daily driver."),
}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(value)).strip("-")


def load_source() -> list[dict]:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "QuivrrTaxonomyReview/2.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
    if not isinstance(data, list) or len(data) != 425:
        raise RuntimeError(f"Expected 425 live published models, received {len(data) if isinstance(data, list) else type(data)}")
    return data


def contains(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def fish_is_negated(text: str) -> bool:
    return contains(
        text,
        r"\bnot (?:a |another )?(?:true )?fish\b",
        r"\bdo(?:n't| not) want[^.]{0,100}\bfish\b",
        r"\bwithout[^.]{0,80}\bfish\b",
        r"\brelegated to riding[^.]{0,100}\bfishy?\b",
        r"\bmore shortboard than fish\b",
    )


def explicit_category(text: str, model: str, current: str) -> tuple[str | None, list[str], list[str]]:
    reasons: list[str] = []
    flags: list[str] = []

    if contains(text, r"\bsoft ?board\b", r"\bfoamie\b"):
        return "softboard", reasons + ["explicit softboard language"], flags
    if contains(text, r"\blongboard\b", r"\bnose ?rider\b", r"\btraditional log\b"):
        return "longboard", reasons + ["explicit longboard or log language"], flags
    if contains(text, r"\bbig wave gun\b", r"\btrue gun\b", r"\bserious big wave\b"):
        return "gun", reasons + ["explicit gun language"], flags
    if contains(text, r"\bperformance mid[ -]?length\b", r"\bhigh performance mid[ -]?length\b"):
        return "performance_mid_length", reasons + ["explicit performance mid-length language"], flags
    if contains(text, r"\bmid[ -]?length\b", r"\bmidlength\b", r"\bspeed egg\b"):
        return "mid_length", reasons + ["explicit mid-length language"], flags
    if contains(text, r"\btwin[ -]?pin\b") or "twin pin" in model:
        return "twin_pin", reasons + ["explicit twin-pin language"], flags
    if contains(text, r"\btraditional fish\b", r"\bretro fish\b", r"\bkeel fish\b", r"\bclassic fish\b") and not fish_is_negated(text):
        return "traditional_fish", reasons + ["explicit traditional fish language"], flags
    if contains(text, r"\bperformance fish\b", r"\bmodern fish\b", r"\bhigh performance fish\b") and not fish_is_negated(text):
        return "performance_fish", reasons + ["explicit performance fish language"], flags
    if contains(text, r"\bperformance twin\b", r"\bhigh performance twin\b", r"\bperformance twin fin\b"):
        return "performance_twin", reasons + ["explicit performance twin language"], flags
    if contains(text, r"\bgrovell?er\b", r"\bgrovel board\b", r"\bweak-wave weapon\b", r"\bsmall-wave machine\b"):
        return "groveller", reasons + ["explicit groveller or weak-wave-machine language"], flags
    if contains(text, r"\bsmall[ -]?wave shortboard\b", r"\bshortboard for weak waves\b", r"\bsmall-wave performance shortboard\b"):
        return "small_wave_shortboard", reasons + ["explicit small-wave shortboard language"], flags
    if contains(text, r"\bstep[ -]?up\b", r"\bsemi[ -]?gun\b"):
        return "step_up", reasons + ["explicit step-up or semi-gun language"], flags
    if contains(text, r"\bhigh performance shortboard\b", r"\bperformance shortboard\b", r"\bhpsb\b", r"\bpro-?formance(?: series)? shortboard\b", r"\bcompetition shortboard\b"):
        return "performance_shortboard", reasons + ["explicit performance-shortboard language"], flags
    if contains(text, r"\bperformance daily driver\b", r"\bhigh-performance daily driver\b", r"\beveryday performance shortboard\b"):
        return "performance_daily_driver", reasons + ["explicit performance daily-driver language"], flags
    if contains(text, r"\bdaily driver\b", r"\bone-board quiver\b", r"\beveryday board\b", r"\ball[ -]?rounder\b"):
        return "daily_driver", reasons + ["explicit daily-driver or all-rounder language"], flags
    if contains(text, r"\bhybrid shortboard\b", r"\bhybrid design\b"):
        return "hybrid_shortboard", reasons + ["explicit hybrid-shortboard language"], flags

    if fish_is_negated(text) and current in {"traditional_fish", "performance_fish"}:
        flags.append("current fish classification conflicts with manufacturer evidence")
    return None, reasons, flags


def classify(board: dict) -> dict:
    brand = str(board.get("brand") or "")
    model_name = str(board.get("model") or "")
    current_label = str(board.get("primaryFamily") or "")
    current = CATEGORY_MAP.get(current_label, "alternative")
    evidence = norm(board.get("manufacturerEvidence"))
    design = norm(board.get("designSubtype"))
    summary = norm(board.get("sourceSummary"))
    fins = " ".join(norm(item) for item in board.get("finSetup", []))
    wave_terms = " ".join(norm(item) for item in (board.get("waveTypes", []) + board.get("wavePower", [])))
    technical = " ".join(norm(board.get(key)) for key in ("rockerNotes", "railNotes", "tailNotes", "performanceStyle"))
    text = " ".join((norm(model_name), norm(current_label), design, summary, evidence, fins, wave_terms, technical))

    reasons: list[str] = []
    flags: list[str] = []
    secondary: list[str] = []

    manual = MANUAL_PROPOSALS.get((brand, model_name))
    if manual:
        proposed, secondary, manual_reason = manual
        reasons.append(manual_reason)
        flags.append("manual editorial proposal requiring owner approval")
    else:
        explicit, explicit_reasons, explicit_flags = explicit_category(text, norm(model_name), current)
        flags.extend(explicit_flags)
        if explicit:
            proposed = explicit
            reasons.extend(explicit_reasons)
        else:
            proposed = current
            reasons.append(f"retained current running primaryFamily={current_label}")

    # Adjacent families are recorded but do not become strict category membership.
    if proposed == "performance_shortboard" and contains(text, r"\bdaily driver\b", r"\beveryday\b", r"\ball[ -]?rounder\b"):
        secondary.append("performance_daily_driver")
    if proposed == "performance_daily_driver" and contains(text, r"\bhigh performance shortboard\b", r"\bcompetition\b"):
        secondary.append("performance_shortboard")
    if proposed == "performance_twin" and contains(text, r"\bfish\b") and not fish_is_negated(text):
        secondary.append("performance_fish")
    if proposed == "twin_pin" and "performance_twin" not in secondary:
        secondary.append("performance_twin")
    if proposed == "step_up" and contains(text, r"\bperformance shortboard\b", r"\bpro-?formance\b"):
        secondary.append("performance_shortboard")

    # Conflict checks are deliberately broad so Nathan sees questionable rows.
    if proposed in {"traditional_fish", "performance_fish"} and fish_is_negated(text):
        flags.append("fish language is negated in manufacturer evidence")
    if current in {"traditional_fish", "performance_fish"} and contains(text, r"\bpro-?formance(?: series)? shortboard\b", r"\bhigh performance shortboard\b"):
        flags.append("current fish family conflicts with explicit performance-shortboard evidence")
    if current == "hybrid_shortboard" and contains(text, r"\bworld tour\b", r"\belite[- ]level team\b", r"\bcompetition shortboard\b"):
        flags.append("current hybrid family may conflict with competition-board evidence")
    if "twin pin" in norm(model_name) and proposed != "twin_pin":
        flags.append("model name explicitly says twin pin")
    if proposed == "step_up" and not contains(text, r"\bstep[ -]?up\b", r"\bsemi[ -]?gun\b", r"\bpowerful\b", r"\boverhead\b", r"\bhollow\b", r"\bbigger waves\b"):
        flags.append("step-up proposal needs owner confirmation of wave intent")

    changed = proposed != current
    confidence = "high"
    if manual or flags:
        confidence = "owner_review_required"
    elif len(evidence) < 120:
        confidence = "medium"
    if proposed == "alternative" or not evidence:
        confidence = "owner_review_required"

    lanes = LANES[proposed]
    excluded = [lane for lane in ALL_LANES if lane not in lanes]

    wave_text = f"{wave_terms} {evidence}"
    if contains(wave_text, r"\bbig wave\b", r"\bheavy\b", r"\bpowerful\b", r"\boverhead\b", r"\bhollow\b", r"\bbarrel\b"):
        wave_power = "powerful"
    elif contains(wave_text, r"\bweak\b", r"\bsoft\b", r"\bsmall wave\b", r"\bgrovel\b"):
        wave_power = "weak"
    else:
        wave_power = "moderate"

    return {
        "manufacturer": brand,
        "model": model_name,
        "canonical_id": board.get("id"),
        "official_product_url": board.get("officialSourceUrl"),
        "existing_primary_family": current_label,
        "existing_design_subtype": board.get("designSubtype"),
        "proposed_primary_category": proposed,
        "secondary_categories": sorted(set(secondary)),
        "fin_configuration": board.get("finSetup", []),
        "wave_power": wave_power,
        "wave_types": board.get("waveTypes", []),
        "ability_range": board.get("abilityPreferred", []),
        "paddle_profile": PADDLE[proposed],
        "performance_profile": PERFORMANCE[proposed],
        "recommendation_lanes": lanes,
        "excluded_lanes": excluded,
        "source_summary": board.get("sourceSummary"),
        "manufacturer_evidence": board.get("manufacturerEvidence"),
        "rocker_notes": board.get("rockerNotes"),
        "rail_notes": board.get("railNotes"),
        "tail_notes": board.get("tailNotes"),
        "key_trade_offs": board.get("keyTradeOffs", []),
        "source_confidence": board.get("confidence"),
        "classification_confidence": confidence,
        "classification_status": "proposed_for_owner_review",
        "changed_from_current": changed,
        "conflict_flags": sorted(set(flags)),
        "change_reason": "; ".join(reasons),
        "review_decision": "",
        "review_notes": "",
    }


def flatten(value: object) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return "" if value is None else str(value)


def main() -> None:
    rows = [classify(board) for board in load_source()]
    rows.sort(key=lambda row: (norm(row["manufacturer"]), norm(row["model"])))

    payload = {
        "schema_version": "quivrr_board_taxonomy_owner_review_v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "OWNER_REVIEW_REQUIRED_NOT_RUNTIME_APPROVED",
        "source_authority": SOURCE_URL,
        "source_rule": "Current GitHub and running generated files are authoritative. Uploaded architecture/source documents are excluded from classification authority.",
        "model_count": len(rows),
        "models": rows,
    }
    (OUTPUT / "board-taxonomy-owner-review-v2.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fields = list(rows[0].keys())
    with (OUTPUT / "board-taxonomy-owner-review-v2.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: flatten(value) for key, value in row.items()} for row in rows)

    by_manufacturer: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_manufacturer[str(row["manufacturer"])].append(row)
    manufacturer_dir = OUTPUT / "manufacturers"
    manufacturer_dir.mkdir(exist_ok=True)
    for manufacturer, manufacturer_rows in sorted(by_manufacturer.items()):
        with (manufacturer_dir / f"{slug(manufacturer)}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: flatten(value) for key, value in row.items()} for row in manufacturer_rows)

    summary = {
        "generated_utc": payload["generated_utc"],
        "model_count": len(rows),
        "manufacturer_count": len(by_manufacturer),
        "manufacturer_counts": dict(sorted(Counter(str(row["manufacturer"]) for row in rows).items())),
        "proposed_category_counts": dict(sorted(Counter(str(row["proposed_primary_category"]) for row in rows).items())),
        "confidence_counts": dict(sorted(Counter(str(row["classification_confidence"]) for row in rows).items())),
        "changed_from_current": sum(bool(row["changed_from_current"]) for row in rows),
        "rows_with_conflict_flags": sum(bool(row["conflict_flags"]) for row in rows),
        "strict_runtime_gate": "Do not consume this taxonomy in runtime until Nathan completes review_decision and approves the dataset.",
    }
    (OUTPUT / "board-taxonomy-owner-review-summary-v2.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
