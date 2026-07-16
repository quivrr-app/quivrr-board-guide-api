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
OUTPUT = ROOT / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

PRIMARY_CATEGORIES = (
    "traditional_fish",
    "performance_fish",
    "performance_twin",
    "twin_pin",
    "groveller",
    "small_wave_shortboard",
    "hybrid_shortboard",
    "daily_driver",
    "performance_daily_driver",
    "performance_shortboard",
    "step_up",
    "gun",
    "mid_length",
    "performance_mid_length",
    "longboard",
    "softboard",
    "alternative",
)

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

ALL_STRICT_LANES = sorted({lane for values in LANES.values() for lane in values})

CATEGORY_ALIASES = {
    "fish": "traditional_fish",
    "performance fish": "performance_fish",
    "performance twin": "performance_twin",
    "twin pin": "twin_pin",
    "groveller": "groveller",
    "small wave shortboard": "small_wave_shortboard",
    "small wave board": "small_wave_shortboard",
    "hybrid shortboard": "hybrid_shortboard",
    "daily driver": "daily_driver",
    "performance daily driver": "performance_daily_driver",
    "high performance shortboard": "performance_shortboard",
    "performance shortboard": "performance_shortboard",
    "step up": "step_up",
    "gun": "gun",
    "mid length": "mid_length",
    "performance mid length": "performance_mid_length",
    "longboard": "longboard",
    "softboard": "softboard",
    "alternative performance": "alternative",
}

# Strong phrases from the current manufacturer evidence. More specific patterns are
# deliberately evaluated before generic collection/category labels.
PATTERNS = {
    "softboard": [r"\bsoft ?board\b", r"\bfoamie\b", r"\bfoam board\b"],
    "longboard": [r"\blongboard\b", r"\bnose ?rid", r"\btraditional log\b", r"\bsingle fin log\b"],
    "gun": [r"\bbig wave gun\b", r"\btrue gun\b", r"\bserious big wave\b", r"\bouter reef gun\b"],
    "step_up": [r"\bstep[ -]?up\b", r"\bsemi[ -]?gun\b", r"\bsolid surf\b", r"\bheavy water\b", r"\bpowerful surf\b", r"\boverhead and hollow\b"],
    "performance_mid_length": [r"\bperformance mid[ -]?length\b", r"\bmid[ -]?length performance\b", r"\bperformance mid twin\b"],
    "mid_length": [r"\bmid[ -]?length\b", r"\bmidlength\b", r"\bspeed egg\b"],
    "traditional_fish": [r"\btraditional fish\b", r"\bretro fish\b", r"\bkeel fish\b", r"\bclassic fish\b"],
    "performance_fish": [r"\bperformance fish\b", r"\bmodern fish\b", r"\bhigh performance fish\b", r"\bfish-inspired performance\b"],
    "twin_pin": [r"\btwin[ -]?pin\b"],
    "performance_twin": [r"\bperformance twin\b", r"\bhigh performance twin\b", r"\bperformance twin fin\b"],
    "groveller": [r"\bgrovell?er\b", r"\bgrovel board\b", r"\bweak-wave weapon\b", r"\bsmall-wave machine\b"],
    "small_wave_shortboard": [r"\bsmall[ -]?wave shortboard\b", r"\bshortboard for weak waves\b", r"\bsmall-wave performance\b"],
    "performance_daily_driver": [r"\bperformance daily driver\b", r"\bhigh-performance daily driver\b", r"\beveryday performance shortboard\b"],
    "daily_driver": [r"\bdaily driver\b", r"\beveryday board\b", r"\bone-board quiver\b", r"\ball[ -]?rounder\b"],
    "performance_shortboard": [r"\bhigh performance shortboard\b", r"\bperformance shortboard\b", r"\bhpsb\b", r"\bcompetition shortboard\b", r"\bworld tour\b"],
    "hybrid_shortboard": [r"\bhybrid shortboard\b", r"\bhybrid design\b", r"\bshortboard hybrid\b"],
    "alternative": [r"\balternative craft\b", r"\basymmetrical\b", r"\bexperimental design\b"],
}

