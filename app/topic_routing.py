"""Current-message topic pivots that must outrank conversation memory."""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.inventory_client import normalise_region


@dataclass(frozen=True)
class TopicRoute:
    kind: str
    region: str | None = None
    correction: bool = False

    @property
    def pivot(self) -> bool:
        # A bare correction can still refine a recommendation (for example,
        # "actually, make it a fish"). Only an independently scoped platform
        # question must discard the prior recommendation plan outright.
        return self.kind.startswith("PLATFORM_") or self.kind == "REGIONAL_AVAILABLE_BOARD_COUNT"


def classify_topic_route(message: str) -> TopicRoute:
    text = (message or "").lower()
    correction = bool(re.search(r"^\s*(?:no[, ]|nope\b|actually\b|instead\b|forget that\b|new question\b|i mean\b)", text))
    region = normalise_region(next((name for name in ("australia", "australian", "aus", "europe", "indonesia", "indo", "united states", "usa") if name in text), None))
    if "aus" in text:
        region = "AU"
    if "indo" in text:
        region = "ID"
    if re.search(r"\bhow many\b", text) and re.search(r"\b(?:available|stock|can i buy)\b", text):
        return TopicRoute("REGIONAL_AVAILABLE_BOARD_COUNT", region, correction)
    if re.search(r"\bhow many\b", text) and re.search(r"\b(?:boards?|boartds?|models?)\b", text):
        return TopicRoute("PLATFORM_CATALOGUE_COUNT", region, correction)
    if re.search(r"\bhow many\b", text) and "brands" in text:
        return TopicRoute("PLATFORM_BRAND_COUNT", region, correction)
    if re.search(r"\b(?:what regions|regions are live)\b", text):
        return TopicRoute("PLATFORM_REGION_LIST", None, correction)
    if re.search(r"\b(?:foamies?|softboards?|cheap beginner boards?|premium boards?)\b", text) or (
        "catalogue" in text and re.search(r"\b(?:what|why|do you|does quivrr|is the)\b", text)
    ):
        return TopicRoute("PLATFORM_CATALOGUE_SCOPE", region, correction)
    if correction:
        return TopicRoute("NEW_GENERAL_TOPIC", region, True)
    return TopicRoute("CONTINUE_CURRENT_TOPIC")
