"""Conversation-first orchestration for Bodhi's governed operations.

The decision is intentionally separate from the deterministic implementations.
Conversation history may resolve a reference or pending action, but the current
raw message must independently request work before an action tool can run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import ConversationState


TOOL_NAMES = {
    "resolve_board",
    "recommend_boards",
    "check_model_availability",
    "compare_boards",
    "get_regional_inventory_summary",
    "get_platform_catalogue_facts",
    "read_authenticated_profile",
    "propose_profile_update",
    "confirm_profile_update",
    "reject_profile_update",
    "generate_exact_search_handoff",
}


@dataclass(frozen=True)
class ConversationDecision:
    interaction_type: str
    requires_tool: bool
    candidate_tool: str | None
    references_pending_action: bool
    references_active_board: bool
    topic_changed: bool


def _normalise(message: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,;]", " ", (message or "").strip().lower())).strip()


def _has_pending_action(state: ConversationState | None) -> bool:
    return bool(state and (state.pending_action or state.pending_profile_update))


def _is_confirmation(text: str) -> bool:
    return bool(re.fullmatch(
        r"(?:(?:yes|yep|yeah)(?:\s+(?:please\s+)?(?:do|update|save)\s+it)?|confirm|do it|update it|save it|please change it|that(?:'s| is) right)[!. ]*",
        text,
    ))


def _is_rejection(text: str) -> bool:
    return bool(re.fullmatch(r"(?:no|nope|not now|leave it|don't|do not|cancel)[!. ]*", text))


def _is_acknowledgement(text: str) -> bool:
    """Recognise conversational closure, not just a finite list of exact phrases."""
    if not text:
        return True
    tokens = set(re.findall(r"[a-z']+", text))
    acknowledgement_tokens = {
        "thanks", "thank", "you", "great", "nice", "cool", "okay", "ok", "cheers",
        "appreciate", "got", "it", "later", "checking", "sounds", "good", "for", "that",
        "makes", "sense",
    }
    return bool(tokens) and tokens <= acknowledgement_tokens


def _has_rider_recommendation_signal(text: str) -> bool:
    """Recognise a substantive rider brief, including terse chat follow-ups."""
    return bool(re.search(
        r"\b(?:\d{2,3}\s*kg|beginner|intermediate|advanced|expert|surf(?:ing)?|waves?|beach breaks?|reef breaks?|point breaks?|daily driver|short ?board|fish|mid ?length|longboard|volume|litres?|\d+(?:-\d+)?\s*ft)\b",
        text,
    ))


def decide_conversation(
    message: str,
    *,
    normalized_intent: str,
    topic_kind: str,
    state: ConversationState | None,
    event_type: str | None = None,
    profile_change_requested: bool = False,
    active_board_requested: bool = False,
    has_conversation_history: bool = False,
) -> ConversationDecision:
    """Select at most one governed operation from the *current* message."""
    text = _normalise(message)
    pending = _has_pending_action(state)
    references_active_board = bool(active_board_requested or re.search(r"\b(?:it|this|that|that board|the board)\b", text))
    topic_changed = topic_kind not in {"CONTINUE_CURRENT_TOPIC", "NEW_GENERAL_TOPIC"}

    if event_type == "AUTH_STATE_UPDATE" or normalized_intent in {"AUTH_STATE_UPDATE", "IDENTITY_QUERY"}:
        return ConversationDecision("action_request", True, "read_authenticated_profile", False, False, False)
    if profile_change_requested:
        return ConversationDecision("action_request", True, "propose_profile_update", False, False, False)
    if pending and _is_confirmation(text):
        return ConversationDecision("confirmation", True, "confirm_profile_update", True, False, False)
    if pending and _is_rejection(text):
        return ConversationDecision("rejection", True, "reject_profile_update", True, False, False)
    if normalized_intent == "NO_REQUEST" or re.search(r"\b(?:i (?:did not|didn't) ask|i wasn't asking|not what i asked)\b", text):
        return ConversationDecision("correction", False, None, False, False, True)
    if _is_acknowledgement(text) or normalized_intent in {"GREETING", "SMALL_TALK", "ACKNOWLEDGEMENT_ONLY"}:
        return ConversationDecision("conversation", False, None, False, False, False)
    if normalized_intent == "CONVERSATION_RESET":
        return ConversationDecision("action_request", False, None, False, False, True)
    if has_conversation_history and normalized_intent == "FOLLOW_UP":
        return ConversationDecision("action_request", True, "recommend_boards", False, references_active_board, False)
    if normalized_intent in {
        "GENERAL_HELP", "PROFILE_QUESTION", "VOLUME_GUIDANCE", "DIMENSION_GUIDANCE",
        "CONSTRUCTION_GUIDANCE", "FIN_GUIDANCE", "WAVE_GUIDANCE", "BOARD_CATEGORY_EDUCATION",
        "QUIVER_REVIEW", "QUIVER_GAP", "PROGRESSION", "FOLLOW_UP", "OFF_TOPIC", "ABUSIVE", "PROMPT_INJECTION",
    }:
        return ConversationDecision("question", False, None, False, references_active_board, topic_changed)
    if topic_kind == "REGIONAL_AVAILABLE_BOARD_COUNT":
        return ConversationDecision("question", True, "get_regional_inventory_summary", False, False, True)
    if topic_kind.startswith("PLATFORM_"):
        return ConversationDecision("question", True, "get_platform_catalogue_facts", False, False, True)
    if normalized_intent == "BOARD_COMPARISON":
        return ConversationDecision("action_request", True, "compare_boards", False, references_active_board, topic_changed)
    if normalized_intent == "AVAILABILITY":
        return ConversationDecision("action_request", True, "check_model_availability", False, references_active_board, topic_changed)
    if normalized_intent in {"BOARD_DETAILS", "BRAND_QUESTION"}:
        return ConversationDecision("question", True, "resolve_board", False, references_active_board, topic_changed)
    if normalized_intent == "BOARD_RECOMMENDATION":
        return ConversationDecision("action_request", True, "recommend_boards", False, False, topic_changed)
    if (
        state
        and state.previous_outcome in {"SUCCESS_NO_EXACT_MATCH", "SUCCESS_NO_EXPANDED_MATCH"}
        and re.fullmatch(r"why[?!. ]*", text)
    ):
        # A bare “why?” can only resume a just-completed, constrained search.
        # It is not a generic shortcut for an unrelated educational question.
        return ConversationDecision("question", True, "recommend_boards", False, True, False)
    if normalized_intent == "FOLLOW_UP" and state and state.last_recommendations and re.search(
        r"\b(?:more paddle|easier|forgiving|more performance|sharper|alternative|instead|another|show me)\b",
        text,
    ):
        return ConversationDecision("action_request", True, "recommend_boards", False, references_active_board, False)
    if has_conversation_history and _has_rider_recommendation_signal(text):
        return ConversationDecision("action_request", True, "recommend_boards", False, references_active_board, False)
    if re.match(r"^(?:why|what|how|when)\b", text):
        return ConversationDecision("question", False, None, False, references_active_board, topic_changed)
    if _has_rider_recommendation_signal(text):
        return ConversationDecision("action_request", True, "recommend_boards", False, False, topic_changed)
    if has_conversation_history and re.search(
        r"\b(?:why|more|another|alternative|instead|stock|available|check)\b",
        text,
    ):
        # Legacy clients may supply a transcript instead of ConversationState.
        # The current text still has to ask for a concrete continuation action.
        return ConversationDecision("action_request", True, "recommend_boards", False, references_active_board, False)
    return ConversationDecision("question" if "?" in text else "conversation", False, None, False, references_active_board, topic_changed)
