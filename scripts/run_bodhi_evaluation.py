from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.board_intelligence import board_intelligence_baseline
from app.board_relationship_graph import relationship_type
from app.board_relationships import relationship_validation_counts
from app.comparison_engine import compare_board_models
from app.intent_router import route_intent
from app.model_recommendation_engine import recommend_models
from app.models import RiderProfile

SCENARIOS_PATH = ROOT / "tests" / "bodhi_evaluation" / "scenarios" / "slice2_scenarios.json"
OUTPUT_PATH = ROOT / "tests" / "bodhi_evaluation" / "slice2_report.json"


def main() -> int:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    results = []
    passed = 0

    for scenario in scenarios:
        scenario_type = scenario["type"]
        success = False
        details: dict[str, object] = {}

        if scenario_type == "intent":
            actual = route_intent(scenario["message"])
            success = actual == scenario["expected_intent"]
            details = {"actual_intent": actual}
        elif scenario_type == "recommendation":
            profile = RiderProfile(**scenario["profile"])
            rows = recommend_models(profile, limit=8)
            top_models = [row.model for row in rows[:3]]
            success = len(rows) >= scenario["expected_min_results"] and rows and rows[0].model in scenario["expected_top_models"]
            details = {"top_models": top_models, "count": len(rows)}
        elif scenario_type == "comparison":
            profile = RiderProfile(**scenario["profile"])
            result = compare_board_models(
                scenario["left"]["brand"],
                scenario["left"]["model"],
                scenario["right"]["brand"],
                scenario["right"]["model"],
                profile,
            )
            winner = result.ordered_boards[0].model if result else None
            success = winner == scenario["expected_winner"]
            details = {"winner": winner, "conclusion": result.comparison.rider_specific_conclusion if result else None}
        elif scenario_type == "relationship":
            actual = relationship_type(scenario["message"])
            success = actual == scenario["expected_relation"]
            details = {"actual_relation": actual}
        elif scenario_type == "determinism":
            profile = RiderProfile(**scenario["profile"])
            first = [(row.brand, row.model, row.suggested_size) for row in recommend_models(profile, limit=scenario["limit"])]
            second = [(row.brand, row.model, row.suggested_size) for row in recommend_models(profile, limit=scenario["limit"])]
            success = first == second
            details = {"sequence": first}

        passed += int(success)
        results.append({"id": scenario["id"], "type": scenario_type, "passed": success, "details": details})

    report = {
        "baseline": board_intelligence_baseline(),
        "relationship_validation_counts": relationship_validation_counts(),
        "summary": {
            "total_scenarios": len(scenarios),
            "passed_scenarios": passed,
            "failed_scenarios": len(scenarios) - passed,
            "pass_rate": round((passed / len(scenarios)) * 100, 1),
        },
        "determinism": {
            "checks": sum(1 for row in scenarios if row["type"] == "determinism"),
            "all_passed": all(row["passed"] for row in results if row["type"] == "determinism"),
        },
        "results": results,
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(OUTPUT_PATH)
    print(json.dumps(report["summary"], indent=2))
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())
