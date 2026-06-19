from __future__ import annotations

import json
import re
from pathlib import Path


GRAPH_PATH = Path(__file__).parent / "knowledge" / "generated" / "board_recommendation_graph.json"
ALLOWED_CATEGORIES = {
    "daily_driver", "performance_shortboard", "groveller", "fish", "hybrid", "step_up",
    "gun", "mid_length", "longboard", "softboard", "youth", "foil",
}
CATEGORY_ALIASES = {"high_performance": "performance_shortboard"}
LEVELS = {"low": 1, "medium": 2, "high": 3}

TAXONOMY_OVERRIDES = {
    ("haydenshapes", "hypto krypto"): ("hybrid", ["daily_driver"]),
    ("pyzel", "ghost"): ("step_up", ["performance_shortboard"]),
    ("js industries", "monsta"): ("performance_shortboard", ["daily_driver"]),
    ("lost", "rnf 96"): ("fish", ["groveller"]),
    ("firewire", "seaside"): ("fish", ["hybrid"]),
    ("pyzel", "phantom"): ("daily_driver", ["performance_shortboard"]),
    ("sharp eye", "inferno 72"): ("performance_shortboard", ["daily_driver"]),
    ("pyzel", "gremlin"): ("groveller", ["daily_driver"]),
}

CURATED_RELATIONSHIPS = {
    ("js industries", "monsta"): {
        "similarBoards": [
            ("Pyzel", "Phantom"), ("Sharp Eye", "Inferno 72"),
            ("Channel Islands", "happy-everyday"),
        ],
        "alternativeBoards": [("DHD", "MF DNA"), ("Lost", "Driver 3.0 Squash")],
        "upgradeBoards": [("Pyzel", "Ghost")],
        "downgradeBoards": [("Haydenshapes", "Hypto Krypto")],
    },
}


def normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def board_key(brand: object, model: object) -> tuple[str, str]:
    return normalise(brand), normalise(model)


def _description(profile: dict) -> str:
    return str(profile.get("description", {}).get("manufacturerDescription") or "").lower()


def _canonical_category(value: object) -> str | None:
    category = CATEGORY_ALIASES.get(normalise(value).replace(" ", "_"), normalise(value).replace(" ", "_"))
    return category if category in ALLOWED_CATEGORIES else None


def assign_taxonomy(profile: dict, size_stats: dict | None = None) -> dict:
    identity = profile["identity"]
    override = TAXONOMY_OVERRIDES.get(board_key(identity["brand"], identity["model"]))
    if override:
        return {"primaryCategory": override[0], "secondaryCategories": override[1], "confidence": "high", "source": "reviewed_deterministic_override"}

    harvested = profile.get("category", {})
    primary = _canonical_category(harvested.get("primaryCategory"))
    secondary = [value for value in (_canonical_category(item) for item in harvested.get("secondaryCategories", [])) if value and value != primary]
    if primary:
        confidence = harvested.get("categoryConfidence") or "low"
        return {"primaryCategory": primary, "secondaryCategories": sorted(set(secondary)), "confidence": confidence, "source": harvested.get("categorySource") or "canonical_harvest"}

    text = " ".join([normalise(identity.get("model")), _description(profile)])
    rules = [
        ("softboard", r"\bsoftboard|foamie\b"), ("foil", r"\bfoil board|hydrofoil\b"),
        ("youth", r"\byouth|grom\b"), ("longboard", r"\blongboard|noserider|nose rider\b"),
        ("mid_length", r"\bmid length|midlength|egg\b"), ("gun", r"\bbig wave gun|retro gun\b"),
        ("step_up", r"\bstep up|stepup|semi gun\b"), ("groveller", r"\bgrovell?er|small wave machine\b"),
        ("fish", r"\bfish|twin keel|keel fish\b"), ("performance_shortboard", r"\bperformance shortboard|pro model\b"),
        ("daily_driver", r"\bdaily driver|everyday shortboard|one board quiver|all rounder\b"),
        ("hybrid", r"\bhybrid\b"),
    ]
    for category, pattern in rules:
        if re.search(pattern, text):
            return {"primaryCategory": category, "secondaryCategories": [], "confidence": "medium", "source": "deterministic_manufacturer_text"}

    size_stats = size_stats or {}
    maximum = size_stats.get("maxLengthInches")
    if maximum is not None and maximum >= 108:
        return {"primaryCategory": "longboard", "secondaryCategories": [], "confidence": "medium", "source": "deterministic_length_taxonomy"}
    if maximum is not None and maximum >= 84:
        return {"primaryCategory": "mid_length", "secondaryCategories": [], "confidence": "low", "source": "deterministic_length_taxonomy"}
    return {"primaryCategory": "hybrid", "secondaryCategories": [], "confidence": "low", "source": "conservative_shortboard_fallback"}


