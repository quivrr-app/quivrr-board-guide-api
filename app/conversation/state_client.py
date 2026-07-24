from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from .models import ConversationIntelligenceState


CONVERSATION_API_URL = os.getenv("QUIVRR_CONVERSATION_API_URL", "https://quivrr-backend-api.azurewebsites.net/api/bodhi/conversations").rstrip("/")


@dataclass(frozen=True)
class StateConflict(Exception):
    revision: int
    state: dict


class ConversationStateClient:
    def load(self, conversation_id: str, access_token: str | None, authorization: str | None) -> ConversationIntelligenceState:
        headers = {"Authorization": authorization} if authorization else {}
        if access_token:
            headers["X-Bodhi-Conversation-Token"] = access_token
        response = requests.get(f"{CONVERSATION_API_URL}/{conversation_id}", headers=headers, timeout=4)
        response.raise_for_status()
        payload = response.json()
        state = ConversationIntelligenceState.model_validate(payload["state"])
        state.state_revision = int(payload["stateRevision"])
        return state

    def persist(self, state: ConversationIntelligenceState, *, message_id: str, raw_message: str,
                response_summary: dict, access_token: str | None, authorization: str | None,
                expected_revision: int | None = None, events: list[dict] | None = None) -> tuple[int, str | None, dict]:
        headers = {"Authorization": authorization} if authorization else {}
        body = {
            "conversationId": state.conversation_id,
            "expectedRevision": state.state_revision if expected_revision is None else expected_revision,
            "messageId": message_id,
            "conversationAccessToken": access_token,
            "rawMessage": raw_message,
            "state": state.model_dump(by_alias=True),
            "responseSummary": response_summary,
            "events": events or [],
        }
        response = requests.post(CONVERSATION_API_URL, headers=headers, json=body, timeout=5)
        if response.status_code == 409:
            detail = response.json().get("detail") or {}
            raise StateConflict(int(detail.get("latestRevision") or 0), detail.get("state") or {})
        response.raise_for_status()
        payload = response.json()
        return int(payload["stateRevision"]), payload.get("conversationAccessToken"), payload
