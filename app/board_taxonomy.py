from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.board_master import load_board_master, master_taxonomy_record


TAXONOMY_PATH = Path(__file__).parent / "knowledge/board_taxonomy_v2.json"


def normalise(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower().replace("&", " and ")).strip()


@lru_cache(maxsize=1)
def load_taxonomy() -> list[dict]:
    legacy = {
        int(row["canonical_model_id"]): row
        for row in json.loads(TAXONOMY_PATH.read_text(encoding="utf-8-sig"))["models"]
    }
    return [master_taxonomy_record(row, legacy.get(int(row["canonical_model_id"]))) for row in load_board_master()["models"]]


@lru_cache(maxsize=1)
def taxonomy_by_id() -> dict[int, dict]:
    return {int(row["canonical_model_id"]): row for row in load_taxonomy()}


@lru_cache(maxsize=1)
def taxonomy_search_index() -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in load_taxonomy():
        for name in [row["model"], *row.get("aliases", [])]:
            index[(normalise(row["brand"]), normalise(name))] = row
    return index


def find_taxonomy(brand: str, model: str) -> dict | None:
    return taxonomy_search_index().get((normalise(brand), normalise(model)))


def requested_category(*values: str | None) -> str | None:
    text = " ".join(normalise(value) for value in values if value)
    checks = (
        ("performance mid length", "performance_mid_length"), ("performance twin", "performance_twin"),
        ("performance fish", "performance_fish"), ("traditional fish", "traditional_fish"),
        ("performance daily driver", "performance_daily_driver"),
        ("performance shortboard", "performance_shortboard"), ("small wave shortboard", "small_wave_shortboard"),
        ("twin pin", "twin_pin"), ("step up", "step_up"), ("mid length", "mid_length"),
        ("groveller", "groveller"), ("grovler", "groveller"), ("hybrid", "hybrid_shortboard"),
        ("daily driver", "daily_driver"), ("longboard", "longboard"), ("softboard", "softboard"),
        ("gun", "gun"), ("fish", "fish"),
    )
    return next((category for phrase, category in checks if phrase in text), None)


def allows_category(row: dict, category: str | None) -> bool:
    if not category:
        return True
    included = {row["primary_category"], *row.get("secondary_categories", []), *row.get("recommendation_lanes", [])}
    excluded = set(row.get("excluded_lanes", []))
    if category == "fish":
        return row["primary_category"] in {"traditional_fish", "performance_fish", "twin_pin"}
    return category in included and category not in excluded
