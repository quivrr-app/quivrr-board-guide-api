from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from app.board_master import load_board_master, master_dna_record


DNA_PATH = Path(__file__).resolve().parent / "knowledge" / "board_dna_v1.json"
PHRASES_PATH = Path(__file__).resolve().parent / "knowledge" / "curated" / "dna_intent_phrases.json"
CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.94, "low": 0.82}


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower().replace("&", " and ")).strip()


@lru_cache(maxsize=1)
def load_board_dna() -> dict:
    legacy_payload = json.loads(DNA_PATH.read_text(encoding="utf-8"))
    legacy = {int(row["canonical_model_id"]): row for row in legacy_payload.get("models", [])}
    models = [master_dna_record(row, legacy.get(int(row["canonical_model_id"]))) for row in load_board_master()["models"]]
    return {"schema_version": 2, "model_count": len(models), "authority": "quivrr_board_master_matrix_v2", "models": models}


@lru_cache(maxsize=1)
def _indexes() -> tuple[dict[int, dict], dict[str, dict]]:
    by_id = {}
    by_name = {}
    for row in load_board_dna()["models"]:
        by_id[int(row["canonical_model_id"])] = row
        names = [row["model"], *row.get("aliases", [])]
        for name in names:
            by_name[f"{_key(row['brand'])}::{_key(name)}"] = row
    return by_id, by_name


def find_board_dna(brand: str, model: str) -> dict | None:
    return _indexes()[1].get(f"{_key(brand)}::{_key(model)}")


def find_board_dna_by_id(canonical_model_id: int | str) -> dict | None:
    try:
        return _indexes()[0].get(int(canonical_model_id))
    except (TypeError, ValueError):
        return None


def _numbers(board: dict) -> list[int]:
    return [
        *board["behaviour"].values(),
        *board["conditions"].values(),
        *board["rider_fit"].values(),
    ]


def dna_similarity(board_a: dict, board_b: dict) -> int:
    left, right = _numbers(board_a), _numbers(board_b)
    distance = sum(abs(a - b) for a, b in zip(left, right, strict=True))
    maximum = len(left) * 9
    return round(100 * (1 - distance / maximum))


@lru_cache(maxsize=1)
def load_intent_phrases() -> dict:
    return json.loads(PHRASES_PATH.read_text(encoding="utf-8"))["phrases"]


def resolve_dna_brief(message: str | None, profile: Any = None, prior: dict | None = None) -> dict:
    text = _key(message)
    brief = dict(prior or {})
    desired = list(brief.get("desired_feel") or [])
    behaviour = dict(brief.get("behaviour") or {})
    conditions = dict(brief.get("conditions") or {})
    fin_configurations = list(brief.get("fin_configurations") or [])
    for phrase, target in load_intent_phrases().items():
        if _key(phrase) in text:
            desired.append(phrase)
            behaviour.update(target.get("behaviour") or {})
            conditions.update(target.get("conditions") or {})
            fin_configurations.extend(target.get("fin_configurations") or [])
    category = getattr(profile, "preferred_board_type", None) if profile is not None else None
    region = getattr(profile, "region", None) if profile is not None else None
    volume = getattr(profile, "target_volume_litres", None) if profile is not None else None
    ability = getattr(profile, "ability", None) if profile is not None else None
    if re.search(r"\bfish\b", text): brief["public_family"] = "fish"
    if re.search(r"\bgrovell?er\b", text): brief["public_family"] = "groveller"
    if re.search(r"\bdaily driver\b", text): brief["public_family"] = "daily_driver"
    if re.search(r"\bperformance shortboard\b|\bhpsb\b", text): brief["public_family"] = "performance_shortboard"
    if re.search(r"\bstep[ -]?up\b", text): brief["public_family"] = "step_up"
    if re.search(r"\bmid[ -]?length\b", text): brief["public_family"] = "mid_length"
    if re.search(r"\blongboard\b", text): brief["public_family"] = "longboard"
    if not brief.get("public_family") and category:
        category_key = _key(category)
        brief["public_family"] = next((family for token, family in (
            ("performance shortboard", "performance_shortboard"), ("daily driver", "daily_driver"),
            ("step up", "step_up"), ("mid length", "mid_length"), ("longboard", "longboard"),
            ("groveller", "groveller"), ("fish", "fish"),
        ) if token in category_key), None)
    brief.update({
        "primary_category": category or brief.get("primary_category"),
        "desired_feel": list(dict.fromkeys(desired)),
        "behaviour": behaviour, "conditions": conditions,
        "fin_configurations": list(dict.fromkeys(fin_configurations)),
        "wave_type": getattr(profile, "wave_type", None) if profile is not None else brief.get("wave_type"),
        "wave_power": getattr(profile, "wave_power", None) if profile is not None else brief.get("wave_power"),
        "ability": ability or brief.get("ability"), "volume_target": volume or brief.get("volume_target"),
        "region": region or brief.get("region"),
        "stock_required": bool(brief.get("stock_required") or re.search(r"\bin stock\b|\bavailable\b", text)),
    })
    return brief


