from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.board_expert_matrix import find_matrix_board
from app.board_relationships import normalize_relationship_type
from app.models import RiderProfile, SuggestedBoard
from app.board_reputation import relationship_expert_intro


GRAPH_PATH = Path(__file__).parent / "knowledge/generated/board_relationship_graph.json"


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


@lru_cache(maxsize=1)
def load_relationship_graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8-sig"))


def find_relationship_board(brand: str, model: str) -> dict | None:
    wanted = (_key(brand), _key(model))
    return next((row for row in load_relationship_graph()["boards"] if (_key(row["brand"]), _key(row["model"])) == wanted), None)


def relationship_type(message: str) -> str | None:
    text = _key(message)
    if any(token in text for token in ("fish alternative", "fish version", "as a fish")):
        return normalize_relationship_type("fishAlternativeBoards")
    if any(token in text for token in ("shortboard alternative", "shortboard version", "as a shortboard")):
        return normalize_relationship_type("shortboardAlternativeBoards")
    if any(token in text for token in ("step up from", "next board after", "after my")):
        return normalize_relationship_type("stepUpFromBoards")
    if any(token in text for token in ("step down from", "step down", "less demanding")):
        return normalize_relationship_type("stepDownFromBoards")
    if any(token in text for token in ("more paddle", "easier paddle", "paddles better", "catch more waves")):
        return normalize_relationship_type("morePaddleBoards")
    if "point" in text and any(token in text for token in ("like", "better", "alternative")):
        return normalize_relationship_type("betterPointBreakBoards")
    if any(token in text for token in ("more performance", "sharper", "more responsive")):
        return normalize_relationship_type("morePerformanceBoards")
    if any(token in text for token in ("more forgiving", "easier than", "easier", "less demanding")):
        return normalize_relationship_type("moreForgivingBoards")
    if "small wave" in text:
        return normalize_relationship_type("betterSmallWaveBoards")
    if "good wave" in text:
        return normalize_relationship_type("betterGoodWaveBoards")
    if "beach break" in text:
        return normalize_relationship_type("betterBeachBreakBoards")
    if "reef" in text:
        return normalize_relationship_type("betterReefBoards")
    if any(token in text for token in ("similar", "like", "alternative")):
        return normalize_relationship_type("similarBoards")
    return None


def source_board_from_message(message: str, profile: RiderProfile) -> dict | None:
    text = _key(message)
    aliases = {
        "hypto": ("Haydenshapes", "Hypto Krypto"), "rnf": ("Lost", "RNF 96"),
        "seaside": ("Firewire", "Seaside"), "monsta": ("JS Industries", "Monsta"),
        "phantom": ("Pyzel", "Phantom"),
    }
    for alias, identity in aliases.items():
        if alias in text.split():
            return find_relationship_board(*identity)
    matches = []
    for row in load_relationship_graph()["boards"]:
        model = _key(row["model"])
        brand = _key(row["brand"])
        if model and f" {model} " in f" {text} " and (f" {brand} " in f" {text} " or len(model.split()) > 1):
            matches.append((len(model), row))
    explicit = max(matches, default=(0, None))[1]
    if explicit:
        return explicit
    if profile.current_board:
        current = _key(profile.current_board)
        return next((row for row in load_relationship_graph()["boards"] if current.endswith(_key(row["model"]))), None)
    return None


def relationship_suggestions(source: dict, relation: str, limit: int = 8, profile: RiderProfile | None = None) -> list[SuggestedBoard]:
    relation = normalize_relationship_type(relation) or relation
    output = []
    size_hint = None
    if profile and profile.current_volume_litres:
        base = profile.current_volume_litres
        ability = (profile.ability or "").lower()
        if relation in {"moreForgivingBoards", "morePaddleBoards", "stepDownFromBoards"}:
            low, high = base + 1, base + 3
        elif ability in {"intermediate", "beginner"}:
            low, high = base, base + 2.5
        else:
            low, high = base - 1, base + 1.5
        size_hint = f"Aim around {low:g}-{high:g}L; keep this progression anchored to your {base:g}L board."
    for edge in source.get("relationships", {}).get(relation, [])[:limit]:
        matrix = find_matrix_board(edge["brand"], edge["model"])
        if not matrix:
            continue
        output.append(SuggestedBoard(
            brand=edge["brand"], model=edge["model"],
            category=matrix["primaryLane"].replace("_", " ").title(),
            confidence={"high": .94, "medium": .78, "low": .58}[edge["confidence"]],
            why_it_fits=edge["reason"], description=matrix.get("manufacturerDescription"),
            volume_range=(f"{matrix['volumeRange']['min']:g}-{matrix['volumeRange']['max']:g}L" if matrix.get("volumeRange", {}).get("min") is not None else None),
            source="quivrr_board_relationship_graph_v2", board_model_id=matrix.get("boardModelId"),
            suggested_size=size_hint,
        ))
    return output


def relationship_reply(source: dict, relation: str, canonical: list[SuggestedBoard], live: list[SuggestedBoard], region: str | None) -> str:
    labels = {
        "similarBoards": "closest canonical relatives", "morePerformanceBoards": "sharper, more performance-focused steps",
        "moreForgivingBoards": "more forgiving options", "betterPointBreakBoards": "better point-break fits",
        "morePaddleBoards": "easier-paddling options", "stepUpFromBoards": "controlled step-ups",
        "stepDownFromBoards": "less demanding step-downs", "fishAlternativeBoards": "fish alternatives",
        "shortboardAlternativeBoards": "shortboard alternatives",
        "betterSmallWaveBoards": "better small-wave fits", "betterGoodWaveBoards": "better good-wave fits",
        "betterBeachBreakBoards": "better beach-break fits", "betterReefBoards": "better reef fits",
    }
    names = ", ".join(f"{row.brand} {row.model}" for row in canonical[:5])
    reply = relationship_expert_intro(source["brand"], source["model"], relation, canonical)
    if not reply:
        reply = f"From the relationship graph, the {labels.get(relation, relation)} from {source['brand']} {source['model']} are {names}."
    if not region:
        return reply + " That is canonical board advice; tell me Australia, Europe or Indonesia if you want live stock checked."
    live_keys = {(row.brand.lower(), row.model.lower()) for row in live}
    if live:
        reply += f" Verified {region} stock is available for " + ", ".join(f"{row.brand} {row.model}" for row in live[:5]) + "."
    unavailable = [row for row in canonical if (row.brand.lower(), row.model.lower()) not in live_keys]
    if unavailable:
        reply += " Strong canonical fits not found in live stock are " + ", ".join(f"{row.brand} {row.model}" for row in unavailable[:4]) + "."
    return reply
