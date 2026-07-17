from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import BoardReference, ConversationState


PHASE_BY_INTENT = {
    "GREETING": "OPEN",
    "GENERAL_HELP": "DISCOVERY",
    "BOARD_RECOMMENDATION": "RECOMMENDATION",
    "BOARD_COMPARISON": "COMPARISON",
    "BOARD_DETAILS": "EXPLANATION",
    "BOARD_CATEGORY_EDUCATION": "EXPLANATION",
    "FIN_GUIDANCE": "EXPLANATION",
    "WAVE_GUIDANCE": "EXPLANATION",
    "VOLUME_GUIDANCE": "CLARIFICATION",
    "DIMENSION_GUIDANCE": "CLARIFICATION",
    "AVAILABILITY": "STOCK_CHECK",
    "REGIONAL_SEARCH": "STOCK_CHECK",
    "FOLLOW_UP": "REFINEMENT",
    "OFF_TOPIC": "OFF_TOPIC_REDIRECT",
    "ABUSIVE": "OFF_TOPIC_REDIRECT",
    "SMALL_TALK": "CLOSURE",
    "CONVERSATION_RESET": "OPEN",
}


@dataclass(frozen=True)
class ConversationDirective:
    phase: str
    reset_scope: str | None = None
    target_surfer: str = "account_holder"
    rejected_board: BoardReference | None = None
    rejection_reason: str | None = None
    resolved_reference: BoardReference | None = None
    needs_reference_clarification: bool = False
    refinement: str | None = None

    @property
    def clears_rider_brief(self) -> bool:
        return self.reset_scope in {"brief", "surfer"}


def _cards(state: ConversationState | None):
    if not state:
        return []
    return state.last_recommendations or state.mentioned_boards


def _indexed_card(text: str, state: ConversationState | None):
    cards = _cards(state)
    words = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "sixth": 5}
    for word, index in words.items():
        if re.search(rf"\b{word}(?: one| board)?\b", text) and index < len(cards):
            return cards[index]
    match = re.search(r"\b(?:number|board)\s*([1-6])\b", text)
    if match and int(match.group(1)) <= len(cards):
        return cards[int(match.group(1)) - 1]
    return None


def _last_reference(state: ConversationState | None):
    cards = _cards(state)
    if len(cards) == 1:
        return cards[0]
    if state and len(state.comparison_boards) == 1:
        return state.comparison_boards[0]
    return None


def control_conversation(message: str, normalized_intent: str, state: ConversationState | None) -> ConversationDirective:
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    phase = PHASE_BY_INTENT.get(normalized_intent, "DISCOVERY")

    different_surfer = bool(re.search(
        r"\b(?:different surfer|for my (?:wife|husband|partner|friend|son|daughter)|this is for my|not for me)\b",
        text,
    ))
    reset_only = bool(re.fullmatch(
        r"(?:start again|start over|new board|forget that|new search|reset)(?: please)?[.! ]*",
        text,
    ))
    reset_then_continue = bool(re.match(
        r"(?:start again|start over|forget that|new search|reset)[.!,:; -]+\S+",
        text,
    ))
    reset_brief = reset_only or reset_then_continue
    reset_scope = "surfer" if different_surfer else "brief" if reset_brief else None
    target_surfer = "different_surfer" if different_surfer else (state.target_surfer if state else "account_holder")

    rejection = bool(re.search(
        r"\b(?:i (?:do not|don't) like|not keen on|reject|remove|skip|rubbish recommendation|bad recommendation)\b",
        text,
    ))
    indexed = _indexed_card(text, state)
    rejected = indexed if rejection else None
    if rejection and rejected is None:
        cards = _cards(state)
        rejected = cards[0] if cards else None
    rejected_ref = BoardReference(brand=rejected.brand, model=rejected.model) if rejected else None

    pronoun = bool(re.search(r"\b(?:it|that one|this one|that board|the xl)\b", text))
    resolved = indexed or (_last_reference(state) if pronoun else None)
    resolved_ref = BoardReference(brand=resolved.brand, model=resolved.model) if resolved else None
    ambiguous = pronoun and resolved_ref is None and len(_cards(state)) > 1

    refinement = None
    if re.search(r"\b(?:more paddle|easier to paddle|easier.*paddle|paddles? better)\b", text):
        refinement = "more_paddle"
    elif re.search(r"\b(?:easier|more forgiving)\b", text):
        refinement = "more_forgiving"
    elif re.search(r"\b(?:more performance|sharper|more responsive)\b", text):
        refinement = "more_performance"
    elif re.search(r"\b(?:weaker waves?|less powerful)\b", text):
        refinement = "weaker_waves"

    if rejection or refinement:
        phase = "REFINEMENT"
    if reset_scope and (different_surfer or normalized_intent == "CONVERSATION_RESET"):
        phase = "OPEN" if not different_surfer else "DISCOVERY"

    return ConversationDirective(
        phase=phase,
        reset_scope=reset_scope,
        target_surfer=target_surfer,
        rejected_board=rejected_ref,
        rejection_reason="user_rejected" if rejected_ref else None,
        resolved_reference=resolved_ref,
        needs_reference_clarification=ambiguous,
        refinement=refinement,
    )
