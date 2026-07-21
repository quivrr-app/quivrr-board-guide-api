from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.board_expert_matrix import recommend_from_matrix
from app.board_master import MASTER_PATH, find_master_board
from app.family_intent import FamilyIntent, resolve_family_intent
from app.models import ConversationState, RiderProfile
from main import app


FAMILY_PHRASES = {
    "performance_shortboard": [
        "high performance shortboard", "high performance shortboards", "high performance board",
        "performance shorty", "proper shorty", "HPSB", "competition shortboard", "pro board",
        "performance thruster", "perforamce shortboard", "high perfance board",
        "high performance stick", "something spicy", "something for good waves", "something less cruisy",
    ],
    "daily_driver": [
        "daily driver", "everyday shortboard", "one-board quiver", "everyday performance board",
        "performance daily driver", "daily drivver", "everyday board",
    ],
    "fish": ["fish", "performance fish", "modern fish", "high performance fish", "traditional fish", "retro fish", "performnce fish"],
    "groveller": ["groveller", "groveler", "tiny-wave board", "summer slop board", "small-wave twin"],
    "step_up": ["step-up", "stepup", "reef step-up", "travel step-up"],
    "mid_length": ["mid length", "mid-length", "mid lenght"],
    "longboard": ["longboard", "long board", "long bord"],
}
WRAPPERS = ("I want a {}", "Show me a {}", "What about a {}?", "Find me a {} around 29L")


CASES = [
    (family, wrapper.format(phrase))
    for family, phrases in FAMILY_PHRASES.items()
    for phrase in phrases
    for wrapper in WRAPPERS
]


@pytest.mark.parametrize(("expected", "message"), CASES)
def test_family_resolver_covers_public_family_language(expected: str, message: str):
    intent = resolve_family_intent(message)
    assert intent.requested_public_family == expected
    assert intent.explicit is True
    assert intent.confidence >= 0.9


def test_expanded_family_fixture_contains_at_least_150_scenarios():
    assert len(CASES) >= 150


@pytest.mark.parametrize(
    ("message", "family", "detail", "excluded"),
    [
        ("No, high performance boards. These are daily drivers.", "performance_shortboard", "Competition HPSB", "daily_driver"),
        ("A proper step-up, not a mid length.", "step_up", None, "mid_length"),
        ("A groveller, not a fish.", "groveller", None, "fish"),
        ("A performance fish, not a groveller.", "fish", "Performance Fish", "groveller"),
    ],
)
def test_same_turn_corrections(message, family, detail, excluded):
    intent = resolve_family_intent(message)
    assert intent.requested_public_family == family
    assert intent.requested_detailed_category == detail
    assert excluded in intent.excluded_public_families
    assert intent.correction is True


def test_classic_fish_excludes_performance_fish_detail():
    intent = resolve_family_intent("I'm looking for a fish, not a performance fish—a classic one.")
    assert intent.requested_public_family == "fish"
    assert intent.requested_detailed_category == "Traditional Fish"
    assert "Performance Fish" in intent.excluded_detailed_categories


def test_new_explicit_family_replaces_stale_family_and_preserves_rejection():
    previous = ConversationState(
        requestedPublicFamily="fish",
        excludedPublicFamilies=["groveller"],
        familyIntentConfidence=0.98,
    )
    intent = resolve_family_intent("Nice. What about a performance shortboard?", previous)
    assert intent.requested_public_family == "performance_shortboard"
    assert "groveller" in intent.excluded_public_families
    assert "fish" not in intent.excluded_public_families


def test_rejected_family_persists_through_stock_and_volume_followups():
    state = ConversationState(
        requestedPublicFamily="performance_shortboard",
        excludedPublicFamilies=["daily_driver"],
        requestedDetailedCategory="Competition HPSB",
    )
    for message in ("Only in stock.", "Something around 29L.", "Show me more.", "More paddle."):
        intent = resolve_family_intent(message, state)
        assert intent.requested_public_family == "performance_shortboard"
        assert "daily_driver" in intent.excluded_public_families


def test_fin_constraint_does_not_infer_family_and_honours_negative_family():
    intent = resolve_family_intent("Show me a twin that isn't a fish")
    assert intent.requested_public_family is None
    assert intent.requested_fin_setup == "twin"
    assert "fish" in intent.excluded_public_families


