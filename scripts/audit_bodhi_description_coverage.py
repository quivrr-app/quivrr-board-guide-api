import json
from collections import defaultdict
from pathlib import Path

path = Path("app/knowledge/generated/board_intelligence_generated.json")
data = json.loads(path.read_text(encoding="utf-8-sig"))
boards = data["boards"] if isinstance(data, dict) and "boards" in data else data

brand_stats = defaultdict(lambda: {
    "total": 0,
    "rich": 0,
    "weak": 0,
    "empty_description": 0,
    "low_confidence": 0,
    "examples": []
})

for board in boards:
    brand = board.get("brand") or "UNKNOWN"
    model = board.get("model") or "UNKNOWN"

    desc = (board.get("model_description") or "").strip()
    short = (board.get("short_description") or "").strip()
    summary = (board.get("summary") or "").strip()
    confidence = float(board.get("classificationConfidence") or 0)

    weak = False

    if not desc and not short:
        weak = True
        brand_stats[brand]["empty_description"] += 1

    if confidence <= 0.25:
        weak = True
        brand_stats[brand]["low_confidence"] += 1

    if summary in {f"{brand} {model}.", f"{brand} {model}"}:
        weak = True

    brand_stats[brand]["total"] += 1

    if weak:
        brand_stats[brand]["weak"] += 1
        if len(brand_stats[brand]["examples"]) < 8:
            brand_stats[brand]["examples"].append(model)
    else:
        brand_stats[brand]["rich"] += 1

print("")
print("Brand description and intelligence coverage")
print("=" * 80)

for brand in sorted(brand_stats):
    s = brand_stats[brand]
    print(f"\n{brand}")
    print(f"  total:             {s['total']}")
    print(f"  rich:              {s['rich']}")
    print(f"  weak:              {s['weak']}")
    print(f"  empty description: {s['empty_description']}")
    print(f"  low confidence:    {s['low_confidence']}")
    print(f"  examples:          {', '.join(s['examples'])}")

total = sum(s["total"] for s in brand_stats.values())
weak = sum(s["weak"] for s in brand_stats.values())
rich = sum(s["rich"] for s in brand_stats.values())

print("")
print("=" * 80)
print(f"TOTAL BOARDS: {total}")
print(f"RICH:         {rich}")
print(f"WEAK:         {weak}")
print(f"WEAK %:       {round((weak / total) * 100, 1) if total else 0}%")
