from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.conversation_flow import find_boards_in_message
from app.models import BoardGuideRequest, RiderProfile


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
    fresh_search = current_intent in {"exact_board_location_request", "inventory_count_question"} or bool(
        re.search(r"\b(?:fresh|new|different) (?:stock )?search\b|\bwhere can i buy\b|\bexact (?:board|location)\b", text)
    )
    if fresh_search:
        return _topic(profile, kind="board_search", boards=latest_boards)

    previous_comparison: list[dict] = []
    prior_monsta = False
    for turn in request.conversation:
        if turn.role != "user":
            continue
        prior_monsta = prior_monsta or "monsta" in turn.content.lower()
        if re.search(r"\b(?:compare|comparison|versus|vs\.?|difference between)\b", turn.content.lower()):
            found = find_boards_in_message(turn.content)
            if len(found) >= 2:
                previous_comparison = found

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