def test_matrix_hard_constrains_explicit_hpsb_to_board_master_family():
    profile = RiderProfile(
        weight_kg=75,
        ability="Advanced",
        preferred_board_type="performance shortboard",
        target_volume_litres=29,
        wave_power="Powerful",
        region="ID",
    )
    intent = resolve_family_intent("I want a true high performance shortboard for good waves")
    boards = recommend_from_matrix(profile, limit=12, family_intent=intent)
    assert boards
    assert all(board.authoritative_public_family == "performance_shortboard" for board in boards)
    assert all(find_master_board(board.brand, board.model)["public_family"] == "performance_shortboard" for board in boards)
    assert not any(board.model in {"Phantom", "Xero Gravity", "Rad Ripper"} for board in boards)


def test_matrix_fin_only_request_excludes_fish_without_reclassifying_twins():
    profile = RiderProfile(weight_kg=75, ability="Advanced", target_volume_litres=29, region="ID")
    intent = resolve_family_intent("A twin that is not a fish")
    boards = recommend_from_matrix(profile, limit=12, family_intent=intent)
    assert boards
    assert all(board.authoritative_public_family != "fish" for board in boards)
    assert all("Twin" in {board.primary_fin_setup, *board.alternative_fin_setup} for board in boards)


def test_board_master_authority_is_unchanged():
    assert hashlib.sha256(Path(MASTER_PATH).read_bytes()).hexdigest() == "0330adf012c5e6d67f307db7fdc4b309779d0e6b7c473f482a2ad33cee742899"


@patch("main.safe_ask_bodhi", return_value=(None, None))
@patch("main.enrich_suggestions_with_inventory")
def test_required_multi_turn_family_correction_contract(inventory, _llm):
    inventory.side_effect = lambda rows, profile: [
        row.model_copy(update={
            "available_count": 1,
            "retailer_count": 1,
            "availability_checked": True,
            "availability_status": "retailer_stock",
            "region": profile.region or "ID",
            "region_code": profile.region or "ID",
        })
        for row in rows
    ]
    client = TestClient(app)
    state = None
    conversation = []
    profile = {
        "weight_kg": 75, "ability": "Advanced", "target_volume_litres": 29,
        "region": "ID", "wave_type": "Reef Break", "wave_power": "Average to Powerful",
    }

    def turn(message: str):
        nonlocal state
        response = client.post("/api/board-guide/chat", json={
            "message": message, "region": "ID", "profile": profile,
            "conversation": conversation, "conversationState": state,
        })
        assert response.status_code == 200
        body = response.json()
        conversation.extend([
            {"role": "user", "content": message},
            {"role": "assistant", "content": body["reply"]},
        ])
        state = body["conversationState"]
        return body

    assert turn("G'day")["recommendations"] == []
    fish = turn("I'm looking for some performance fish in my size and in stock.")
    assert {item["authoritativePublicFamily"] for item in fish["recommendations"]} == {"fish"}
    for message in (
        "Nice. What about a performance shortboard?",
        "High performance shortboards?",
        "No, high performance boards. These are daily drivers.",
        "Only in stock.",
        "Give me something with more paddle.",
    ):
        body = turn(message)
        assert body["recommendations"]
        assert {item["authoritativePublicFamily"] for item in body["recommendations"]} == {"performance_shortboard"}
        assert "daily_driver" in body["conversationState"]["excludedPublicFamilies"] if "daily drivers" in message.lower() else True

    compared = turn("Compare the top two.")
    assert len(compared["conversationState"]["comparisonBoards"]) == 2
    twin = turn("Actually, show me a twin that isn't a fish.")
    assert twin["recommendations"]
    assert all(item["authoritativePublicFamily"] != "fish" for item in twin["recommendations"])
    step_up = turn("Start again. I want a proper step-up for hollow reef waves.")
    assert step_up["conversationState"]["requestedPublicFamily"] == "step_up"
    assert step_up["recommendations"]
    assert {item["authoritativePublicFamily"] for item in step_up["recommendations"]} == {"step_up"}
