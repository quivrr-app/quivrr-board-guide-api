from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests


SUPPORTED_REGION_PATHS = ("/australia", "/europe", "/indonesia", "/united-states")
UNSAFE_URL_TOKENS = ("construction=", "volume=", "boardSizeId=", "autoSearch=")
FAMILY_CATEGORIES = {
    "performance_shortboard": {
        "high performance shortboard",
        "performance daily driver",
        "competition shortboard",
    },
    "fish": {
        "fish",
        "performance fish",
        "cruisy fish",
        "modern fish",
        "traditional fish",
        "small wave fish",
        "fish hybrid",
        "twin fin performance",
    },
}


def build_session(token: str | None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def call_chat(session: requests.Session, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(f"{base_url}/api/board-guide/chat", json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def check_search_urls(recommendations: list[dict[str, Any]]) -> None:
    for item in recommendations:
        url = item.get("searchUrl") or item.get("quivrrSearchUrl") or ""
        assert_true(url.startswith("https://quivrr.app/"), f"Invalid search host: {url}")
        assert_true(any(path in url for path in SUPPORTED_REGION_PATHS), f"Unsupported regional path: {url}")
        for token in UNSAFE_URL_TOKENS:
            assert_true(token not in url, f"Unsafe standard recommendation URL: {url}")


def assert_family(recommendations: list[dict[str, Any]], family: str) -> None:
    allowed = FAMILY_CATEGORIES[family]
    actual = {(item.get("category") or "").lower() for item in recommendations}
    assert_true(bool(actual), f"No recommendation categories returned for {family}")
    unexpected = sorted(actual - allowed)
    assert_true(not unexpected, f"Incoherent {family} shortlist categories: {unexpected}")


def assert_only_verified_stock(recommendations: list[dict[str, Any]]) -> None:
    for item in recommendations:
      assert_true((item.get("availableCount") or 0) > 0, f"Stock-only request included unavailable board: {item.get('brand')} {item.get('model')}")
      assert_true(item.get("availabilityStatus") == "available", f"Stock-only request included non-available status: {item.get('availabilityStatus')}")


def run(base_url: str, token: str | None) -> list[tuple[str, bool, str]]:
    session = build_session(token)
    results: list[tuple[str, bool, str]] = []

    def scenario(name: str, fn) -> None:
        try:
            fn()
            results.append((name, True, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, f"FAIL: {exc}"))

    scenario("1. Health endpoint returns status ok", lambda: assert_true(
        session.get(f"{base_url}/api/health", timeout=30).json().get("status") == "ok",
        "Health status was not ok",
    ))

    scenario("2. Hello returns no recommendations", lambda: assert_true(
        call_chat(session, base_url, {"message": "Hello", "region": "AU"}).get("recommendations") == [],
        "Greeting returned recommendations",
    ))

    def misspelled_greeting() -> None:
        data = call_chat(session, base_url, {"message": "Hey Bohdi", "region": "AU"})
        assert_true(data.get("recommendations") == [], "Misspelled greeting returned recommendations")
        assert_true(data.get("volumeGuidance") is None, "Misspelled greeting returned volume guidance")
        assert_true(data.get("category") is None, "Misspelled greeting resolved a category")
    scenario("3. Hey Bohdi returns no recommendations, no volume guidance and no category", misspelled_greeting)

    scenario("4. General help returns no recommendations", lambda: assert_true(
        call_chat(session, base_url, {"message": "Can you help me?", "region": "AU"}).get("recommendations") == [],
        "General help returned recommendations",
    ))

    def broad_fish() -> None:
        data = call_chat(session, base_url, {
            "message": "I need a fish for weak waves around my usual volume",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "AU", "wave_type": "Beach Break", "wave_power": "Weak"},
            "region": "AU",
        })
        count = len(data.get("recommendations", []))
        assert_true(3 <= count <= 6, f"Expected 3-6 recommendations, got {count}")
        assert_family(data.get("recommendations", []), "fish")
    scenario("5. Broad fish request returns between 3 and 6 coherent fish recommendations", broad_fish)

    def no_overflow() -> None:
        data = call_chat(session, base_url, {
            "message": "What should I ride next?",
            "profile": {"weight_kg": 78, "ability": "Advanced", "region": "ID", "wave_type": "Point Break", "wave_size": "3-5ft"},
            "region": "ID",
        })
        assert_true(len(data.get("recommendations", [])) <= 6, "Recommendation response exceeded six")
    scenario("6. No recommendation response exceeds 6", no_overflow)

    def rec_contract() -> None:
        data = call_chat(session, base_url, {
            "message": "Show me six performance shortboards",
            "profile": {"weight_kg": 75, "ability": "Advanced", "region": "AU", "wave_type": "Point Break", "wave_power": "Average to Powerful"},
            "region": "AU",
        })
        for item in data.get("recommendations", []):
            assert_true(bool(item.get("brand")), "Recommendation missing brand")
            assert_true(bool(item.get("model")), "Recommendation missing model")
        assert_true(data.get("category") == "performance_shortboard", "Performance request did not resolve performance category")
        assert_true((data.get("categorySource") or "") == "explicit_user_request", "Performance category source was not explicit user request")
        assert_family(data.get("recommendations", []), "performance_shortboard")
    scenario("7. Performance shortlist stays coherent and returns category metadata", rec_contract)

    scenario("8. Every supplied search URL uses quivrr.app and a supported regional path", lambda: check_search_urls(
        call_chat(session, base_url, {
            "message": "I need a daily driver for 3 to 5ft surf",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "US", "wave_type": "Beach Break", "wave_size": "3-5ft"},
            "region": "US",
        }).get("recommendations", [])
    ))

    def follow_up_state() -> None:
        first = call_chat(session, base_url, {
            "message": "I need a fish for weak waves around my usual volume",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "ID", "wave_type": "Beach Break", "wave_power": "Weak"},
            "region": "ID",
        })
        second = call_chat(session, base_url, {
            "message": "Tell me about number 1",
            "conversationState": first.get("conversationState"),
            "region": "ID",
        })
        assert_true("Want the design details" in second.get("reply", ""), "Numbered follow-up did not resolve")
    scenario("9. Follow-up conversation state can reference prior recommendations", follow_up_state)

    def anonymous_isolation() -> None:
        data = call_chat(session, base_url, {"message": "What's my name?", "region": "AU"})
        assert_true("Nathan" not in data.get("reply", ""), "Anonymous response exposed a saved name")
        assert_true(not data.get("profileLoaded"), "Anonymous response claimed profileLoaded")
    scenario("10. Anonymous response does not expose a user name or saved profile", anonymous_isolation)

    if token:
        scenario("11. Authenticated mode reports profileLoaded true", lambda: assert_true(
            call_chat(session, base_url, {"message": "What's my name?"}).get("profileLoaded") is True,
            "Authenticated response did not report profileLoaded true",
        ))
    else:
        results.append(("11. Authenticated mode reports profileLoaded true", True, "PASS: skipped (no bearer token supplied)"))

    def anonymous_conversation_contract() -> None:
        profile = {
            "region": "ID",
            "ability": "Advanced",
            "current_volume_litres": 28.6,
            "preferred_volume_min_litres": 27.5,
            "preferred_volume_max_litres": 30,
            "wave_type": "Reef Break",
            "home_break": "Canggu",
            "preferred_brands": ["JS Industries", "Album"],
            "goal": "Performance progression",
        }
        transcript: list[dict[str, str]] = []
        conversation_state: dict[str, Any] = {}

        def turn(message: str) -> dict[str, Any]:
            nonlocal conversation_state
            payload = {
                "message": message,
                "region": "ID",
                "pageContext": "quivrr.surf",
                "conversation": transcript,
                "profile": profile,
                "conversationState": conversation_state,
                "clientCapabilities": {
                    "supportsRecommendationCards": True,
                    "supportsDeepLinks": True,
                },
            }
            data = call_chat(session, base_url, payload)
            transcript.extend([
                {"role": "user", "content": message},
                {"role": "assistant", "content": data.get("reply", "")},
            ])
            conversation_state = data.get("conversationState") or conversation_state
            return data

        hello = turn("Hello")
        assert_true(hello.get("normalizedIntent") == "GREETING", "Hello did not classify as greeting")
        assert_true(len(hello.get("recommendations", [])) == 0, "Hello returned cards")

        help_data = turn("What can you help me with?")
        assert_true(help_data.get("intent") == "capability_help_request", "Capability help intent routed incorrectly")
        assert_true("choose a board" in help_data.get("reply", "").lower(), "Capability help reply missing Bodhi help")
        assert_true("start in the" not in help_data.get("reply", "").lower(), "Capability help fell into site help")

        fish = turn("I want a fish for small weak waves around my normal volume.")
        recommendations = fish.get("recommendations", [])
        assert_true(3 <= len(recommendations) <= 6, f"Expected 3-6 fish cards, got {len(recommendations)}")
        assert_true(len({item.get('brand') for item in recommendations}) >= 3, "Expected at least 3 brands in broad fish set")
        check_search_urls(recommendations)

        detail = turn("Tell me about number 3.")
        third = recommendations[2]
        assert_true(third["brand"] in detail.get("reply", "") and third["model"] in detail.get("reply", ""), "Numbered detail did not resolve the third board")
        state_after_detail = detail.get("conversationState", {}).get("lastRecommendations", [])
        assert_true(len(state_after_detail) >= 3, "Detail follow-up did not preserve the active recommendation set")

        compare = turn("Compare number 1 and number 4.")
        first = recommendations[0]
        fourth = recommendations[3]
        compare_reply = compare.get("reply", "")
        assert_true(first["brand"] in compare_reply and first["model"] in compare_reply, "Comparison did not reference first board")
        assert_true(fourth["brand"] in compare_reply and fourth["model"] in compare_reply, "Comparison did not reference fourth board")
        comparison_boards = compare.get("conversationState", {}).get("comparisonBoards", [])
        assert_true(len(comparison_boards) == 2, "Comparison context was not persisted")

        paddle = turn("Which one paddles best?")
        assert_true("paddle" in paddle.get("reply", "").lower(), "Paddle follow-up did not use active comparison context")

        available = turn("Only show the boards currently available in Indonesia.")
        filtered = available.get("recommendations", [])
        original_pairs = {(item["brand"], item["model"]) for item in recommendations}
        filtered_pairs = {(item["brand"], item["model"]) for item in filtered}
        assert_true(filtered_pairs.issubset(original_pairs), "Availability filter introduced unrelated boards")

        education = turn("What does a swallow tail change?")
        education_reply = education.get("reply", "").lower()
        assert_true("swallow tail" in education_reply and "hold" in education_reply, "Education reply fell back generically")
        assert_true(len(education.get("recommendations", [])) == 0, "Education reply returned recommendation cards")

    scenario("12. Anonymous multi-turn conversation preserves state, safe links, follow-ups and education", anonymous_conversation_contract)

    def stock_only_contract() -> None:
        initial = call_chat(session, base_url, {
            "message": "I need a new short board, just show me ones in stock in indo",
            "profile": {"weight_kg": 75, "ability": "Advanced", "region": "ID", "wave_type": "Reef Break", "wave_power": "Average to Powerful"},
            "region": "ID",
        })
        cards = initial.get("recommendations", [])
        assert_only_verified_stock(cards)
        assert_true((initial.get("conversationState") or {}).get("availabilityConstraint") == "VERIFIED_IN_STOCK", "Stock-only constraint was not persisted")
        follow_up = call_chat(session, base_url, {
            "message": "Show me fish instead",
            "region": "ID",
            "conversationState": initial.get("conversationState"),
            "intakeState": initial.get("intakeState"),
        })
        assert_only_verified_stock(follow_up.get("recommendations", []))
        assert_true((follow_up.get("conversationState") or {}).get("availabilityConstraint") == "VERIFIED_IN_STOCK", "Stock-only constraint did not persist to follow-up")
        relaxed = call_chat(session, base_url, {
            "message": "Show catalogue options too",
            "region": "ID",
            "conversationState": follow_up.get("conversationState"),
            "intakeState": follow_up.get("intakeState"),
        })
        assert_true((relaxed.get("conversationState") or {}).get("availabilityConstraint") in {None, ""}, "Stock-only constraint did not clear")
        assert_true(any((item.get("availableCount") or 0) == 0 for item in relaxed.get("recommendations", [])), "Relaxed stock request did not restore catalogue options")

    scenario("13. Explicit stock-only requests preserve and can remove the verified-stock constraint", stock_only_contract)

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://quivrr-board-guide-api.azurewebsites.net")
    args = parser.parse_args()

    token = os.getenv("BODHI_TEST_BEARER_TOKEN")
    results = run(args.base_url.rstrip("/"), token)
    failed = False
    for name, ok, message in results:
        print(f"{message} - {name}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
