import json
from pathlib import Path

path = Path("app/knowledge/generated/board_intelligence_generated.json")

data = json.loads(path.read_text(encoding="utf-8-sig"))

boards = data["boards"] if isinstance(data, dict) and "boards" in data else data

targets = {
    ("Haydenshapes", "Hypto Krypto"),
    ("Pyzel", "Phantom"),
    ("JS Industries", "Xero Gravity"),
    ("Channel Islands", "happy-everyday"),
    ("Sharp Eye", "Inferno 72"),
    ("Lost", "RNF 96"),
    ("Firewire", "Seaside"),
    ("Album", "Twinsman"),
    ("Christenson", "Ocean Racer"),
}

for board in boards:
    key = (board.get("brand"), board.get("model"))

    if key in targets:
        print("\n" + "=" * 100)
        print(f"{board.get('brand')} | {board.get('model')}")
        print("=" * 100)

        interesting = {
            k: v
            for k, v in board.items()
            if k not in {
                "official_image_url",
                "official_product_url",
                "source_url"
            }
        }

        print(json.dumps(interesting, indent=2, ensure_ascii=False)[:8000])
