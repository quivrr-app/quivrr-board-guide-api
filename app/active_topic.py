from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.conversation_flow import find_boards_in_message
from app.board_relationship_graph import relationship_suggestions, relationship_type, source_board_from_message
from app.models import BoardGuideRequest, RiderProfile
from app.intent_router import route_intent


@dataclass
class ActiveTopic:
    kind: str | None = None
    boards: list[dict] = field(default_factory=list)
    region: str | None = None
    weight_kg: int | None = None
    target_volume_litres: float | None = None
    ability: str | None = None
    wave_type: str | None = None
    wave_size: str | None = None
    preferred_board_type: str | None = None
    desired_feel: str | None = None
    is_follow_up: bool = False
    is_everyday_pushback: bool = False
    stock_check: bool = False
    relationship_source: dict | None = None
    relationship_type: str | None = None


def _topic(profile: RiderProfile, **values) -> ActiveTopic:
    return ActiveTopic(
        region=profile.region, weight_kg=profile.weight_kg,
        target_volume_litres=profile.target_volume_litres, ability=profile.ability,
        wave_type=profile.wave_type, wave_size=profile.wave_size,
        preferred_board_type=profile.preferred_board_type, desired_feel=profile.desired_feel,
        **values,
    )


def resolve_active_topic(request: BoardGuideRequest, profile: RiderProfile, current_intent: str) -> ActiveTopic:
    """Derive the conversational topic from the request; no persistence or API change required."""
    latest_boards = find_boards_in_message(request.message)
    text = request.message.lower()
    stock_check = bool(re.search(
        r"\b(?:yes[, ]+)?check (?:the )?stock(?: levels)?\b|\bshow availability\b|\bwhat is available\b",
        text,
    ))
    fresh_request = current_intent in {"board_search_request", "expert_board_question"} or bool(re.search(
        r"\b(?:show me|find me|search(?: for)?|give me|recommend)\b|\b(?:good|best)\s+"
        r"(?:daily drivers?|fish boards?|shortboards?)\b",
        text,
    ))
    if fresh_request and not stock_check:
        return _topic(profile, kind="board_search", boards=latest_boards)
    fresh_search = current_intent in {"exact_board_location_request", "inventory_count_question"} or bool(
        re.search(r"\b(?:fresh|new|different) (?:stock )?search\b|\bwhere can i buy\b|\bexact (?:board|location)\b", text)
    )
    if fresh_search:
        return _topic(profile, kind="board_search", boards=latest_boards)

    previous_comparison: list[dict] = []
    previous_relationship_boards: list[dict] = []
    previous_relationship_source: dict | None = None
    previous_relationship_type: str | None = None
    prior_monsta = False
    for turn in request.conversation:
        if turn.role != "user":
            continue
        prior_monsta = prior_monsta or "monsta" in turn.content.lower()
        if re.search(r"\b(?:compare|comparison|versus|vs\.?|difference between)\b", turn.content.lower()):
            found = find_boards_in_message(turn.content)
            if len(found) >= 2:
                previous_comparison = found
        relation = relationship_type(turn.content) if route_intent(turn.content) == "relationship_request" else None
        source = source_board_from_message(turn.content, profile) if relation else None
        if source and relation:
            previous_relationship_source = source
            previous_relationship_type = relation
            previous_relationship_boards = [
                {"brand": row.brand, "model": row.model}
                for row in relationship_suggestions(source, relation)
            ]

    if stock_check and previous_relationship_boards:
        return _topic(
            profile, kind="relationship", boards=previous_relationship_boards,
            relationship_source=previous_relationship_source,
            relationship_type=previous_relationship_type,
            is_follow_up=True, stock_check=True,
        )

    if stock_check and previous_comparison:
        return _topic(
            profile, kind="comparison", boards=previous_comparison,
            is_follow_up=True, stock_check=True,
        )

    if current_intent == "relationship_request":
        relation = relationship_type(request.message)
        source = source_board_from_message(request.message, profile) or previous_relationship_source
        if relation and source:
            return _topic(
                profile, kind="relationship", relationship_source=source,
                relationship_type=relation, is_follow_up=bool(previous_relationship_source),
            )

    pushback = (
        prior_monsta
        and bool(re.search(r"\b(?:too |bit )?(?:aggressive|demanding)|\beveryday\b", text))
        and any("happy" in board["model"].lower() or "gravity" in board["model"].lower() for board in latest_boards)
    )
    if pushback:
        everyday = [
            board for board in latest_boards
            if board["model"].replace("-", " ").lower() in {"happy everyday", "xero gravity"}
        ]
        return _topic(profile, kind="comparison", boards=everyday, is_follow_up=True, is_everyday_pushback=True)

    if current_intent == "comparison_request" and len(latest_boards) >= 2:
        return _topic(profile, kind="comparison", boards=latest_boards)

    enrichment = any([
        profile.weight_kg, profile.target_volume_litres, profile.region, profile.wave_type,
        profile.wave_size, profile.desired_feel,
    ]) or bool(re.search(r"\bi already told you\b", text))
    if previous_comparison and enrichment and not latest_boards:
        return _topic(profile, kind="comparison", boards=previous_comparison, is_follow_up=True)
    if previous_comparison and latest_boards and current_intent not in {"board_search_request", "relationship_request"}:
        return _topic(profile, kind="comparison", boards=latest_boards, is_follow_up=True)
    return _topic(profile, kind=None, boards=latest_boards)
