from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests


SUPPORTED_REGION_PATHS = ("/australia", "/europe", "/indonesia", "/united-states")


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

    scenario("3. General help returns no recommendations", lambda: assert_true(
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
    scenario("4. Broad fish request returns between 3 and 6 recommendations", broad_fish)

    def no_overflow() -> None:
        data = call_chat(session, base_url, {
            "message": "What should I ride next?",
            "profile": {"weight_kg": 78, "ability": "Advanced", "region": "ID", "wave_type": "Point Break", "wave_size": "3-5ft"},
            "region": "ID",
        })
        assert_true(len(data.get("recommendations", [])) <= 6, "Recommendation response exceeded six")
    scenario("5. No recommendation response exceeds 6", no_overflow)

    def rec_contract() -> None:
        data = call_chat(session, base_url, {
            "message": "Show me fish boards around 30 litres in Europe",
            "region": "EU",
        })
        for item in data.get("recommendations", []):
            assert_true(bool(item.get("brand")), "Recommendation missing brand")
            assert_true(bool(item.get("model")), "Recommendation missing model")
    scenario("6. Every recommendation includes brand and model", rec_contract)

    scenario("7. Every supplied search URL uses quivrr.app and a supported regional path", lambda: check_search_urls(
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
    scenario("8. Follow-up conversation state can reference prior recommendations", follow_up_state)

    def anonymous_isolation() -> None:
        data = call_chat(session, base_url, {"message": "What's my name?", "region": "AU"})
        assert_true("Nathan" not in data.get("reply", ""), "Anonymous response exposed a saved name")
        assert_true(not data.get("profileLoaded"), "Anonymous response claimed profileLoaded")
    scenario("9. Anonymous response does not expose a user name or saved profile", anonymous_isolation)

    if token:
        scenario("10. Authenticated mode reports profileLoaded true", lambda: assert_true(
            call_chat(session, base_url, {"message": "What's my name?"}).get("profileLoaded") is True,
            "Authenticated response did not report profileLoaded true",
        ))
    else:
        results.append(("10. Authenticated mode reports profileLoaded true", True, "PASS: skipped (no bearer token supplied)"))

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
