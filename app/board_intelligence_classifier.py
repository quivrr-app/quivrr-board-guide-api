from __future__ import annotations

import re


CATEGORY_RULES = {
    "dailyDriver": ["daily driver", "everyday board", "everyday shortboard", "all-rounder", "all rounder", "one-board quiver", "one board quiver"],
    "performanceShortboard": ["performance shortboard", "high-performance shortboard", "high performance shortboard", "pro model", "critical surfing"],
    "groveller": ["groveller", "groveler", "small-wave board", "small wave board", "summer board"],
    "fish": ["fish surfboard", "fish shape", "retro fish", "keel fish"],
    "stepUp": ["step-up", "step up", "stepup", "semi-gun", "semi gun"],
    "midLength": ["mid-length", "mid length", "midlength"],
    "longboard": ["performance longboard", "traditional longboard", "longboard model", "longboard shape", "nose rider", "noserider"],
    "twinFin": ["twin fin", "twin-fin", "twinfin", "keel fin"],
    "hybrid": ["hybrid shortboard", "hybrid surfboard", "performance hybrid", "shortboard/fish hybrid"],
}

WAVE_TYPE_RULES = {
    "beachBreak": ["beach break", "beachbreak"],
    "pointBreak": ["point break", "pointbreak"],
    "reefBreak": ["reef break", "reefbreak"],
}

WAVE_POWER_RULES = {
    "weak": ["weak waves", "weak surf", "soft waves", "soft surf", "gutless", "mushy"],
    "average": ["average waves", "everyday waves", "all conditions", "wide range of conditions"],
    "powerful": ["powerful waves", "powerful surf", "hollow waves", "heavy waves", "solid surf", "serious waves"],
}

SURFER_LEVEL_RULES = {
    "beginner": ["beginner", "novice", "learning to surf"],
    "intermediate": ["intermediate"],
    "advanced": ["advanced", "experienced surfer"],
    "expert": ["expert", "elite surfer", "professional surfer", "pro-level", "pro level"],
}

TAG_RULES = {
    "small_wave": ["small wave", "weak waves", "weak surf", "soft waves", "summer board", "groveller", "groveler"],
    "daily_driver": ["daily driver", "everyday board", "everyday shortboard", "all-rounder", "all rounder"],
    "travel_board": ["travel board", "surf trip", "travel quiver"],
    "one_board_quiver": ["one-board quiver", "one board quiver", "one board for", "true all-rounder"],
    "high_performance": ["high performance", "high-performance", "performance shortboard", "critical surfing"],
    "tube_riding": ["tube riding", "tube-riding", "barrel riding", "barrel", "in the tube"],
    "easy_paddling": ["easy paddling", "paddles easily", "paddles well", "easy wave entry", "wave entry"],
    "high_wave_count": ["wave count", "catch more waves", "catches waves with ease", "easy to catch waves"],
}

PRIMARY_CATEGORY_ORDER = [
    ("longboard", "longboard"),
    ("midLength", "mid_length"),
    ("stepUp", "step_up"),
    ("groveller", "groveller"),
    ("fish", "fish"),
    ("hybrid", "hybrid"),
    ("performanceShortboard", "performance_shortboard"),
    ("dailyDriver", "daily_driver"),
]

MODEL_OVERRIDES = {
    ("pyzel", "ghost"): {
        "boardCategory": "step_up",
        "performanceShortboard": True, "stepUp": True, "advanced": True,
        "powerful": True, "waveRangeMinFt": 4.0, "waveRangeMaxFt": 12.0,
        "tags": ["high_performance", "tube_riding", "travel_board"],
    },
    ("haydenshapes", "hypto krypto"): {
        "boardCategory": "hybrid",
        "dailyDriver": True, "hybrid": True, "intermediate": True, "advanced": True,
        "average": True, "powerful": True, "waveRangeMinFt": 2.0, "waveRangeMaxFt": 8.0,
        "tags": ["daily_driver", "one_board_quiver", "easy_paddling", "high_wave_count"],
    },
    ("js industries", "monsta"): {
        "boardCategory": "performance_shortboard",
        "performanceShortboard": True, "dailyDriver": True, "advanced": True,
        "average": True, "powerful": True, "waveRangeMinFt": 2.0, "waveRangeMaxFt": 8.0,
        "tags": ["daily_driver", "high_performance", "tube_riding"],
    },
}


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _contains(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)


def _wave_range(text: str) -> tuple[float | None, float | None]:
    patterns = [
        r"\b(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:ft|foot|feet)\b",
        r"\b(?:waves?|surf)\s*(?:from\s*)?(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:ft|foot|feet)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            low, high = float(match.group(1)), float(match.group(2))
            if 0.5 <= low <= high <= 30:
                return low, high
    return None, None


def classify_board(board: dict) -> dict:
    description = str(board.get("model_description") or board.get("description") or "").lower()
    summary = str(board.get("short_description") or board.get("summary") or "").lower()
    text = re.sub(r"\s+", " ", " ".join([description, summary])).strip()

    output = {name: _contains(text, tokens) for name, tokens in CATEGORY_RULES.items()}
    output.update({name: _contains(text, tokens) for name, tokens in WAVE_TYPE_RULES.items()})
    output.update({name: _contains(text, tokens) for name, tokens in WAVE_POWER_RULES.items()})
    output.update({name: _contains(text, tokens) for name, tokens in SURFER_LEVEL_RULES.items()})

    tags = [name for name, tokens in TAG_RULES.items() if _contains(text, tokens)]
    low, high = _wave_range(text)
    override = MODEL_OVERRIDES.get((_key(board.get("brand")), _key(board.get("model"))))
    override_evidence = False
    if override:
        override_evidence = True
        for name, value in override.items():
            if name == "tags":
                tags.extend(value)
            elif name == "boardCategory":
                continue
            elif name == "waveRangeMinFt":
                low = value
            elif name == "waveRangeMaxFt":
                high = value
            else:
                output[name] = value

    board_category = "unclassified"
    for field, label in PRIMARY_CATEGORY_ORDER:
        if output[field]:
            board_category = label
            break
    if override and override.get("boardCategory"):
        board_category = override["boardCategory"]

    wave_types = [label for field, label in [("beachBreak", "beach_break"), ("pointBreak", "point_break"), ("reefBreak", "reef_break")] if output[field]]
    wave_power = [label for label in ["weak", "average", "powerful"] if output[label]]
    surfer_level = [label for label in ["beginner", "intermediate", "advanced", "expert"] if output[label]]

    evidence_groups = sum([
        board_category != "unclassified",
        bool(wave_types), bool(wave_power), bool(surfer_level),
        low is not None and high is not None, bool(tags),
    ])
    if not text:
        confidence = 0.0
    else:
        confidence = 0.25 + (0.1 * evidence_groups) + (0.1 if len(text) >= 240 else 0)
        if override_evidence:
            confidence += 0.15
        confidence = min(round(confidence, 2), 0.95)

    return {
        "boardCategory": board_category,
        **output,
        "waveType": wave_types,
        "wavePower": wave_power,
        "surferLevel": surfer_level,
        "waveRangeMinFt": low,
        "waveRangeMaxFt": high,
        "tags": sorted(set(tags)),
        "classificationConfidence": confidence,
    }
