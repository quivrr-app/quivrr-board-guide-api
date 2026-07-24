from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Fact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    value: Any
    source: Literal["CURRENT_CONVERSATION", "SAVED_PROFILE", "INFERRED", "SYSTEM"]
    confidence: float = Field(ge=0, le=1)
    turn: int = Field(ge=0)
    temporary: bool = True


class Goal(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: Literal["FIND_BOARD", "LEARN_ABOUT_BOARD", "COMPARE_BOARDS", "CHECK_BOARD_AVAILABILITY", "CHECK_REGIONAL_INVENTORY", "BUILD_QUIVER", "UPDATE_PROFILE", "LEARN_SURF_CONCEPT", "UNDERSTAND_QUIVRR", "CASUAL_CONVERSATION", "NO_ACTIVE_GOAL"] = "NO_ACTIVE_GOAL"
    status: Literal["ACTIVE", "SUSPENDED", "COMPLETED", "CANCELLED"] = "ACTIVE"
    for_whom: Literal["SELF", "OTHER"] = Field(default="SELF", alias="forWhom")
    summary: str = ""
    explicit_user_request: str = Field(default="", alias="explicitUserRequest")
    created_at_turn: int = Field(default=0, alias="createdAtTurn")
    updated_at_turn: int = Field(default=0, alias="updatedAtTurn")
    confidence: float = Field(default=0, ge=0, le=1)
    suspended_goal_id: str | None = Field(default=None, alias="suspendedGoalId")


class Stage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    stage: str | None = None
    label: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    source: str | None = None
    evidence: list[str] = Field(default_factory=list)
    resolved_at_turn: int | None = Field(default=None, alias="resolvedAtTurn")
    locked_for_goal: bool = Field(default=False, alias="lockedForGoal")


class PendingInteraction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    status: Literal["AWAITING_RESPONSE", "AWAITING_CONFIRMATION", "SUSPENDED"]
    question: str | None = None
    prompt: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    created_at_turn: int = Field(default=0, alias="createdAtTurn")
    expires_after_turns: int = Field(default=5, alias="expiresAfterTurns")
    confirmation_policy: str | None = Field(default=None, alias="confirmationPolicy")
    security_context: str | None = Field(default=None, alias="securityContext")


class RecommendationStrategy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    strategy_id: str = Field(default_factory=lambda: str(uuid4()), alias="strategyId")
    goal: str = ""
    stage: str | None = None
    preferred_families: list[str] = Field(default_factory=list, alias="preferredFamilies")
    conditional_families: list[str] = Field(default_factory=list, alias="conditionalFamilies")
    excluded_families: list[str] = Field(default_factory=list, alias="excludedFamilies")
    size_guidance: dict[str, Any] = Field(default_factory=dict, alias="sizeGuidance")
    reasoning_summary: str = Field(default="", alias="reasoningSummary")
    created_at_turn: int = Field(default=0, alias="createdAtTurn")
    updated_at_turn: int = Field(default=0, alias="updatedAtTurn")


class ConversationIntelligenceState(BaseModel):
    """The only durable source of conversational continuity (schema v1)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    conversation_id: str = Field(default_factory=lambda: str(uuid4()), alias="conversationId")
    state_revision: int = Field(default=0, ge=0, alias="stateRevision")
    created_at: str = Field(default_factory=utc_now, alias="createdAt")
    updated_at: str = Field(default_factory=utc_now, alias="updatedAt")
    identity: dict[str, Any] = Field(default_factory=dict)
    active_goal: Goal = Field(default_factory=Goal, alias="activeGoal")
    rider_context: dict[str, Fact] = Field(default_factory=dict, alias="riderContext")
    surfer_stage: Stage = Field(default_factory=Stage, alias="surferStage")
    pending_clarification: PendingInteraction | None = Field(default=None, alias="pendingClarification")
    pending_action: PendingInteraction | None = Field(default=None, alias="pendingAction")
    active_recommendation: RecommendationStrategy | None = Field(default=None, alias="activeRecommendation")
    candidate_set: list[dict[str, Any]] = Field(default_factory=list, alias="candidateSet")
    rejected_options: list[dict[str, Any]] = Field(default_factory=list, alias="rejectedOptions")
    active_board: dict[str, Any] | None = Field(default=None, alias="activeBoard")
    active_size: dict[str, Any] | None = Field(default=None, alias="activeSize")
    active_region: str | None = Field(default=None, alias="activeRegion")
    conversation_phase: str = Field(default="GREETING", alias="conversationPhase")
    last_question: dict[str, Any] | None = Field(default=None, alias="lastQuestion")
    last_user_answer: dict[str, Any] | None = Field(default=None, alias="lastUserAnswer")
    conversation_memory: dict[str, Any] = Field(default_factory=lambda: {"recentTurns": [], "summary": ""}, alias="conversationMemory")
    tool_history: list[dict[str, Any]] = Field(default_factory=list, alias="toolHistory")
    last_decision: dict[str, Any] = Field(default_factory=dict, alias="lastDecision")

    @field_validator("conversation_id")
    @classmethod
    def safe_conversation_id(cls, value: str) -> str:
        if len(value) > 64:
            raise ValueError("conversation ID is invalid")
        return value

    def safe_projection(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude={"identity", "rider_context", "conversation_memory", "tool_history"})