def _level(value: int) -> str:
    return {1: "low", 2: "medium", 3: "high"}[max(1, min(3, value))]


def build_board_dna(profile: dict, taxonomy: dict) -> dict:
    category = taxonomy["primaryCategory"]
    secondary = set(taxonomy["secondaryCategories"])
    text = _description(profile)
    paddle = 2
    turning = 2
    forgiveness = 2
    performance = 2
    if category in {"groveller", "fish", "hybrid", "mid_length", "longboard", "softboard"}:
        paddle += 1; forgiveness += 1
    if category in {"performance_shortboard", "step_up", "gun"}:
        performance += 1; forgiveness -= 1
    if category in {"performance_shortboard", "fish", "hybrid"}:
        turning += 1
    if "daily_driver" in secondary:
        forgiveness += 1
    if "performance_shortboard" in secondary:
        performance += 1
    if re.search(r"easy padd|paddle power|wave catching|wave-catching|extra volume|fuller outline", text):
        paddle += 1
    if re.search(r"forgiving|user friendly|user-friendly|stable|easy to surf", text):
        forgiveness += 1
    if re.search(r"critical|elite performance|high performance|professional", text):
        performance += 1
    if re.search(r"tight turns|rail to rail|responsive|pivot", text):
        turning += 1
    personality = {
        "performance_shortboard": "precise_and_responsive", "step_up": "controlled_in_power",
        "gun": "maximum_hold", "groveller": "fast_and_forgiving", "fish": "fast_and_loose",
        "hybrid": "versatile_and_forgiving", "daily_driver": "balanced_everyday_performance",
        "mid_length": "glide_and_early_entry", "longboard": "stable_glide", "softboard": "maximum_forgiveness",
        "youth": "scaled_performance", "foil": "foil_specific",
    }[category]
    wave = profile.get("wave", {})
    return {
        "boardPersonality": personality,
        "waveRange": {"minFt": wave.get("waveHeightMinFt"), "maxFt": wave.get("waveHeightMaxFt")},
        "wavePower": wave.get("wavePower") or [],
        "paddlingBias": _level(paddle), "turningBias": _level(turning),
        "forgiveness": _level(forgiveness), "performanceBias": _level(performance),
        "source": "deterministic_canonical_intelligence", "confidence": taxonomy["confidence"],
    }


def range_overlap(left: dict, right: dict) -> float:
    if left.get("min") is None or left.get("max") is None or right.get("min") is None or right.get("max") is None:
        return 0.0
    intersection = max(0.0, min(left["max"], right["max"]) - max(left["min"], right["min"]))
    union = max(left["max"], right["max"]) - min(left["min"], right["min"])
    return intersection / union if union else 1.0


