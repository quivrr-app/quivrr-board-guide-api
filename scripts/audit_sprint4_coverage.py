import json
from collections import Counter
from pathlib import Path

path = Path("app/knowledge/generated/board_intelligence_generated.json")

data = json.loads(path.read_text(encoding="utf-8-sig"))

boards = data["boards"] if isinstance(data, dict) and "boards" in data else data

confidence = Counter()

empty_summary = 0
manufacturer_summary = 0

for board in boards:

    score = float(board.get("classificationConfidence", 0))
    confidence[score] += 1

    summary = (board.get("summary") or "").strip()

    if not summary:
        empty_summary += 1

    if summary.endswith(".") and len(summary.split()) <= 4:
        manufacturer_summary += 1

print()
print("Total boards:", len(boards))
print()

print("Confidence distribution")
for k in sorted(confidence):
    print(f"{k}: {confidence[k]}")

print()
print("Very weak summaries:", manufacturer_summary)
print("Empty summaries:", empty_summary)
