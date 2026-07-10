import json
import unittest
from pathlib import Path

from app.comparison_engine import compare_board_models
from app.intent_router import route_intent
from app.model_recommendation_engine import recommend_models
from app.models import RiderProfile
from app.board_relationship_graph import relationship_type


SCENARIOS_PATH = Path(__file__).parent / "scenarios" / "slice2_scenarios.json"


def load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


class BodhiSlice2ScenarioTests(unittest.TestCase):
    def test_all_scenarios(self):
        scenarios = load_scenarios()
        self.assertGreaterEqual(len(scenarios), 40)

        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                scenario_type = scenario["type"]
                if scenario_type == "intent":
                    self.assertEqual(route_intent(scenario["message"]), scenario["expected_intent"])
                elif scenario_type == "recommendation":
                    rows = recommend_models(RiderProfile(**scenario["profile"]), limit=8)
                    self.assertGreaterEqual(len(rows), scenario["expected_min_results"])
                    self.assertIn(rows[0].model, scenario["expected_top_models"])
                elif scenario_type == "comparison":
                    result = compare_board_models(
                        scenario["left"]["brand"],
                        scenario["left"]["model"],
                        scenario["right"]["brand"],
                        scenario["right"]["model"],
                        RiderProfile(**scenario["profile"]),
                    )
                    self.assertIsNotNone(result)
                    self.assertEqual(result.ordered_boards[0].model, scenario["expected_winner"])
                elif scenario_type == "relationship":
                    self.assertEqual(relationship_type(scenario["message"]), scenario["expected_relation"])
                elif scenario_type == "determinism":
                    profile = RiderProfile(**scenario["profile"])
                    first = [(row.brand, row.model, row.suggested_size) for row in recommend_models(profile, limit=scenario["limit"])]
                    second = [(row.brand, row.model, row.suggested_size) for row in recommend_models(profile, limit=scenario["limit"])]
                    self.assertEqual(first, second)
                else:
                    self.fail(f"Unsupported scenario type: {scenario_type}")


if __name__ == "__main__":
    unittest.main()