def _target_score(actual: int, target: int) -> float:
    return max(0.0, 1.0 - abs(actual - target) / 9)


def score_dna_fit(board: dict, rider_profile: Any, conversation_brief: dict) -> dict:
    allowed_families = set(conversation_brief.get("allowed_public_families") or [])
    if allowed_families and board["public_family"] not in allowed_families:
        return {"valid": False, "score": 0.0, "behaviour_score": 0.0, "condition_score": 0.0, "style_score": 0.0, "exclusions": ["Public family hard exclusion."]}
    if not allowed_families and conversation_brief.get("public_family") and board["public_family"] != conversation_brief["public_family"]:
        return {"valid": False, "score": 0.0, "behaviour_score": 0.0, "condition_score": 0.0, "style_score": 0.0, "exclusions": ["Public family hard exclusion."]}
    behaviour_targets = conversation_brief.get("behaviour") or {}
    condition_targets = conversation_brief.get("conditions") or {}
    behaviour_fit = [_target_score(board["behaviour"][metric], target) for metric, target in behaviour_targets.items() if metric in board["behaviour"]]
    condition_fit = [_target_score(board["conditions"][metric], target) for metric, target in condition_targets.items() if metric in board["conditions"]]
    behaviour_score = 25 * (sum(behaviour_fit) / len(behaviour_fit)) if behaviour_fit else 12.5
    condition_score = 25 * (sum(condition_fit) / len(condition_fit)) if condition_fit else 12.5
    desired = set(conversation_brief.get("desired_feel") or [])
    style_score = min(10.0, 2.5 * len(desired.intersection(set(board.get("style_tags") or []))))
    confidence = board["evidence"]["behaviour_confidence"]
    total = (behaviour_score + condition_score + style_score) * CONFIDENCE_WEIGHT[confidence]
    return {"valid": True, "score": round(total, 2), "behaviour_score": round(behaviour_score, 2), "condition_score": round(condition_score, 2), "style_score": round(style_score, 2), "confidence": confidence, "exclusions": []}


def explain_dna_fit(board: dict, rider_profile: Any, conversation_brief: dict) -> str:
    scored = score_dna_fit(board, rider_profile, conversation_brief)
    if not scored["valid"]:
        return scored["exclusions"][0]
    behaviour = board["behaviour"]
    conditions = board["conditions"]
    strongest = sorted(behaviour, key=behaviour.get, reverse=True)[:2]
    wave = max(conditions, key=conditions.get)
    tradeoff = min(behaviour, key=behaviour.get)
    confidence = board["evidence"]["behaviour_confidence"]
    qualifier = "The governed design evidence indicates" if confidence == "low" else "Its Board DNA shows"
    return (
        f"{qualifier} strong {strongest[0].replace('_', ' ')} and {strongest[1].replace('_', ' ')}, "
        f"with its best condition fit in {wave.replace('_', ' ')}. The trade-off is lower {tradeoff.replace('_', ' ')}."
    )
