import json
import re
import html
from pathlib import Path


SOURCE_PATH = Path("app/knowledge/generated/canonical_board_profiles.json")
OUTPUT_PATH = Path("app/knowledge/generated/board_intelligence_generated.json")
OVERRIDES_PATH = Path("app/knowledge/board_intelligence_overrides.json")


CATEGORY_RULES = [
    ("step up", ["step up", "gun", "big wave", "barrel", "heavy", "hollow", "reef", "indo"]),
    ("groveller", ["groveller", "small wave", "weak", "soft", "summer", "puddle", "easy speed"]),
    ("fish", ["fish", "twin", "retro", "keel", "swallow"]),
    ("hybrid shortboard", ["hybrid", "everyday", "daily driver", "all round", "versatile"]),
    ("performance shortboard", ["performance", "pro", "high performance", "responsive", "critical"]),
    ("mid length", ["mid length", "midlength", "egg", "funboard"]),
    ("longboard", ["longboard", "log", "nose ride", "noseride"]),
]


FEEL_RULES = {
    "paddle power": ["paddle", "foam", "volume", "easy to catch", "wave count", "forgiving"],
    "easy speed": ["speed", "fast", "flow", "drive", "down the line"],
    "responsive": ["responsive", "performance", "turn", "rail to rail", "maneuver", "manoeuvre"],
    "hold": ["hold", "barrel", "hollow", "reef", "powerful", "step up"],
    "small wave": ["small wave", "weak", "soft", "summer", "groveller"],
    "everyday": ["everyday", "daily driver", "all round", "versatile"],
}


WAVE_RULES = {
    "Beach Break": ["beach", "pocket", "everyday", "small wave", "groveller", "soft"],
    "Point Break": ["point", "down the line", "open face", "drive"],
    "Reef Break": ["reef", "barrel", "hollow", "powerful", "hold"],
}


ABILITY_RULES = {
    "Beginner": ["easy", "forgiving", "stable", "foam", "paddle"],
    "Intermediate": ["everyday", "hybrid", "groveller", "fish", "versatile", "all round", "daily driver"],
    "Advanced": ["performance", "responsive", "critical", "barrel", "step up", "pro"],
}


def normalise(value):
    return str(value or "").strip().lower()


