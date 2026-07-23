"""Small deterministic policy helpers for Bodhi's conversational recovery."""

from __future__ import annotations

from dataclasses import dataclass
import re

FOLLOW_UP_EXPLANATION = "explain_previous_failure"
FOLLOW_UP_CORRECTION = "acknowledge_correction"


@dataclass(frozen=True)
class LanguageTone:
    level: str = "none"
    target: str = "situation"
    continue_task: bool = True


def classify_language_tone(message: str) -> LanguageTone:
    text = (message or "").lower()
    if re.search(r"\b(?:kill|hurt|attack)\b", text):
        return LanguageTone("threatening", "third_party", False)
    if re.search(r"\b(?:fucking useless|are you stupid|what the fuck are you doing)\b", text):
        return LanguageTone("abusive", "assistant")
    if re.search(r"\b(?:shit|bloody useless|what the hell|fucked|damn)\b", text):
        return LanguageTone("frustrated", "situation")
    return LanguageTone()


def follow_up_kind(message: str, previous_outcome: str | None) -> str | None:
    if not previous_outcome or not previous_outcome.startswith("SUCCESS_NO_"):
        return None
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    if re.fullmatch(r"(?:why|how come|what happened)[?!. ]*", text):
        return FOLLOW_UP_EXPLANATION
    if re.search(r"\b(?:yes you can|that(?:'s| is) wrong|you just told me|you said there were boards|try again|search again|you misunderstood|don'?t repeat yourself)\b", text):
        return FOLLOW_UP_CORRECTION
    return None


def is_performance_fish_request(message: str) -> bool:
    return bool(re.search(r"\b(?:pro|performance|high[ -]?performance|modern|fast)\s+fish\b|\bfish\s+(?:that\s+)?(?:still\s+)?performs?\b", (message or "").lower()))


def response_signature(reply: str, outcome: str) -> str:
    normalised = re.sub(r"[^a-z0-9]+", " ", (reply or "").lower()).strip()
    return f"{outcome}:{normalised[:220]}"


def recovery_opening(kind: str | None, tone: LanguageTone) -> str:
    if tone.level in {"frustrated", "abusive"}:
        return "Fair call. That result was not useful."
    if kind == FOLLOW_UP_EXPLANATION:
        return "The overall regional inventory is available, but my first search was too narrow."
    return "You’re right. I searched too narrowly."


def prompt_disclosure_reply() -> str:
    return "I can’t provide internal instructions, but I can explain how I reached a recommendation or what verified information I used."