def similarity_score(left: dict, right: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    lt, rt = left["taxonomy"], right["taxonomy"]
    if lt["primaryCategory"] == rt["primaryCategory"]:
        score += 35; reasons.append("same primary category")
    shared = set([lt["primaryCategory"], *lt["secondaryCategories"]]) & set([rt["primaryCategory"], *rt["secondaryCategories"]])
    if shared and lt["primaryCategory"] != rt["primaryCategory"]:
        score += 15; reasons.append("compatible category")
    wave_overlap = range_overlap(
        {"min": left["dna"]["waveRange"]["minFt"], "max": left["dna"]["waveRange"]["maxFt"]},
        {"min": right["dna"]["waveRange"]["minFt"], "max": right["dna"]["waveRange"]["maxFt"]},
    )
    if wave_overlap >= 0.5:
        score += 20; reasons.append("similar wave range")
    shared_power = set(left["dna"]["wavePower"]) & set(right["dna"]["wavePower"])
    if shared_power:
        score += 8; reasons.append("similar wave power")
    for field, label in [("paddlingBias", "paddling"), ("turningBias", "turning"), ("forgiveness", "forgiveness"), ("performanceBias", "performance")]:
        difference = abs(LEVELS[left["dna"][field]] - LEVELS[right["dna"][field]])
        if difference == 0:
            score += 5; reasons.append(f"similar {label}")
        elif difference == 1:
            score += 2
    volume_overlap = range_overlap(left.get("volumeRange", {}), right.get("volumeRange", {}))
    if volume_overlap >= 0.4:
        score += 10; reasons.append("overlapping volume range")
    return min(score, 100), reasons


def edge(candidate: dict, score: int, reasons: list[str]) -> dict:
    confidence = "high" if score >= 75 else "medium" if score >= 55 else "low"
    return {
        "brand": candidate["brand"], "model": candidate["model"],
        "boardModelId": candidate.get("boardModelId"), "primaryCategory": candidate["taxonomy"]["primaryCategory"],
        "confidence": confidence, "score": score, "reason": ", ".join(reasons[:4]),
    }


def build_relations(target: dict, candidates: list[dict], limit: int = 5) -> dict:
    scored = []
    for candidate in candidates:
        if candidate is target:
            continue
        score, reasons = similarity_score(target, candidate)
        if score >= 35:
            scored.append((score, candidate, reasons))
    scored.sort(key=lambda row: (-row[0], row[1]["brand"], row[1]["model"]))
    same = [row for row in scored if row[1]["taxonomy"]["primaryCategory"] == target["taxonomy"]["primaryCategory"]]
    alternatives = [row for row in scored if row not in same]
    target_perf = LEVELS[target["dna"]["performanceBias"]]
    target_forgive = LEVELS[target["dna"]["forgiveness"]]
    upgrades = [row for row in scored if LEVELS[row[1]["dna"]["performanceBias"]] > target_perf]
    downgrades = [row for row in scored if LEVELS[row[1]["dna"]["forgiveness"]] > target_forgive]
    output = {
        "similarBoards": [edge(candidate, score, reasons) for score, candidate, reasons in same[:limit]],
        "alternativeBoards": [edge(candidate, score, reasons) for score, candidate, reasons in alternatives[:limit]],
        "upgradeBoards": [edge(candidate, score, reasons + ["higher performance bias"]) for score, candidate, reasons in upgrades[:limit]],
        "downgradeBoards": [edge(candidate, score, reasons + ["more forgiving profile"]) for score, candidate, reasons in downgrades[:limit]],
    }
    curated = CURATED_RELATIONSHIPS.get(board_key(target["brand"], target["model"]), {})
    candidate_map = {board_key(candidate["brand"], candidate["model"]): candidate for candidate in candidates}
    for relation, requested in curated.items():
        additions = []
        for brand, model in requested:
            candidate = candidate_map.get(board_key(brand, model))
            if not candidate:
                continue
            score, reasons = similarity_score(target, candidate)
            additions.append(edge(candidate, max(score, 80), reasons + ["Quivrr-reviewed deterministic relationship"]))
        existing = {board_key(item["brand"], item["model"]) for item in additions}
        output[relation] = additions + [item for item in output[relation] if board_key(item["brand"], item["model"]) not in existing]
        output[relation] = output[relation][:limit]
    return output


def load_graph(path: Path = GRAPH_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_board(graph: dict, brand: str, model: str) -> dict | None:
    target = board_key(brand, model)
    return next((row for row in graph.get("boards", []) if board_key(row.get("brand"), row.get("model")) == target), None)


def compare_boards(graph: dict, left_brand: str, left_model: str, right_brand: str, right_model: str) -> dict | None:
    left, right = find_board(graph, left_brand, left_model), find_board(graph, right_brand, right_model)
    if not left or not right:
        return None
    fields = ["waveRange", "wavePower", "paddlingBias", "turningBias", "forgiveness", "performanceBias"]
    return {
        "left": {"brand": left["brand"], "model": left["model"], "category": left["taxonomy"], "recommendedSurfer": left.get("surferFit"), **{field: left["dna"][field] for field in fields}},
        "right": {"brand": right["brand"], "model": right["model"], "category": right["taxonomy"], "recommendedSurfer": right.get("surferFit"), **{field: right["dna"][field] for field in fields}},
        "explanation": "Deterministic comparison from canonical taxonomy, manufacturer metadata, and Board DNA.",
    }


def available_replacements(graph: dict, brand: str, model: str, volume: float | None, region: str, availability: dict) -> list[dict]:
    target = find_board(graph, brand, model)
    if not target or region not in {"AU", "EU", "ID"}:
        return []
    edges = []
    for relation in ["similarBoards", "alternativeBoards", "downgradeBoards", "upgradeBoards"]:
        for item in target["recommendations"].get(relation, []):
            candidate_key = board_key(item["brand"], item["model"])
            rows = [row for row in availability.get(candidate_key, []) if row.get("RegionCode") == region and row.get("IsAvailable") is not False]
            candidate = find_board(graph, item["brand"], item["model"])
            volume_range = candidate.get("volumeRange", {}) if candidate else {}
            if volume is None or volume_range.get("min") is None:
                distance = 0.0
            elif volume_range["min"] <= volume <= volume_range["max"]:
                distance = 0.0
            else:
                distance = min(abs(volume - volume_range["min"]), abs(volume - volume_range["max"]))
            edges.append({**item, "relation": relation, "isAvailable": bool(rows), "availableCount": len(rows), "volumeDistance": round(distance, 2), "region": region})
    deduped = {}
    for item in edges:
        item_key = board_key(item["brand"], item["model"])
        current = deduped.get(item_key)
        if current is None or (item["isAvailable"], -item["volumeDistance"], item["score"]) > (current["isAvailable"], -current["volumeDistance"], current["score"]):
            deduped[item_key] = item
    return sorted(deduped.values(), key=lambda item: (not item["isAvailable"], item["volumeDistance"], -item["score"], item["brand"], item["model"]))
