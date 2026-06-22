import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "app" / "knowledge"
GENERATED = KNOWLEDGE / "generated"

RELATIONSHIP_FILES = [
    KNOWLEDGE / "board_relationships.json",
    KNOWLEDGE / "curated" / "board_relationship_overrides.json",
]

CANONICAL_FILES = [
    GENERATED / "canonical_board_profiles.json",
    GENERATED / "board_intelligence_generated.json",
]


def compact(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def canonical_index():
    by_brand = {}

    for path in CANONICAL_FILES:
        if not path.exists():
            continue

        data = load_json(path)
        boards = data.get("boards", data) if isinstance(data, dict) else data

        if not isinstance(boards, list):
            continue

        for board in boards:
            if not isinstance(board, dict):
                continue

            brand = board.get("brand") or board.get("brand_name") or board.get("BrandName")
            model = board.get("model") or board.get("model_name") or board.get("ModelName")

            if brand and model:
                by_brand.setdefault(str(brand), set()).add(compact(model))

    return by_brand


def test_relationship_files_reference_canonical_board_names():
    by_brand = canonical_index()
    assert by_brand, "Canonical board profile index is empty."

    unresolved = []

    for path in RELATIONSHIP_FILES:
        if not path.exists():
            continue

        data = load_json(path)

        for item in iter_dicts(data):
            for brand_key, model_key in [
                ("brand", "model"),
                ("board_brand", "board_model"),
                ("source_brand", "source_model"),
                ("target_brand", "target_model"),
                ("from_brand", "from_model"),
                ("to_brand", "to_model"),
                ("recommended_brand", "recommended_model"),
            ]:
                if brand_key not in item and model_key not in item:
                    continue

                brand = item.get(brand_key)
                model = item.get(model_key)

                if not brand or not model:
                    continue

                if str(brand) not in by_brand or compact(model) not in by_brand[str(brand)]:
                    unresolved.append({
                        "file": str(path.relative_to(ROOT)),
                        "brand": brand,
                        "model": model,
                        "brand_key": brand_key,
                        "model_key": model_key,
                    })

    assert not unresolved, f"Unresolved relationship aliases: {unresolved}"


def test_legacy_curated_aliases_are_not_reintroduced():
    legacy_aliases = {
        ("JS Industries", "Red Baron"),
        ("DHD", "Golden Child"),
        ("Christenson", "Fish"),
    }

    found = []

    for path in RELATIONSHIP_FILES:
        if not path.exists():
            continue

        data = load_json(path)

        for item in iter_dicts(data):
            brand = item.get("brand")
            model = item.get("model")

            if (brand, model) in legacy_aliases:
                found.append({
                    "file": str(path.relative_to(ROOT)),
                    "brand": brand,
                    "model": model,
                })

    assert not found, f"Legacy curated aliases were reintroduced: {found}"
