from __future__ import annotations

import re


INTENTS = {
    "inventory_count_question", "board_search_request", "surfer_fit_request",
    "alternative_request", "comparison_request", "general_board_question",
    "site_help_question",
}


def route_intent(message: str) -> str:
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    if not text:
        return "surfer_fit_request"
    if re.search(r"\b(?:how do i|how can i|help me)\s+(?:use|search|find|navigate)\b|\bhow does (?:quivrr|the site) work\b|\bwhere (?:do i|can i) (?:search|find)\b", text):
        return "site_help_question"
    if re.search(r"\b(?:compare|comparison|versus|vs\.?|better\b.+\bthan)\b", text):
        return "comparison_request"
    if re.search(r"\b(?:instead of|alternative|similar to|what else is similar|what is like|out of stock)\b", text):
        return "alternative_request"
    if re.search(r"\bhow many\b|\bwhat stock\b|\bhow much stock\b|\bboards? (?:are|do you have) available\b", text):
        return "inventory_count_question"
    if re.search(r"\b(?:show me|find me|search for|available|in stock|do you have|stock of|looking for)\b", text):
        return "board_search_request"
    if re.search(r"\bwhat (?:is|are) (?:a |an )?(?:fish|daily driver|groveller|groveler|step[ -]?up|mid[ -]?length|shortboard|longboard)\b|\bwhat waves? (?:is|are|do)\b", text):
        return "general_board_question"
    if re.search(r"^(?:what|why|how|when)\b", text) and re.search(r"\b(?:surfboard|board|volume|litres?|rocker|rails?|concave|fins?|thruster|quad|twin|epoxy|pu|construction)\b", text):
        return "general_board_question"
    return "surfer_fit_request"
