from __future__ import annotations

import re

from app.board_graph_engine import board_key, load_graph
from app.inventory_client import enrich_suggestions_concurrently, normalise_region
from app.models import RiderProfile, SuggestedBoard
from app.daily_driver_taxonomy import daily_driver_lane


CATEGORY_ALIASES = {
    "high performance daily driver": "performance_daily_driver",
    "performance daily driver": "performance_daily_driver",
    "fish": "fish", "twin": "fish", "twin fin": "fish",
    "daily driver": "daily_driver", "everyday": "daily_driver",
    "groveller": "groveller", "groveler": "groveller",
    "step up": "step_up", "step-up": "step_up",
    "performance shortboard": "performance_shortboard", "shortboard": "shortboard",
    "mid length": "mid_length", "mid-length": "mid_length",
    "longboard": "longboard", "hybrid": "hybrid",
}
FISH_MODEL_TERMS = ("fish", "twin", "rnf", "seaside", "pisces", "hydra")
VERIFIED_INVENTORY_SNAPSHOT = {
    "AU": {"retailer": 11765, "manufacturer": 6493},
    "EU": {"retailer": 9132, "manufacturer": 2735},
    "ID": {"retailer": 3996, "manufacturer": 184},
}
VERIFIED_INVENTORY_SNAPSHOT_DATE = "20 June 2026"


def extract_category(message: str, preferred: str | None = None) -> str | None:
    text = re.sub(r"[-_]", " ", f"{preferred or ''} {message or ''}".lower())
    for phrase in sorted(CATEGORY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}s?\b", text):
            return CATEGORY_ALIASES[phrase]
    return None


def _category_matches(board: dict, category: str) -> bool:
    taxonomy = board.get("taxonomy", {})
    values = {taxonomy.get("primaryCategory"), *taxonomy.get("secondaryCategories", [])}
    model = board_key("", board.get("model"))[1]
    if category == "shortboard":
        return bool(values & {"daily_driver", "performance_shortboard", "groveller", "fish", "hybrid", "step_up"})
    if category == "fish":
        return "fish" in values or any(term in model for term in FISH_MODEL_TERMS)
    if category == "performance_daily_driver":
        return daily_driver_lane(board.get("brand"), board.get("model")) == "performance_daily_driver"
    return category in values


def _volume_distance(board: dict, target: float | None) -> float:
    if target is None:
        return 0.0
    volume = board.get("volumeRange", {})
    low, high = volume.get("min"), volume.get("max")
    if low is None or high is None:
        return 1.5
    if low <= target <= high:
        return 0.0
    return min(abs(target - low), abs(target - high))


def _to_suggestion(board: dict, category: str, target: float | None) -> SuggestedBoard:
    volume = board.get("volumeRange", {})
    dna = board.get("dna", {})
    wave = dna.get("waveRange", {})
    distance = _volume_distance(board, target)
    why = f"canonical {category.replace('_', ' ')} profile"
    if target is not None:
        why += f" with a size range covering or close to {target:g}L"
    return SuggestedBoard(
        brand=board["brand"], model=board["model"],
        category=board["taxonomy"]["primaryCategory"],
        confidence=max(.55, .9 - distance * .08), why_it_fits=why,
        volume_range=(f"{volume['min']:g}-{volume['max']:g}L" if volume.get("min") is not None else None),
        wave_range=(f"{wave['minFt']:g}-{wave['maxFt']:g}ft" if wave.get("minFt") is not None and wave.get("maxFt") is not None else None),
        skill_fit=(f"{board['surferFit'].get('abilityMin') or 'unspecified'} to {board['surferFit'].get('abilityMax') or 'unspecified'}"),
        source="quivrr_board_graph", board_model_id=board.get("boardModelId"),
    )


def category_candidates(category: str, target: float | None, limit: int = 20) -> list[SuggestedBoard]:
    boards = [
        board for board in load_graph().get("boards", [])
        if board.get("boardModelId") and _category_matches(board, category)
    ]
    boards.sort(key=lambda board: (
        _volume_distance(board, target),
        {"high": 0, "medium": 1, "low": 2}.get(board["taxonomy"].get("confidence"), 3),
        board["brand"], board["model"],
    ))
    selected, brand_counts = [], {}
    for board in boards:
        key = board_key(board["brand"], "")[0]
        if brand_counts.get(key, 0) >= 2:
            continue
        selected.append(board)
        brand_counts[key] = brand_counts.get(key, 0) + 1
        if len(selected) == limit:
            break
    return [_to_suggestion(board, category, target) for board in selected]


def search_live_category(profile: RiderProfile, category: str, limit: int = 20) -> list[SuggestedBoard]:
    target = profile.target_volume_litres
    candidates = category_candidates(category, target, limit)
    live = enrich_suggestions_concurrently(candidates, profile)
    if not profile.construction_preference:
        return [board for board in live if board.available_count > 0]
    exact = [board.model_copy(update={"why_it_fits": board.why_it_fits + "; matches your carbon/epoxy construction preference"})
             for board in live if board.available_count > 0]
    if len(exact) >= 5:
        return exact
    relaxed_profile = profile.model_copy(update={"construction_preference": None})
    relaxed = enrich_suggestions_concurrently(candidates, relaxed_profile)
    seen = {(board.brand.lower(), board.model.lower()) for board in exact}
    close = [board.model_copy(update={"why_it_fits": board.why_it_fits + "; close fit in another construction"})
             for board in relaxed if board.available_count > 0 and (board.brand.lower(), board.model.lower()) not in seen]
    return exact + close


def inventory_snapshot_reply(region: str, category: str | None = None) -> str:
    code = normalise_region(region)
    if not code:
        return "Tell me whether you want Australia, Europe, or Indonesia and I’ll check the right regional stock."
    if category:
        return ""
    counts = VERIFIED_INVENTORY_SNAPSHOT[code]
    total = counts["retailer"] + counts["manufacturer"]
    name = {"AU": "Australia", "EU": "Europe", "ID": "Indonesia"}[code]
    return (
        f"My inventory snapshot verified on {VERIFIED_INVENTORY_SNAPSHOT_DATE} contains roughly {total:,} "
        f"live board listings in {name}: "
        f"{counts['retailer']:,} retailer listings and {counts['manufacturer']:,} manufacturer-direct listings. "
        "Those totals move as feeds refresh. Give me a board type, litres, brand, or model and I’ll check live matching stock."
    )
