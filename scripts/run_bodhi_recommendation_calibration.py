from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.board_expert_matrix import recommend_from_matrix
from app.models import RiderProfile

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "bodhi_expert_expectations.json"
OUTPUT_DIR = ROOT / "scripts" / "output"
JSON_PATH = OUTPUT_DIR / "bodhi_recommendation_calibration.json"
CSV_PATH = OUTPUT_DIR / "bodhi_recommendation_calibration.csv"


def _check_scenario(scenario: dict) -> dict:
    rows = recommend_from_matrix(RiderProfile.model_validate(scenario["profile"]), limit=8)
    categories = [row.category for row in rows[:6]]
    names = [row.model for row in rows[:6]]
    excluded = []
    if scenario.get("allowed_families"):
        unexpected = sorted(set(categories) - set(scenario["allowed_families"]))
        if unexpected:
            excluded.append(f"unexpected families: {', '.join(unexpected)}")
    for model in scenario.get("excluded_models", []):
        if model in {row.model for row in rows}:
            excluded.append(f"excluded model surfaced: {model}")
    for family in scenario.get("excluded_families", []):
        if family in set(categories):
            excluded.append(f"excluded family surfaced: {family}")
    for model in scenario.get("required_models", []):
        if model not in {row.model for row in rows}:
            excluded.append(f"required model missing: {model}")

    return {
        "scenario": scenario["id"],
        "request": scenario["request"],
        "profile_summary": {
            "age": scenario["profile"].get("age"),
            "weight_kg": scenario["profile"].get("weight_kg"),
            "ability": scenario["profile"].get("ability"),
            "wave_type": scenario["profile"].get("wave_type"),
            "wave_power": scenario["profile"].get("wave_power"),
            "preferred_board_type": scenario["profile"].get("preferred_board_type"),
        },
        "recommended_models": [f"{row.brand} {row.model}" for row in rows[:6]],
        "recommended_families": categories,
        "variant_selections": [row.model for row in rows[:6] if row.model.endswith("XL") or "Pro" in row.model],
        "excluded_models": scenario.get("excluded_models", []),
        "exclusion_reasons": excluded,
        "pass": not excluded,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    report = [_check_scenario(scenario) for scenario in scenarios]
    JSON_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "request",
                "recommended_models",
                "recommended_families",
                "variant_selections",
                "excluded_models",
                "exclusion_reasons",
                "pass",
            ],
        )
        writer.writeheader()
        for row in report:
            writer.writerow({
                "scenario": row["scenario"],
                "request": row["request"],
                "recommended_models": "; ".join(row["recommended_models"]),
                "recommended_families": "; ".join(row["recommended_families"]),
                "variant_selections": "; ".join(row["variant_selections"]),
                "excluded_models": "; ".join(row["excluded_models"]),
                "exclusion_reasons": "; ".join(row["exclusion_reasons"]),
                "pass": row["pass"],
            })
    passed = sum(1 for row in report if row["pass"])
    print(json.dumps({"total": len(report), "passed": passed, "failed": len(report) - passed}, indent=2))


if __name__ == "__main__":
    main()
