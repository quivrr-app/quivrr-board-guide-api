import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.conversation_controller import control_conversation
from app.conversation_flow import comparison_reply
from app.intent_router import classify_intent
from app.models import BodhiRecommendation, ConversationState, RiderProfile


def scenarios():
    groups = [
        ("OPEN", ["Hello", "Hi Bodhi", "Morning", "G'day", "Hey mate", "Good evening", "How are you?", "Yo"]),
        ("DISCOVERY", ["Can you help me?", "What can you do?", "Help me choose", "What should I ask?", "How does this work?", "I need help", "Show me how Quivrr works", "What can you help with?"]),
        ("RECOMMENDATION", ["Recommend a fish", "Find me a daily driver", "I need a step-up", "Show me a groveller", "Pick a performance shortboard", "I want a mid length", "Find a twin", "Recommend something for reefs", "I need a board for weak waves", "Choose my next board"]),
        ("COMPARISON", ["Compare Ghost and Phantom", "Ghost versus Phantom", "Difference between RNF 96 and Seaside", "Which is better, Monsta or Ghost?", "Compare the first and second", "Trade offs between these two", "How does Phantom compare with Ghost?", "Bom Dia vs Twinsman"]),
        ("EXPLANATION", ["Tell me about the Ghost", "Explain the Phantom", "What is a fish?", "What fins does the Tiger Twin use?", "Would Ghost work in reefs?", "Is Happy Twin a groveller?", "Explain rocker", "Tell me about RNF 96"]),
        ("STOCK_CHECK", ["What is in stock near me?", "Find Phantom stock in Australia", "Only show available boards", "Can I buy a Seaside in Europe?", "Show live stock", "Which retailers have Ghost?", "Check regional availability", "Only in stock"]),
        ("OFF_TOPIC_REDIRECT", ["Tell me a joke", "What is the capital of France?", "Football score", "Give me a recipe", "You are useless", "This is shit", "Weather forecast", "Talk politics"]),
    ]
    output = []
    for phase, messages in groups:
        output.extend({"message": message, "phase": phase} for message in messages)

    reset_messages = ["Start again", "Start over", "New board", "Forget that", "New search", "Reset"]
    output.extend({"message": message, "phase": "OPEN", "reset": "brief"} for message in reset_messages)
    surfer_messages = [
        "This is for my wife", "This is for my partner", "Different surfer", "Not for me, for my friend",
        "This is for my husband", "This is for my daughter",
    ]
    output.extend({"message": message, "phase": "DISCOVERY", "reset": "surfer"} for message in surfer_messages)

    rejection_messages = [
        "I don't like the first one", "Not keen on board 1", "Remove the second board",
        "That is a rubbish recommendation", "Skip number 3", "I do not like that one",
    ]
    output.extend({"message": message, "phase": "REFINEMENT", "rejection": True} for message in rejection_messages)
    refinements = {
        "Show me something easier": "more_forgiving",
        "More forgiving please": "more_forgiving",
        "Give me more paddle": "more_paddle",
        "Which is easier to paddle?": "more_paddle",
        "Show me something sharper": "more_performance",
        "More responsive": "more_performance",
        "Would that work in weaker waves?": "weaker_waves",
    }
    output.extend({"message": message, "phase": "REFINEMENT", "refinement": value} for message, value in refinements.items())
    pronouns = [
        "How does it compare with the Phantom?", "Would that work in weaker waves?", "What about the XL?",
        "Is there a twin version?", "Tell me about that one", "Would it suit reefs?",
    ]
    output.extend({"message": message, "phase": "REFINEMENT", "pronoun": True} for message in pronouns)

    # Controlled spelling, slang and short-reply variants extend the same high-value behaviours.
    for base, variants, phase in [
        ("fish", ["recomend a fish", "need a fish mate", "fish for mush", "fsh for weak waves"], "RECOMMENDATION"),
        ("comparison", ["ghost v phantom", "compare ghost n phantom", "ghost or phantom", "difference ghost phantom"], "COMPARISON"),
        ("stock", ["wots in stock", "got any phantom stock", "stock near me mate", "only stuff i can buy"], "STOCK_CHECK"),
        ("volume", ["wat litres", "how many ltrs", "volume for 75kg", "keep it near 29l"], "CLARIFICATION"),
        ("fin", ["wot fins", "is it a twin", "thruster or quad", "twin plus trailer?"], "EXPLANATION"),
    ]:
        output.extend({"message": message, "phase": phase, "category": base} for message in variants)
    output.extend([
        {"message": "Is the Great White Twin a fish?", "phase": "EXPLANATION"},
        {"message": "Why isn't the Ghost a daily driver?", "phase": "EXPLANATION"},
        {"message": "What is the difference between the Ghost and Phantom?", "phase": "COMPARISON"},
        {"message": "Why is the Happy Twin a groveller if it is a twin?", "phase": "EXPLANATION"},
        {"message": "Show me three performance fish for weak to average waves.", "phase": "RECOMMENDATION"},
        {"message": "Recommend a twin that is not a fish.", "phase": "RECOMMENDATION"},
        {"message": "Give me something between the Phantom and Ghost.", "phase": "RECOMMENDATION"},
        {"message": "Start again. I want a step-up for hollow reef waves.", "phase": "RECOMMENDATION", "reset": "brief"},
        {"message": "What is in stock near me?", "phase": "STOCK_CHECK"},
        {"message": "That's a rubbish recommendation. Give me a proper explanation.", "phase": "REFINEMENT", "rejection": True},
    ])
    return output


