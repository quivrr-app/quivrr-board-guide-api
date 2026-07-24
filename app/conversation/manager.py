from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ConversationIntelligenceState, Fact, Goal, PendingInteraction, RecommendationStrategy, Stage, utc_now


@dataclass(frozen=True)
class TurnTransition:
    relationship: str
    clarification_resolved: bool = False
    action_confirmed: bool = False
    action_rejected: bool = False


class ConversationManager:
    """Deterministic state transitions; tools remain outside this boundary."""

    _stage_two = re.compile(r"\b(?:catch(?:ing)? green waves?|ride along the face|riding green waves?)\b", re.I)
    _challenge = re.compile(r"\b(?:wouldn['’]t|shouldn['’]t|are you sure|thought)\b.*\b(?:mid[ -]?length|fish|board|volume)\b", re.I)
    _more_volume = re.compile(r"\b(?:more volume|more foam|more stable|more glide)\b", re.I)
    _reject = re.compile(r"\b(?:too short|forget the fish|not the fish|don['’]t want (?:a )?fish)\b", re.I)
    _confirm = re.compile(r"^(?:ok(?:ay)?|yes|yep|go ahead|please do|check (?:them|it)?|do it|that works)[!. ]*$", re.I)
    _profile_confirm = re.compile(r"^(?:yes[, ]+)?(?:save|update) it[!. ]*$", re.I)
    _decline = re.compile(r"^(?:no|not now|leave it|cancel)[!. ]*$", re.I)

    def migrate_legacy(self, legacy: dict | None) -> ConversationIntelligenceState:
        legacy = legacy or {}
        state = ConversationIntelligenceState(
            active_region=legacy.get("activeRegion"),
            active_board=legacy.get("activeBoard"),
            candidate_set=list(legacy.get("lastRecommendations") or []),
            rejected_options=list(legacy.get("rejectedRecommendations") or []),
            conversation_phase=legacy.get("phase") or "DISCOVERY",
            last_decision={"previousIntent": legacy.get("lastIntent"), "migration": "legacy_v0_to_v1"},
        )
        if legacy.get("activeProfile"):
            state.rider_context = {
                key: Fact(value=value, source="CURRENT_CONVERSATION", confidence=0.7, turn=int(legacy.get("conversationTurn") or 0))
                for key, value in legacy["activeProfile"].items() if value not in (None, "", [], {})
            }
        if legacy.get("surferStage"):
            state.surfer_stage = Stage(stage=legacy["surferStage"], source="LEGACY_STATE", confidence=0.7, lockedForGoal=True)
        if legacy.get("pendingClarification"):
            state.pending_clarification = PendingInteraction(type="SURFER_STAGE", status="AWAITING_RESPONSE", question=str(legacy["pendingClarification"].get("question") or ""))
        if legacy.get("pendingAction") or legacy.get("pendingProfileUpdate"):
            proposal = legacy.get("pendingAction") or legacy.get("pendingProfileUpdate")
            state.pending_action = PendingInteraction(type="CONFIRM_PROFILE_UPDATE", status="AWAITING_CONFIRMATION", arguments=dict(proposal or {}), confirmationPolicy="EXPLICIT")
        elif legacy.get("stockCheckOffered") and legacy.get("activeRegion"):
            state.pending_action = PendingInteraction(
                type="CHECK_INVENTORY", status="AWAITING_CONFIRMATION",
                question=f"Would you like me to check {legacy['activeRegion']}?",
                arguments={"region": legacy["activeRegion"], "candidateStrategy": "legacy-current"},
                confirmationPolicy="CONTEXTUAL",
            )
        return state

    def apply_turn(self, state: ConversationIntelligenceState, message: str) -> TurnTransition:
        text = (message or "").strip()
        turn = state.state_revision + 1
        state.updated_at = utc_now()
        state.last_user_answer = {"text": text, "receivedAtTurn": turn}
        if state.pending_clarification and self._stage_two.search(text):
            state.surfer_stage = Stage(stage="STAGE_2_PROGRESSING_BEGINNER", label="Progressing beginner", confidence=.93,
                                       source="USER_CLARIFICATION", evidence=[text], resolvedAtTurn=turn, lockedForGoal=True)
            state.pending_clarification = None
            state.conversation_phase = "STRATEGY"
            state.last_decision = {"relationshipToContext": "CONTINUATION", "clarificationResolved": True}
            self._ensure_stage_two_strategy(state, turn)
            return TurnTransition("CONTINUATION", clarification_resolved=True)
        if state.pending_action and self._decline.fullmatch(text):
            state.pending_action = None
            state.last_decision = {"relationshipToContext": "REJECTION", "pendingActionRejected": True}
            return TurnTransition("REJECTION", action_rejected=True)
        if state.pending_action and self._confirm.fullmatch(text):
            if state.pending_action.type == "CONFIRM_PROFILE_UPDATE" and not self._profile_confirm.fullmatch(text):
                state.last_decision = {"relationshipToContext": "ACKNOWLEDGEMENT", "pendingActionRetained": True}
                return TurnTransition("ACKNOWLEDGEMENT")
            state.last_decision = {"relationshipToContext": "CONFIRMATION", "pendingActionConfirmed": True, "action": state.pending_action.type}
            state.pending_action = None
            return TurnTransition("CONFIRMATION", action_confirmed=True)
        if self._challenge.search(text):
            self._ensure_stage_two_strategy(state, turn, challenge=True)
            state.last_decision = {"relationshipToContext": "CHALLENGE"}
            return TurnTransition("CHALLENGE")
        if self._more_volume.search(text):
            self._ensure_stage_two_strategy(state, turn)
            state.active_recommendation.size_guidance["direction"] = "MORE_VOLUME"
            state.active_recommendation.size_guidance["reason"] = "user stated preference"
            state.last_decision = {"relationshipToContext": "REFINEMENT"}
            return TurnTransition("REFINEMENT")
        if self._reject.search(text):
            state.rejected_options.append({"type": "BOARD_FAMILY", "value": "FISH", "reason": text, "turn": turn, "scope": "ACTIVE_GOAL"})
            self._ensure_stage_two_strategy(state, turn)
            state.active_recommendation.conditional_families = [item for item in state.active_recommendation.conditional_families if item != "FORGIVING_FISH"]
            state.last_decision = {"relationshipToContext": "REJECTION"}
            return TurnTransition("REJECTION")
        state.last_decision = {"relationshipToContext": "CASUAL_CONVERSATION"}
        return TurnTransition("CASUAL_CONVERSATION")

    def _ensure_stage_two_strategy(self, state: ConversationIntelligenceState, turn: int, challenge: bool = False) -> None:
        mid_length_prioritised = bool(
            state.active_recommendation and state.active_recommendation.preferred_families
            and state.active_recommendation.preferred_families[0] == "FORGIVING_MID_LENGTH"
        )
        state.active_goal = Goal(type="FIND_BOARD", status="ACTIVE", forWhom="SELF", summary="Find a progressing-beginner transition board", updatedAtTurn=turn, confidence=.93)
        state.active_recommendation = RecommendationStrategy(
            goal="Find a progressing-beginner transition board", stage="STAGE_2_PROGRESSING_BEGINNER",
            preferredFamilies=["MINI_MAL", "FUNBOARD", "FORGIVING_MID_LENGTH", "EGG", "LARGE_STABLE_HYBRID"],
            conditionalFamilies=["FORGIVING_FISH"],
            excludedFamilies=["PERFORMANCE_FISH", "TECHNICAL_TWIN", "PERFORMANCE_DAILY_DRIVER", "PERFORMANCE_SHORTBOARD", "STEP_UP", "GUN"],
            sizeGuidance={"lengthPriority": "HIGH", "stabilityPriority": "HIGH", "glidePriority": "HIGH"},
            reasoningSummary="Prioritise glide, stability and progression before performance.", updatedAtTurn=turn,
        )
        if challenge or mid_length_prioritised:
            state.active_recommendation.preferred_families.insert(0, "FORGIVING_MID_LENGTH")