PADDLE = {
    "traditional_fish": "high",
    "performance_fish": "moderate_high",
    "performance_twin": "moderate",
    "twin_pin": "moderate",
    "groveller": "high",
    "small_wave_shortboard": "moderate_high",
    "hybrid_shortboard": "moderate_high",
    "daily_driver": "moderate",
    "performance_daily_driver": "moderate",
    "performance_shortboard": "low_moderate",
    "step_up": "moderate",
    "gun": "moderate_high",
    "mid_length": "high",
    "performance_mid_length": "high",
    "longboard": "very_high",
    "softboard": "high",
    "alternative": "variable",
}

PERFORMANCE = {
    "traditional_fish": "flow_and_speed",
    "performance_fish": "moderate_high",
    "performance_twin": "high_alternative",
    "twin_pin": "high_in_clean_powerful_faces",
    "groveller": "moderate_small_wave",
    "small_wave_shortboard": "moderate_high_small_wave",
    "hybrid_shortboard": "moderate",
    "daily_driver": "moderate",
    "performance_daily_driver": "high_everyday",
    "performance_shortboard": "very_high",
    "step_up": "high_powerful_wave",
    "gun": "big_wave_control",
    "mid_length": "flow_and_trim",
    "performance_mid_length": "high_for_length",
    "longboard": "trim_glide_and_noseride",
    "softboard": "entry_level",
    "alternative": "variable",
}


def normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalise(value)).strip("-")


def load_source() -> list[dict]:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "QuivrrTaxonomyReview/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)
    if not isinstance(data, list):
        raise RuntimeError("Live board review source is not an array")
    if len(data) != 425:
        raise RuntimeError(f"Expected 425 published review models, received {len(data)}")
    return data


def phrase_score(text: str, category: str) -> tuple[int, list[str]]:
    score = 0
    evidence = []
    for pattern in PATTERNS.get(category, []):
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += 5
            evidence.append(pattern)
    return score, evidence


def wave_power(board: dict, text: str) -> str:
    values = " ".join(str(value) for value in board.get("wavePower", [])).lower()
    joined = f"{values} {text}"
    if re.search(r"\bbig wave|heavy|powerful|solid|overhead|double overhead|hollow|barrel", joined):
        return "powerful"
    if re.search(r"\bweak|soft|small wave|grovel|knee high|waist high|1[-– ]?3", joined):
        return "weak"
    return "moderate"


def classify(board: dict) -> dict:
    existing_label = normalise(board.get("primaryFamily") or board.get("broadFamily"))
    existing = CATEGORY_ALIASES.get(existing_label)
    evidence = normalise(board.get("manufacturerEvidence"))
    source_summary = normalise(board.get("sourceSummary"))
    model = normalise(board.get("model"))
    design = normalise(board.get("designSubtype"))
    fins = " ".join(normalise(value) for value in board.get("finSetup", []))
    waves = " ".join(normalise(value) for value in (board.get("waveTypes", []) + board.get("wavePower", [])))
    notes = " ".join(normalise(board.get(key)) for key in ("rockerNotes", "railNotes", "tailNotes", "performanceStyle", "constructionNotes"))
    text = " ".join((model, existing_label, design, fins, waves, source_summary, evidence, notes))

    scores: Counter[str] = Counter()
    reasons: defaultdict[str, list[str]] = defaultdict(list)

    if existing:
        scores[existing] += 4
        reasons[existing].append(f"current primaryFamily={board.get('primaryFamily')}")

    for category in PRIMARY_CATEGORIES:
        score, matches = phrase_score(text, category)
        scores[category] += score
        reasons[category].extend(matches)

    # Fin configuration is supporting evidence only and can never create a fish classification by itself.
    if "twin" in fins:
        scores["performance_twin"] += 1
        reasons["performance_twin"].append("twin fin supporting evidence")
    if "single" in fins and re.search(r"\b7['’]?|\b8['’]?|\b9['’]?|mid|long", text):
        scores["mid_length"] += 1

    # Model-name evidence is useful but deliberately weaker than manufacturer prose.
    if re.search(r"\bfish\b", model):
        scores["performance_fish"] += 2
        reasons["performance_fish"].append("fish in model name")
    if "twin pin" in model or "twin-pin" in model:
        scores["twin_pin"] += 3
    if re.search(r"\bgun\b", model):
        scores["gun"] += 3
    if re.search(r"\bstep[ -]?up\b", model):
        scores["step_up"] += 3

    # Explicit good-wave and step-up language excludes fish and groveller interpretations.
    powerful = re.search(r"\bstep[ -]?up|semi[ -]?gun|big wave|heavy water|powerful surf|overhead and hollow", text)
    if powerful:
        scores["step_up"] += 5
        scores["traditional_fish"] -= 8
        scores["performance_fish"] -= 8
        scores["groveller"] -= 8

    # A generic twin label must not be treated as fish without fish-specific evidence.
    if "twin" in text and not re.search(r"\bfish|keel|swallow-tail fish|retro fish|modern fish", text):
        scores["traditional_fish"] -= 5
        scores["performance_fish"] -= 3

    proposed = max(PRIMARY_CATEGORIES, key=lambda category: (scores[category], -PRIMARY_CATEGORIES.index(category)))
    if scores[proposed] <= 0:
        proposed = existing or "alternative"

    ordered = [category for category, score in scores.most_common() if category != proposed and score >= 5]
    secondary = ordered[:3]

    top_score = scores[proposed]
    second_score = max((score for category, score in scores.items() if category != proposed), default=0)
    margin = top_score - second_score
    has_detailed_evidence = len(evidence) >= 80
    if has_detailed_evidence and top_score >= 9 and margin >= 3:
        confidence = "high"
    elif has_detailed_evidence and top_score >= 5:
        confidence = "medium"
    else:
        confidence = "review_required"

    classification_status = "proposed_for_owner_review" if confidence != "review_required" else "hold_for_owner_review"
    lanes = LANES[proposed]
    excluded = [lane for lane in ALL_STRICT_LANES if lane not in lanes]

    existing_key = existing or existing_label.replace(" ", "_")
    changed = existing_key != proposed
    change_reason = "; ".join(reasons[proposed][:8]) or "No sufficiently specific evidence; held for owner review"

    return {
        "manufacturer": board.get("brand"),
        "model": board.get("model"),
        "canonical_id": board.get("id"),
        "official_product_url": board.get("officialSourceUrl"),
        "existing_primary_family": board.get("primaryFamily"),
        "existing_design_subtype": board.get("designSubtype"),
        "proposed_primary_category": proposed,
        "secondary_categories": secondary,
        "fin_configuration": board.get("finSetup", []),
        "wave_power": wave_power(board, text),
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
        "classification_status": classification_status,
        "changed_from_current": changed,
        "change_reason": change_reason,
        "review_decision": "",
        "review_notes": "",
    }