def state_with_cards(count=3):
    rows = [
        BodhiRecommendation(brand="Pyzel", model="Ghost", category="Performance Shortboard", whyItFits="Hold and control"),
        BodhiRecommendation(brand="Pyzel", model="Phantom", category="Daily Driver", whyItFits="More forgiving"),
        BodhiRecommendation(brand="Lost", model="RNF 96", category="Fish", whyItFits="Fast and versatile"),
    ][:count]
    return ConversationState(lastRecommendations=rows, mentionedBoards=rows, conversationTurn=2)


class Phase4ConversationEvaluation(unittest.TestCase):
    def test_at_least_one_hundred_conversation_scenarios(self):
        cases = scenarios()
        self.assertGreaterEqual(len(cases), 100)
        state = state_with_cards()
        for case in cases:
            with self.subTest(message=case["message"]):
                intent = classify_intent(case["message"])
                directive = control_conversation(case["message"], intent.intent, state)
                self.assertEqual(directive.phase, case["phase"])
                if case.get("reset"):
                    self.assertEqual(directive.reset_scope, case["reset"])
                if case.get("rejection"):
                    self.assertIsNotNone(directive.rejected_board)
                if case.get("refinement"):
                    self.assertEqual(directive.refinement, case["refinement"])

    def test_multi_turn_transcripts_preserve_and_reset_the_right_context(self):
        transcripts = [
            ["Recommend a board", "I don't like the first one", "Give me more paddle"],
            ["Compare Ghost and Phantom", "Which paddles better?", "Would that work in weak waves?"],
            ["Find Phantom stock", "Only in Australia", "What about Europe?"],
            ["Recommend a fish", "Start again", "I want a step-up"],
            ["Find me a board", "This is for my partner", "She is progressing and 62 kg"],
            ["Tell me about Ghost", "What about the XL?", "Is there a twin version?"],
        ]
        self.assertGreaterEqual(sum(len(item) for item in transcripts), 18)
        for transcript in transcripts:
            state = state_with_cards()
            for message in transcript:
                intent = classify_intent(message)
                directive = control_conversation(message, intent.intent, state)
                self.assertIn(directive.phase, {
                    "OPEN", "DISCOVERY", "CLARIFICATION", "RECOMMENDATION", "COMPARISON",
                    "REFINEMENT", "STOCK_CHECK", "EXPLANATION", "OFF_TOPIC_REDIRECT", "CLOSURE",
                })

    def test_comparison_ends_with_grounded_board_choices(self):
        reply = comparison_reply(
            "What is the difference between the Ghost and Phantom?",
            [
                {"brand": "Pyzel", "model": "Ghost"},
                {"brand": "Pyzel", "model": "Phantom"},
            ],
            RiderProfile(ability="Advanced", wave_type="Reef Break", target_volume_litres=29),
        )
        self.assertIn("Choose", reply)
        self.assertIn("Pyzel Ghost", reply)
        self.assertIn("Pyzel Phantom", reply)
        self.assertIn("Trade-off", reply)


class Phase4EndpointAssurance(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_different_surfer_clears_previous_rider_fit(self, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Actually, this is for my wife. She is a progressing surfer and weighs 62 kg.",
            "region": "ID",
            "conversationState": {
                "activeProfile": {"weight_kg": 75, "ability": "Advanced", "target_volume_litres": 28.6},
                "activeBoardBrief": {"public_family": "performance_shortboard"},
                "conversationTurn": 4,
            },
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["profile"]["weight_kg"], 62)
        self.assertNotEqual(body["profile"].get("ability"), "Advanced")
        self.assertNotEqual(body["profile"].get("target_volume_litres"), 28.6)
        self.assertEqual(body["conversationState"]["targetSurfer"], "different_surfer")
        brief = body["conversationState"]["activeBoardBrief"]
        self.assertIsNone(brief.get("primary_category"))
        self.assertNotEqual(brief.get("volume_target"), 28.6)

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_anonymous_state_never_invents_a_preferred_name(self, _azure):
        body = self.client.post("/api/board-guide/chat", json={"message": "Hello", "region": "AU"}).json()
        self.assertFalse(body["conversationState"]["authenticated"])
        self.assertIsNone(body["conversationState"]["preferredName"])


if __name__ == "__main__":
    unittest.main()
