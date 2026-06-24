import json
from pathlib import Path

ROOT = Path.cwd()

paths = {
    "canonical": ROOT / "app" / "knowledge" / "generated" / "canonical_board_profiles.json",
    "generated": ROOT / "app" / "knowledge" / "generated" / "board_intelligence_generated.json",
    "overrides": ROOT / "app" / "knowledge" / "board_intelligence_overrides.json",
    "relationships": ROOT / "app" / "knowledge" / "board_relationships.json",
    "relationship_overrides": ROOT / "app" / "knowledge" / "curated" / "board_relationship_overrides.json",
}

def load(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))

def sample_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["boards", "relationships", "items", "profiles"]:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []

for name, path in paths.items():
    print("")
    print("=" * 80)
    print(name)
    print(path)
    print("exists:", path.exists())

    data = load(path)
    items = sample_list(data)

    print("top type:", type(data).__name__ if data is not None else None)
    print("item count:", len(items))

    if items:
        first = items[0]
        print("first item keys:", list(first.keys()) if isinstance(first, dict) else type(first).__name__)
        print("first item sample:")
        print(json.dumps(first, indent=2, ensure_ascii=False)[:2500])