def clean_description(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip() or None


def text_blob(board):
    values = [
        board.get("brand"),
        board.get("model"),
        board.get("model_family"),
        board.get("category"),
        board.get("description"),
        board.get("construction"),
        board.get("fin_system"),
        board.get("tail_shape"),
    ]
    return " ".join(normalise(value) for value in values if value)


def infer_category(text, fallback):
    for category, tokens in CATEGORY_RULES:
        if any(token in text for token in tokens):
            return category

    fallback_text = normalise(fallback)

    if fallback_text in ["surfboard", "surfboards"]:
        return "surfboard"

    if fallback_text:
        return fallback_text

    return "surfboard"


def infer_tags(rule_map, text):
    tags = []
    for tag, tokens in rule_map.items():
        if any(token in text for token in tokens):
            tags.append(tag)
    return tags


def volume_range(board):
    values = []
    for size in board.get("sizes", []):
        try:
            if size.get("volume_litres") is not None:
                values.append(float(size["volume_litres"]))
        except (TypeError, ValueError):
            pass

    if not values:
        return None

    return {
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "count": len(values),
    }


def build_summary(board, inferred_category, feel_tags, wave_tags):
    description = clean_description(board.get("description"))
    if description:
        clean = re.sub(r"\s+", " ", description).strip()
        return clean[:420]

    parts = [f"{board.get('brand')} {board.get('model')}"]
    if inferred_category and inferred_category != "surfboard":
        parts.append(f"is treated as a {inferred_category}")
    if feel_tags:
        parts.append("with " + ", ".join(feel_tags[:3]))
    if wave_tags:
        parts.append("for " + ", ".join(wave_tags[:2]).lower())
    return " ".join(parts) + "."


def first_sentences(value, limit=240):
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if not clean:
        return None
    match = re.match(r"^(.{40,}?)(?:\.(?:\s|$)|$)", clean)
    return (match.group(1) if match else clean)[:limit].rstrip() + "."


def notes_with_tokens(description, tokens):
    sentences = re.split(r"(?<=[.!?])\s+", str(description or ""))
    selected = [sentence.strip() for sentence in sentences if any(token in sentence.lower() for token in tokens)]
    return " ".join(selected[:2])[:500] or None


def key_for(brand, model):
    return (
        str(brand or "").strip().lower(),
        str(model or "").strip().lower(),
    )


def load_overrides():
    if not OVERRIDES_PATH.exists():
        return {}

    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8-sig"))
    rows = data.get("boards", [])
    if not isinstance(rows, list):
        return {}

    output = {}
    for row in rows:
        output[key_for(row.get("brand"), row.get("model"))] = row
    return output


def apply_override(item, override):
    for key in [
        "category",
        "ability_tags",
        "wave_tags",
        "feel_tags",
        "manual_note",
    ]:
        if key in override:
            item[key] = override[key]

    if item.get("manual_note"):
        item["summary"] = f"{item['summary']} Manual note: {item['manual_note']}"

    item["override_applied"] = True
    return item


def main():
    if not SOURCE_PATH.exists():
        raise SystemExit(f"Missing source file: {SOURCE_PATH}")

    boards = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if not isinstance(boards, list):
        raise SystemExit("Source file is not a list")

    output = []
    overrides = load_overrides()
    overrides_applied = 0

    for board in boards:
        brand = board.get("brand")
        model = board.get("model")

        if not brand or not model:
            continue

        text = text_blob(board)
        inferred_category = infer_category(text, board.get("category"))
        feel_tags = infer_tags(FEEL_RULES, text)
        wave_tags = infer_tags(WAVE_RULES, text)
        ability_tags = infer_tags(ABILITY_RULES, text)

        if not ability_tags:
            ability_tags = ["Intermediate"]

        description = clean_description(board.get("description"))
        item = {
            "brand": brand,
            "model": model,
            "board_model_id": board.get("board_model_id"),
            "model_description": description,
            "short_description": first_sentences(description),
            "construction": board.get("construction"),
            "category": inferred_category,
            "wave_range": board.get("recommended_wave_range"),
            "wave_type": infer_tags(WAVE_RULES, text),
            "skill_level": ability_tags,
            "surfer_profile": notes_with_tokens(description, ["surfer", "beginner", "intermediate", "advanced", "ability"]),
            "construction_notes": notes_with_tokens(description, ["construction", "carbon", "fiberglass", "eps", "pu"]),
            "fin_setup_notes": notes_with_tokens(description, ["fin", "thruster", "quad", "twin"]),
            "tail_notes": notes_with_tokens(description, ["tail", "swallow", "squash", "pin"]),
            "rocker_notes": notes_with_tokens(description, ["rocker", "rail"]),
            "volume_range": volume_range(board),
            "ability_tags": ability_tags,
            "wave_tags": wave_tags,
            "feel_tags": feel_tags,
            "official_product_url": board.get("official_product_url"),
            "official_image_url": board.get("official_image_url"),
            "summary": build_summary(board, inferred_category, feel_tags, wave_tags),
            "source": "generated_from_canonical_catalogue",
            "source_url": board.get("description_source_url") or board.get("official_product_url") or board.get("source"),
            "source_type": board.get("description_source_type") or ("manufacturer" if description else None),
            "last_updated_utc": board.get("description_last_scraped_utc"),
            "override_applied": False,
        }

        override = overrides.get(key_for(brand, model))
        if override:
            item = apply_override(item, override)
            overrides_applied += 1

        output.append(item)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"boards": output}, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Generated Bodhi intelligence metadata")
    print(f"Source boards: {len(boards)}")
    print(f"Generated boards: {len(output)}")
    print(f"Wrote: {OUTPUT_PATH}")
    print(f"Overrides applied: {overrides_applied}")

    by_category = {}
    for item in output:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1

    print("")
    print("Category summary")
    for category, count in sorted(by_category.items()):
        print(f"{category}: {count}")


if __name__ == "__main__":
    main()