def flatten(value: object) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return "" if value is None else str(value)


def main() -> None:
    source = load_source()
    rows = [classify(board) for board in source]
    rows.sort(key=lambda row: (normalise(row["manufacturer"]), normalise(row["model"])))

    master = {
        "schema_version": "quivrr_board_taxonomy_owner_review_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "OWNER_REVIEW_REQUIRED_NOT_RUNTIME_APPROVED",
        "source_authority": SOURCE_URL,
        "source_rule": "Current GitHub and running generated files are authoritative. Architecture/source documents are excluded from classification authority.",
        "model_count": len(rows),
        "models": rows,
    }
    (OUTPUT / "board-taxonomy-owner-review-v1.json").write_text(json.dumps(master, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fields = list(rows[0].keys())
    with (OUTPUT / "board-taxonomy-owner-review-v1.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: flatten(value) for key, value in row.items()} for row in rows)

    by_manufacturer: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_manufacturer[str(row["manufacturer"])].append(row)
    manufacturer_dir = OUTPUT / "manufacturers"
    manufacturer_dir.mkdir(exist_ok=True)
    for manufacturer, manufacturer_rows in sorted(by_manufacturer.items()):
        path = manufacturer_dir / f"{slug(manufacturer)}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: flatten(value) for key, value in row.items()} for row in manufacturer_rows)

    summary = {
        "generated_utc": master["generated_utc"],
        "model_count": len(rows),
        "manufacturer_count": len(by_manufacturer),
        "manufacturer_counts": dict(sorted(Counter(str(row["manufacturer"]) for row in rows).items())),
        "proposed_category_counts": dict(sorted(Counter(str(row["proposed_primary_category"]) for row in rows).items())),
        "confidence_counts": dict(sorted(Counter(str(row["classification_confidence"]) for row in rows).items())),
        "changed_from_current": sum(bool(row["changed_from_current"]) for row in rows),
        "owner_review_required": sum(row["classification_status"] == "hold_for_owner_review" for row in rows),
        "strict_runtime_gate": "Do not consume this taxonomy in runtime until review_decision is completed and approved.",
    }
    (OUTPUT / "board-taxonomy-owner-review-summary-v1.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
