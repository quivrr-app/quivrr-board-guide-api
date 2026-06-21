from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.models import RiderProfile, SuggestedBoard
from app.rider_fit import recommend_rider_fit


MATRIX_PATH = Path(__file__).parent / "knowledge/generated/board_expert_matrix.json"


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


@lru_cache(maxsize=1)
def load_matrix() -> list[dict]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8-sig")).get("boards", [])


def find_matrix_board(brand: str, model: str) -> dict | None:
    brand_key, model_key = _key(brand), _key(model)
    return next((row for row in load_matrix() if _key(row.get("brand")) == brand_key and _key(row.get("model")) == model_key), None)


def target_lanes(profile: RiderProfile) -> list[str]:
    text = " ".join(filter(None, [profile.preferred_board_type, profile.goal, profile.wave_power])).lower()
    lanes = []
    if "fish" in text:
        if "point" in (profile.wave_type or "").lower():
            lanes.extend(["point_break_fish", "traditional_fish", "performance_fish", "twin_fin_performance"])
        elif "weak" in text or "beach" in (profile.wave_type or "").lower():
            lanes.extend(["small_wave_fish", "cruisy_fish", "fish_hybrid"])
        else:
            lanes.extend(["modern_fish", "performance_fish", "traditional_fish", "cruisy_fish"])
    if "grov" in text:
        lanes.extend(["groveller", "small_wave_daily_driver", "weak_wave_board"])
    if "daily driver" in text:
        if "forgiving" not in text and "easy" not in text and "paddle" not in text:
            lanes.extend(["performance_daily_driver", "high_performance_shortboard"])
        else:
            lanes.extend(["forgiving_daily_driver", "hybrid_daily_driver", "one_board_quiver"])
    if "performance" in text and "daily driver" not in text:
        lanes.append("high_performance_shortboard")
    if "step" in text:
        lanes.extend(["step_up", "powerful_wave_board"])
    if "mid" in text:
        lanes.append("mid_length")
    if "longboard" in text:
        lanes.append("longboard")
    if "shortboard" in text and "performance" not in text and "daily driver" not in text:
        lanes.extend(["forgiving_daily_driver", "performance_daily_driver", "high_performance_shortboard"])
    return list(dict.fromkeys(lanes)) or ["one_board_quiver", "forgiving_daily_driver", "performance_daily_driver"]


def _volume_distance(board: dict, target: float | None) -> float:
    if target is None:
        return 0
    low, high = board.get("volumeRange", {}).get("min"), board.get("volumeRange", {}).get("max")
    if low is None or high is None:
        return 5
    return 0 if low <= target <= high else min(abs(target - low), abs(target - high))


def recommend_from_matrix(profile: RiderProfile, limit: int = 12) -> list[SuggestedBoard]:
    lanes = target_lanes(profile)
    fit = recommend_rider_fit(profile)
    target = profile.target_volume_litres or ((fit.volume_low + fit.volume_high) / 2 if fit else None)
    brief_text = " ".join(filter(None, [profile.preferred_board_type, profile.goal, profile.desired_feel])).lower()
    daily_driver_brief = "daily driver" in brief_text or "daily shortboard" in brief_text
    asks_forgiving = any(token in brief_text for token in ("forgiving", "easy", "paddle help"))
    performance_daily_brief = daily_driver_brief and not asks_forgiving
    advanced_performance_brief = performance_daily_brief and (
        (profile.ability or "").lower() in {"advanced", "expert"} or "performance" in brief_text
    )
    rows = []
    for board in load_matrix():
        if profile.requested_brand and _key(board.get("brand")) != _key(profile.requested_brand):
            continue
        board_lanes = {board["primaryLane"], *board.get("secondaryLanes", []), *board.get("boardLanes", [])}
        lane_rank = next((len(lanes) - index for index, lane in enumerate(lanes) if lane in board_lanes), 0)
        if lane_rank == 0:
            continue
        distance = _volume_distance(board, target)
        fish_weight = board.get("fishScore", 0) * .1 if any("fish" in lane or "twin" in lane for lane in lanes) else 0
        score = lane_rank * 20 + board.get("oneBoardQuiverScore", 0) * .08 + board.get("performanceScore", 0) * .06 + fish_weight - distance * 4
        if performance_daily_brief:
            model_key = _key(board.get("model"))
            priority = {
                "phantom": 120, "xero gravity": 115, "happy everyday": 110,
                "inferno 72": 105, "rad ripper": 100, "driver 2 0": 95,
                "monsta": 25,
            }
            score += priority.get(model_key, 0)
            if board["primaryLane"] == "hybrid_daily_driver":
                score -= 90 if advanced_performance_brief else 45
            elif board["primaryLane"] == "performance_daily_driver":
                score += 35
        rows.append((score, board, lanes[0], distance))
    rows.sort(key=lambda item: (-item[0], item[1]["brand"], item[1]["model"]))
    selected, brands = [], {}
    for score_value, board, target_lane, distance in rows:
        brand_key = _key(board["brand"])
        if brands.get(brand_key, 0) >= 2:
            continue
        brands[brand_key] = brands.get(brand_key, 0) + 1
        why = f"{board['primaryLane'].replace('_', ' ')} fit from the global expert matrix"
        if target is not None:
            why += f"; canonical sizes cover or sit {distance:g}L from the {target:g}L target"
        confidence = {"high": .94, "medium": .78, "low": .58}.get(board.get("confidence"), .55)
        if performance_daily_brief:
            priority_confidence = {
                "phantom": .995, "xero gravity": .99, "happy everyday": .985,
                "inferno 72": .98, "rad ripper": .975, "driver 2 0": .97,
            }
            confidence = priority_confidence.get(_key(board.get("model")), min(confidence, .94))
        selected.append(SuggestedBoard(
            brand=board["brand"], model=board["model"], category=board["primaryLane"].replace("_", " ").title(),
            confidence=confidence,
            why_it_fits=why, description=board.get("manufacturerDescription"),
            volume_range=(f"{board['volumeRange']['min']:g}-{board['volumeRange']['max']:g}L" if board.get("volumeRange", {}).get("min") is not None else None),
            wave_range=(f"{board['waveRangeMinFt']:g}-{board['waveRangeMaxFt']:g}ft" if board.get("waveRangeMinFt") is not None and board.get("waveRangeMaxFt") is not None else None),
            skill_fit=" to ".join(filter(None, [board.get("abilityMin"), board.get("abilityMax")])) or None,
            source="quivrr_board_expert_matrix", board_model_id=board.get("boardModelId"),
        ))
        if len(selected) >= limit:
            break
    return selected
