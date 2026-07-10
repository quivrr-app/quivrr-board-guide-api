from __future__ import annotations

import re
from dataclasses import dataclass


INTENTS = {
    "inventory_count_question", "board_search_request", "surfer_fit_request",
    "alternative_request", "comparison_request", "general_board_question",
    "site_help_question", "volume_advice_request", "exact_board_location_request",
    "relationship_request", "greeting_request", "expert_board_question",
}


@dataclass(frozen=True)
class IntentResult:
    intent: str
    needs_board_pair: bool = False
    needs_region: bool = False
    relationship_hint: str | None = None


def classify_intent(message: str) -> IntentResult:
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    if not text:
        return IntentResult(intent="greeting_request")
    if re.fullmatch(r"(?:hey|hi|hello|gday|g'day|yo|morning|afternoon|evening|thanks|thank you|cheers|bodhi|hi bodhi|hey bodhi)[!. ]*", text):
        return IntentResult(intent="greeting_request")
    if re.search(r"\b(?:best|top|favourite|favorite|what should i buy|what would you ride)\b", text) and re.search(r"\b(?:shortboard|fish|groveller|groveler|daily driver|step[ -]?up|board)\b", text):
        return IntentResult(intent="expert_board_question")
    if re.search(r"\b(?:more performance|more forgiving|more paddle|easier paddle|sharper|more responsive|easier|less demanding)(?:\s+than)?\b|\b(?:similar to|alternative to|like|step up from|step down from|after my)\b|\blike .+ but better for\b|\b(?:i ride|currently riding|my current board).+\b(?:want|need|after)\b", text):
        return IntentResult(intent="relationship_request")
    if re.search(r"\b(?:how do i|how can i|help me)\s+(?:use|search|find|navigate)\b|\bhow does (?:quivrr|the site) work\b|\bwhere (?:do i|can i) (?:search|find)\b", text):
        return IntentResult(intent="site_help_question")
    if re.search(r"\b(?:compare|comparison|versus|vs\.?|better\b.+\bthan|difference between)\b", text):
        return IntentResult(intent="comparison_request", needs_board_pair=True)
    if re.search(r"\b(?:where (?:is|can i buy)|give me (?:the )?links?|is there)\b", text) and re.search(r"\b(?:board|buy|link|available|there)\b", text):
        return IntentResult(intent="exact_board_location_request", needs_region=True)
    if re.search(r"\b(?:instead of|alternative|similar to|what else is similar|what is like|out of stock)\b", text):
        return IntentResult(intent="alternative_request")
    if re.search(r"\b(?:what|which|how many)\s+(?:board\s+)?(?:volume|litres?|lits?)\b|\bwhat\s+(?:volume|litre)\s+board\b|\bvolume should i\b", text):
        return IntentResult(intent="volume_advice_request")
    if re.search(r"\bis .+\b(?:a |an )?(?:fish|daily driver|groveller|step[ -]?up)\b", text):
        return IntentResult(intent="general_board_question")
    if re.search(r"\bhow many\b|\bwhat stock\b|\bhow much stock\b|\bboards? (?:are|do you have) available\b", text):
        return IntentResult(intent="inventory_count_question")
    if re.search(r"\b(?:show me|find me|search for|available|in stock|do you have|stock of|looking for)\b", text):
        return IntentResult(intent="board_search_request", needs_region="in europe" in text or "in australia" in text or "in indonesia" in text)
    if re.search(r"\bwhat (?:is|are) (?:a |an )?(?:fish|daily driver|groveller|groveler|step[ -]?up|mid[ -]?length|shortboard|longboard)\b|\bwhat waves? (?:is|are|do)\b", text):
        return IntentResult(intent="general_board_question")
    if re.search(r"^(?:what|why|how|when)\b", text) and re.search(r"\b(?:surfboard|board|volume|litres?|rocker|rails?|concave|fins?|thruster|quad|twin|epoxy|pu|construction)\b", text):
        return IntentResult(intent="general_board_question")
    return IntentResult(intent="surfer_fit_request")


def route_intent(message: str) -> str:
    return classify_intent(message).intent
