from fastapi import FastAPI
from fastapi import Header
from fastapi import Request
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os
import time
import uuid

from app.azure_openai_client import (
    build_official_recommendation_context,
    is_azure_openai_configured,
    safe_ask_bodhi,
)
from app.authenticated_profile import load_authenticated_profile_context
from app.board_intelligence import find_board_record
from app.comparison_engine import compare_board_models
from app.conversation_flow import (
    comparison_reply, enough_for_recommendations, expert_board_question_reply, find_requested_board,
    general_board_reply, graph_suggestions, greeting_reply, has_intake_signal, intake_questions, opening_message,
    personalise_opening,
    is_memory_correction, partial_volume_reply, fish_advice_reply, board_family_reply,
    public_recommendations, recommendation_reply, site_help_reply, suggestions_for_board,
    volume_advice_reply, volume_guidance, everyday_pushback_reply,
)
from app.active_topic import resolve_active_topic
from app.catalogue_search import extract_category, inventory_snapshot_reply, search_live_category
from app.intent_router import classify_intent, route_intent
from app.board_expert_matrix import recommend_from_matrix
from app.board_relationship_graph import (
    relationship_reply, relationship_suggestions, relationship_type, source_board_from_message,
)
from app.model_recommendation_engine import build_recommendation_context, recommend_models
from app.inventory_client import enrich_suggestions_with_inventory, locate_exact_board
from app.models import BoardComparison, BoardGuideRequest, BoardGuideResponse, BoardReference, BodhiRecommendation, ConversationState, FollowUpAction, SuggestedBoard
from app.profile_engine import (
    build_recommendation,
    extract_profile,
    merge_rider_profile,
    merge_profiles,
    missing_profile_fields,
    profile_completeness,
    with_profile_source,
)
from app.volume_engine_v2 import build_volume_recommendation
from app.structured_logging import emit_event


load_dotenv()

APP_NAME = "Quivrr Board Guide API"
REGION_DISPLAY_NAMES = {
    "AU": "Australia",
    "EU": "Europe",
    "ID": "Indonesia",
    "US": "the United States",
}


def _region_display_name(value: str | None) -> str:
    return REGION_DISPLAY_NAMES.get((value or "").upper(), value or "your region")


def _state_cards(request: BoardGuideRequest):
    if not request.conversation_state:
        return []
    return [_normalise_active_recommendation(card) for card in request.conversation_state.last_recommendations or []]


def _state_card_index(message: str) -> int | None:
    import re
    lowered = message.lower()
    ordinals = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
        "sixth": 5,
        "top one": 0,
    }
    match = re.search(r"\b(?:number|#)\s*(\d+)\b", lowered)
    if match:
        return max(int(match.group(1)) - 1, 0)
    for token, index in ordinals.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return index
    return None


def _state_card_pair(message: str) -> tuple[int, int] | None:
    import re
    lowered = message.lower()
    ordinal_number = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
    }
    match = re.search(r"\bcompare\s+(?:number\s+)?(\d+)\s+(?:and|&)\s+(?:number\s+)?(\d+)\b", lowered)
    if match:
        return max(int(match.group(1)) - 1, 0), max(int(match.group(2)) - 1, 0)
    match = re.search(r"\bcompare\s+(?:the\s+)?(first|second|third|fourth|fifth|sixth)\s+(?:and|&)\s+(?:the\s+)?(first|second|third|fourth|fifth|sixth)\b", lowered)
    if match:
        return ordinal_number[match.group(1)] - 1, ordinal_number[match.group(2)] - 1
    if "top two" in lowered:
        return 0, 1
    return None


def _requested_card_limit(message: str) -> int | None:
    import re

    lowered = message.lower()
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
    }
    if match := re.search(r"\b([1-6])\b", lowered):
        return int(match.group(1))
    for word, value in number_words.items():
        if re.search(rf"\b{word}\b", lowered):
            return value
    return None


def _card_to_requested_board(card):
    return {"brand": card.brand, "model": card.model}


def _normalise_active_recommendation(card) -> BodhiRecommendation:
    if isinstance(card, BodhiRecommendation):
        return card
    if isinstance(card, SuggestedBoard):
        return public_recommendations([card])[0]
    if isinstance(card, dict):
        return BodhiRecommendation.model_validate(card)
    raise TypeError(f"Unsupported active recommendation record: {type(card)!r}")


def _card_to_suggested_board(card) -> SuggestedBoard:
    card = _normalise_active_recommendation(card)
    return SuggestedBoard(
        brand=card.brand,
        model=card.model,
        category=card.category,
        confidence=card.confidence,
        why_it_fits=card.short_reason or card.why_it_fits,
        region=card.region,
        region_code=card.region_code,
        quivrr_search_url=card.search_url or card.quivrr_search_url,
        available_count=card.available_count,
        manufacturer_direct_count=card.manufacturer_match_count,
        retailer_count=card.retailer_match_count,
        availability_checked=card.availability_checked,
        availability_status=card.availability_status,
        inventory_source=card.inventory_source,
        inventory_match_count=card.inventory_match_count,
    )


def _detail_reply(card) -> str:
    record = find_board_record(card.brand, card.model)
    if not record:
        return (
            f"{card.brand} {card.model} sits in the {card.category.lower()} lane. "
            f"It suits this brief because {card.short_reason or card.why_it_fits}. "
            "Want the design details, sizing guidance, similar boards, or availability?"
        )
    what_it_is = f"{record.brand} {record.model} is a {record.category or card.category}."
    conditions = f"Best in {', '.join(record.wave_types[:2])} waves." if record.wave_types else "Best when you want a clean fit for the same brief."
    feel = f"It tends to feel {', '.join(record.feel_tags[:3])}." if record.feel_tags else f"It should feel {card.short_reason or card.why_it_fits}."
    rider = f"It suits {', '.join(record.ability_tags[:2])} surfers." if record.ability_tags else "It suits the rider profile we have so far."
    trade_off = f"The main trade-off is {record.trade_offs[0]}." if record.trade_offs else "The main trade-off is that it stays specific to its lane."
    return " ".join([what_it_is, conditions, feel, rider, trade_off, "Want the design details, sizing guidance, similar boards, or availability?"])


def _best_paddler_reply(cards) -> str:
    scored = []
    for card in cards:
        record = find_board_record(card.brand, card.model)
        paddle = 0
        if record:
            paddle = record.design_scores.get("paddle") or record.design_scores.get("paddle_power") or 0
        scored.append((paddle, card))
    scored.sort(key=lambda item: (-item[0], item[1].brand.lower(), item[1].model.lower()))
    best = scored[0][1]
    return (
        f"Within this active shortlist, {best.brand} {best.model} looks like the strongest paddler. "
        "If you want, I can rank the rest of the set for paddle help, weak-wave speed, or forgiveness."
    )


def _comparison_follow_up_reply(left_card, right_card, profile: BoardGuideRequest | None = None):
    result = compare_board_models(left_card.brand, left_card.model, right_card.brand, right_card.model, profile)
    if not result:
        return f"{left_card.brand} {left_card.model} and {right_card.brand} {right_card.model} are the two boards in play. Want me to break down paddle power, forgiveness, or weak-wave performance?"
    left = result.left_fit.board if result.left_fit else None
    right = result.right_fit.board if result.right_fit else None
    paddle_winner = None
    if left and right:
        left_paddle = left.design_scores.get("paddle") or left.design_scores.get("paddle_power") or 0
        right_paddle = right.design_scores.get("paddle") or right.design_scores.get("paddle_power") or 0
        if left_paddle > right_paddle:
            paddle_winner = f"{left.brand} {left.model} has the stronger paddle bias."
        elif right_paddle > left_paddle:
            paddle_winner = f"{right.brand} {right.model} has the stronger paddle bias."
    parts = [
        f"Comparing {left_card.brand} {left_card.model} and {right_card.brand} {right_card.model}.",
        f"Paddle power: {paddle_winner or 'They are close, but the more forgiving board usually wins on easier entry.'}",
        f"Speed: {result.comparison.differences[0] if result.comparison.differences else 'They split speed differently through their lanes.'}",
        f"Forgiveness: {result.comparison.better_for_board_a[0] if result.comparison.better_for_board_a else result.comparison.better_for_board_b[0] if result.comparison.better_for_board_b else 'The easier board is the one that asks less of your positioning.'}",
        f"Main trade-off: {result.comparison.rider_specific_conclusion or 'One is cleaner for this rider brief.'}",
    ]
    return " ".join(parts)


def _handle_state_follow_up(request: BoardGuideRequest, profile):
    message = request.message.strip()
    lowered = message.lower()
    cards = _state_cards(request)
    if not cards:
        return None

    index = _state_card_index(message)
    if index is not None and index >= len(cards):
        return {
            "reply": f"I only have {len(cards)} boards in the current shortlist. Pick 1 to {len(cards)}.",
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }
    if index is not None and 0 <= index < len(cards) and ("tell me about" in lowered or "what is" in lowered):
        return {"reply": _detail_reply(cards[index]), "suggested_boards": [], "comparison": None, "questions": []}

    pair = _state_card_pair(message)
    if pair and (pair[0] >= len(cards) or pair[1] >= len(cards)):
        return {
            "reply": f"I only have {len(cards)} boards in the current shortlist. Pick 1 to {len(cards)}.",
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }
    if pair and pair[0] < len(cards) and pair[1] < len(cards):
        left_card = cards[pair[0]]
        right_card = cards[pair[1]]
        comparison = compare_board_models(left_card.brand, left_card.model, right_card.brand, right_card.model, profile)
        reply = _comparison_follow_up_reply(left_card, right_card, profile)
        return {
            "reply": reply,
            "suggested_boards": [],
            "comparison": comparison.comparison if comparison else None,
            "questions": [],
            "comparison_boards": [left_card, right_card],
        }

    if any(token in lowered for token in ("which paddles best", "which one paddles best")) and len(cards) >= 2:
        if request.conversation_state and len(request.conversation_state.comparison_boards) >= 2:
            left_card = request.conversation_state.comparison_boards[0]
            right_card = request.conversation_state.comparison_boards[1]
            return {
                "reply": _comparison_follow_up_reply(left_card, right_card, profile),
                "suggested_boards": [],
                "comparison": None,
                "questions": [],
                "comparison_boards": [left_card, right_card],
            }
        return {
            "reply": _best_paddler_reply(cards),
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }

    if "remove pyzel" in lowered:
        remaining = [_card_to_suggested_board(card) for card in cards if card.brand.lower() != "pyzel"]
        reply = "I’ve taken Pyzel out of the active set." if remaining else "Taking Pyzel out leaves no active boards in this set."
        return {"reply": reply, "suggested_boards": remaining, "comparison": None, "questions": []}

    if "only show" in lowered and ("available" in lowered or "in stock" in lowered):
        target_region = profile.region or request.region
        verified = [_card_to_suggested_board(card) for card in cards]
        inventory_profile = profile if profile.region else profile.model_copy(update={"region": target_region})
        checked = enrich_suggestions_with_inventory(verified, inventory_profile) if target_region and verified else []
        filtered = [row for row in checked if row.available_count > 0]
        region_name = _region_display_name(target_region)
        reply = (
            f"I filtered the active set to boards with verified current availability in {region_name}."
            if filtered else
            f"I couldn’t verify live {region_name} stock for those boards right now. I can keep the best-fitting catalogue options or search a wider set of boards currently in stock."
        )
        return {"reply": reply, "suggested_boards": filtered, "comparison": None, "questions": []}

    return None


def build_follow_up_actions(intent: str, boards: list) -> list[FollowUpAction]:
    if intent == "BOARD_RECOMMENDATION" and boards:
        top_two = boards[:2]
        labels = [
            FollowUpAction(id="compare_top_two", label="Compare top two", prompt=f"Compare {top_two[0].brand} {top_two[0].model} and {top_two[1].brand} {top_two[1].model}") if len(top_two) >= 2 else None,
            FollowUpAction(id="only_in_stock", label="Only in stock", prompt="Only show the ones in stock"),
            FollowUpAction(id="more_paddle", label="More paddle power", prompt="Show me the ones with more paddle power"),
            FollowUpAction(id="details_first", label="Tell me more", prompt=f"Tell me about {boards[0].brand} {boards[0].model}"),
        ]
        return [item for item in labels if item is not None]
    if intent == "BOARD_COMPARISON":
        return [
            FollowUpAction(id="paddle_best", label="Which paddles best?", prompt="Which one paddles best?"),
            FollowUpAction(id="more_forgiving", label="Which is more forgiving?", prompt="Which one is more forgiving?"),
        ]
    if intent == "AVAILABILITY":
        return [FollowUpAction(id="open_region_search", label="Open region search", prompt="Show me similar boards in this region")]
    return []


def build_conversation_state(
    request: BoardGuideRequest,
    profile,
    normalized_intent: str,
    public_cards: list,
    questions: list[str],
    comparison_boards_override: list | None = None,
) -> ConversationState:
    active_region = profile.region or request.region
    last_question = questions[0] if questions else None
    previous_state = request.conversation_state
    previous_turn = previous_state.conversation_turn if previous_state else 0
    previous_recommendations = previous_state.last_recommendations if previous_state else []
    mentioned = previous_state.mentioned_boards if previous_state else []
    comparison_boards = previous_state.comparison_boards if previous_state else []
    if comparison_boards_override:
        comparison_boards = [_normalise_active_recommendation(card) for card in comparison_boards_override]
    if normalized_intent == "BOARD_COMPARISON" and len(public_cards) >= 2:
        comparison_boards = public_cards[:2]
    last_recommendations = public_cards[:6] or previous_recommendations[:6]
    return ConversationState(
        lastIntent=normalized_intent,
        activeRegion=active_region,
        activeProfile=profile.model_dump(exclude={"profile_sources", "profile_conflicts", "field_provenance"}, exclude_none=True),
        lastRecommendations=last_recommendations,
        mentionedBoards=(last_recommendations or mentioned[:8]),
        comparisonBoards=comparison_boards[:4],
        lastQuestion=last_question,
        conversationTurn=previous_turn + 1,
    )


def get_allowed_origins() -> list[str]:
    origins = os.getenv("BOARD_GUIDE_ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins() or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "persona": "Bodhi, the Core Lord",
        "azure_openai_configured": is_azure_openai_configured(),
        "stage2_model_recommendations": True,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    if request.url.path == "/api/board-guide/chat":
        emit_event(
            "bodhi_recommendation_failed",
            "bodhi_api",
            status="failed",
            source="deterministic_intake_engine",
            correlation_id=correlation_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers={"X-Correlation-ID": correlation_id})


@app.post("/api/board-guide/chat", response_model=BoardGuideResponse)
def board_guide_chat(
    request: BoardGuideRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
):
    started = time.perf_counter()
    correlation_id = http_request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    http_request.state.correlation_id = correlation_id
    response.headers["X-Correlation-ID"] = correlation_id
    emit_event(
        "bodhi_request_received",
        "bodhi_api",
        region=request.region,
        status="success",
        source="deterministic_intake_engine",
        conversation_turn_count=len(request.conversation),
        authenticated=bool(authorization),
        correlation_id=correlation_id,
    )
    auth_context = load_authenticated_profile_context(authorization, correlation_id=correlation_id)
    history_profiles = [with_profile_source(extract_profile(item.content, request.region), "conversation_user") for item in request.conversation if item and item.role == "user" and item.content]
    legacy_account_profile = with_profile_source(request.account_profile, "conversation_profile") if request.account_profile else None
    persisted_profile = with_profile_source(request.profile or request.intake_state or extract_profile(""), "conversation_profile")
    if legacy_account_profile:
        persisted_profile = merge_rider_profile(legacy_account_profile, persisted_profile)
    account_profile = auth_context.profile if auth_context.profile else None
    profile = account_profile or extract_profile("")
    for historical in history_profiles:
        profile = merge_rider_profile(profile, historical)
    profile = merge_rider_profile(profile, persisted_profile, account_profile=account_profile)
    current_profile = with_profile_source(extract_profile(request.message, request.region), "current_user")
    profile = merge_rider_profile(profile, current_profile, account_profile=account_profile)

    missing = missing_profile_fields(profile)
    recommendation = build_recommendation(profile)
    volume_recommendation = build_volume_recommendation(profile)
    questions = intake_questions(profile)
    guidance = volume_guidance(profile)
    intent_result = classify_intent(request.message)
    legacy_intent = intent_result.legacy_intent
    intent = intent_result.intent
    active_topic = resolve_active_topic(request, profile, legacy_intent)
    if active_topic.kind == "comparison" and active_topic.is_follow_up:
        legacy_intent = "comparison_request"
        intent = "BOARD_COMPARISON"
    category = extract_category(request.message, profile.preferred_board_type)
    requested_board = find_requested_board(request.message)
    if legacy_intent == "exact_board_location_request" and not requested_board:
        for item in reversed(request.conversation):
            if item.role == "user":
                requested_board = find_requested_board(item.content)
                if requested_board:
                    break
    emit_event(
        "bodhi_profile_extracted",
        "bodhi_api",
        region=profile.region or request.region,
        status="success",
        source="deterministic_intake_engine",
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        profile_fields_used=sorted(
            field for field, value in profile.model_dump().items()
            if field not in {"profile_sources", "profile_conflicts", "field_provenance"} and value not in (None, "", [], {})
        ),
        missing_field_count=len(missing),
        profile_completeness=profile_completeness(profile),
        correlation_id=correlation_id,
    )
    comparison = None
    comparison_boards_override = None
    is_first_turn = not any(item.role == "assistant" for item in request.conversation if item)
    state_follow_up = _handle_state_follow_up(request, profile)
    asks_name = request.message.strip().lower() in {"what's my name?", "what's my name", "whats my name?", "whats my name"}

    if asks_name:
        suggested_boards = []
        if auth_context.profile_loaded and profile.display_name:
            reply = f"You're {profile.display_name}."
        else:
            reply = "I don’t have a verified saved identity for this conversation yet."
        questions = []
    elif state_follow_up:
        suggested_boards = state_follow_up.get("suggested_boards", [])
        comparison = state_follow_up.get("comparison")
        comparison_boards_override = state_follow_up.get("comparison_boards")
        reply = state_follow_up["reply"]
        questions = state_follow_up.get("questions", [])
    elif legacy_intent == "greeting_request":
        suggested_boards = []
        reply = personalise_opening(greeting_reply(profile.region), profile, is_first_turn=is_first_turn)
        questions = []
    elif legacy_intent == "capability_help_request":
        suggested_boards = []
        reply = (
            "I can help you choose a board, compare models, understand design features, check regional availability, "
            "review your quiver, work through volume and sizing, or figure out what will help your surfing progress. "
            "What are we looking at today?"
        )
        questions = []
    elif legacy_intent == "site_help_question":
        suggested_boards = []
        reply = site_help_reply(profile.region)
        questions = []
    elif legacy_intent == "expert_board_question":
        suggested_boards = []
        reply = expert_board_question_reply(request.message)
        questions = []
    elif legacy_intent == "exact_board_location_request" and not profile.region:
        suggested_boards = []
        reply = "I’ve got the board. Should I check Australia, Europe, or Indonesia?"
        questions = ["Which region should I search: Australia, Europe, or Indonesia?"]
    elif legacy_intent == "exact_board_location_request" and not requested_board:
        suggested_boards = []
        if "christenson fish" in request.message.lower():
            reply = "The Christenson Fish is a strong canonical point-break fish reference, but I can’t see a matching canonical model or verified live link in the selected regional inventory right now."
        else:
            reply = "Tell me the brand and model you want located, and I’ll check verified stock in that region."
        questions = []
    elif legacy_intent == "exact_board_location_request":
        base = suggestions_for_board(requested_board)[:1]
        suggested_boards, exact = locate_exact_board(base[0], profile) if base else ([], False)
        if suggested_boards:
            source_names = []
            if any(board.manufacturer_direct_count for board in suggested_boards):
                source_names.append("manufacturer-direct")
            if any(board.retailer_count for board in suggested_boards):
                source_names.append("retailer")
            reply = (
                f"I found {len(suggested_boards)} {'exact' if exact else 'close'} verified {profile.region} match(es) "
                f"for {requested_board['brand']} {requested_board['model']} across {' and '.join(source_names)} stock."
            )
        else:
            reply = (
                f"I can’t see that exact {requested_board['brand']} {requested_board['model']} in {profile.region} right now. "
                "I haven’t invented a substitute link."
            )
        questions = []
    elif legacy_intent == "volume_advice_request":
        suggested_boards = []
        reply = volume_advice_reply(profile)
        questions = []
    elif legacy_intent == "general_board_question" and requested_board and "fish" in request.message.lower():
        suggested_boards = []
        reply = board_family_reply(requested_board, "fish")
        questions = []
    elif legacy_intent == "general_board_question":
        suggested_boards = []
        reply = general_board_reply(request.message)
        questions = []
    elif (
        legacy_intent == "board_search_request"
        and profile.target_volume_litres
        and not profile.weight_kg
        and not (category == "fish" and profile.region)
        and "stock" not in request.message.lower()
        and "available" not in request.message.lower()
    ):
        suggested_boards = []
        reply = (
            f"I can work around {profile.target_volume_litres:g}L, but I still need your weight before I treat that as a real fit target. "
            "Give me your rough weight and I’ll tighten the range properly."
        )
        questions = ["Roughly how much do you weigh?"]
    elif active_topic.stock_check:
        if active_topic.kind == "relationship" and active_topic.relationship_source and active_topic.relationship_type:
            canonical = relationship_suggestions(
                active_topic.relationship_source, active_topic.relationship_type, profile=profile,
            )
        else:
            canonical = []
            for board in active_topic.boards:
                matches = suggestions_for_board(board)
                if matches:
                    canonical.append(matches[0])
        stock_profile = profile
        if active_topic.kind == "relationship" and profile.current_volume_litres and not profile.target_volume_litres:
            offset = 1.5 if active_topic.relationship_type in {"moreForgivingBoards", "morePaddleBoards", "stepDownFromBoards"} else 0
            stock_profile = profile.model_copy(update={"target_volume_litres": profile.current_volume_litres + offset})
        checked = enrich_suggestions_with_inventory(canonical, stock_profile) if profile.region else []
        suggested_boards = checked
        available = [row for row in suggested_boards if row.available_count > 0]
        names = ", ".join(f"{row.brand} {row.model}" for row in available)
        requested_names = ", ".join(f"{row['brand']} {row['model']}" for row in active_topic.boards)
        reply = (
            f"I checked live {profile.region} stock for {requested_names}. "
            + (f"The available matches are {names}." if available else "I can’t verify a live match for those boards right now.")
        ) if profile.region else "Which region should I check for those boards: Australia, Europe, or Indonesia?"
        questions = []
    elif legacy_intent == "comparison_request":
        if len(active_topic.boards) >= 2:
            engine_comparison = compare_board_models(
                active_topic.boards[0]["brand"],
                active_topic.boards[0]["model"],
                active_topic.boards[1]["brand"],
                active_topic.boards[1]["model"],
                profile,
            )
            comparison = engine_comparison.comparison if engine_comparison else BoardComparison(
                board_a=BoardReference(brand=active_topic.boards[0]["brand"], model=active_topic.boards[0]["model"]),
                board_b=BoardReference(brand=active_topic.boards[1]["brand"], model=active_topic.boards[1]["model"]),
                similarities=[],
                differences=[],
                better_for_board_a=[],
                better_for_board_b=[],
                rider_specific_conclusion=None,
                evidence_confidence=0.75,
            )
        if active_topic.is_everyday_pushback:
            requested = active_topic.boards[:]
            phantom = find_requested_board("Pyzel Phantom")
            if phantom and not any(row["brand"] == "Pyzel" and row["model"] == "Phantom" for row in requested):
                requested.append(phantom)
            canonical = [suggestions_for_board(row)[0] for row in requested if suggestions_for_board(row)]
            checked = enrich_suggestions_with_inventory(canonical, profile) if profile.region else []
            suggested_boards = checked
            reply = everyday_pushback_reply(profile.region, requested, suggested_boards)
        else:
            suggested_boards = []
            reply = comparison_reply(request.message, active_topic.boards, profile, active_topic.is_follow_up)
        questions = []
    elif legacy_intent == "relationship_request":
        source_board = active_topic.relationship_source or source_board_from_message(request.message, profile)
        relation = active_topic.relationship_type or relationship_type(request.message)
        if not source_board or not relation:
            suggested_boards = []
            reply = "Tell me the source board and whether you want something sharper, more forgiving, or better for particular waves."
        else:
            canonical_boards = relationship_suggestions(source_board, relation, profile=profile)
            inventory_profile = profile
            if profile.current_volume_litres and not profile.target_volume_litres:
                offset = 1.5 if relation in {"moreForgivingBoards", "morePaddleBoards", "stepDownFromBoards"} else 0
                inventory_profile = profile.model_copy(update={"target_volume_litres": profile.current_volume_litres + offset})
            if profile.region:
                checked = enrich_suggestions_with_inventory(canonical_boards, inventory_profile)
                suggested_boards = checked
            else:
                suggested_boards = []
            reply = relationship_reply(source_board, relation, canonical_boards, suggested_boards, profile.region)
        questions = []
    elif legacy_intent == "inventory_count_question" and category and profile.region:
        suggested_boards = search_live_category(profile, category)
        count = sum(board.available_count for board in suggested_boards)
        models = len(suggested_boards)
        label = category.replace("_", " ")
        target = f" around {profile.target_volume_litres:g}L" if profile.target_volume_litres else ""
        if suggested_boards:
            brands = ", ".join(dict.fromkeys(board.brand for board in suggested_boards))
            reply = (
                f"I found {count} verified live {label} or {label}-style listings{target} in {profile.region}, "
                f"grouped across {models} matching models. Live stock exists from {brands}. "
                "Want to narrow that by ability, waves, brand, or manufacturer-direct versus retailer stock?"
            )
        else:
            reply = f"I can’t verify any live {label} listings{target} in {profile.region} right now."
        questions = []
    elif legacy_intent == "inventory_count_question":
        suggested_boards = []
        reply = inventory_snapshot_reply(profile.region, category)
        questions = []
    elif category == "fish" and legacy_intent in {"board_search_request", "surfer_fit_request"}:
        canonical_boards = recommend_from_matrix(profile, limit=12)
        if not canonical_boards and profile.region:
            canonical_boards = search_live_category(profile, category)
        brand_stock_request = bool(profile.requested_brand and profile.region and legacy_intent == "board_search_request")
        direct_stock_request = bool(
            profile.region
            and legacy_intent == "board_search_request"
            and profile.target_volume_litres
            and not profile.weight_kg
            and any(token in request.message.lower() for token in ("stock", "in stock", "available now", "available"))
        )
        if brand_stock_request:
            checked = enrich_suggestions_with_inventory(canonical_boards, profile)
            suggested_boards = [board for board in checked if board.available_count > 0]
            if suggested_boards:
                reply = f"I found verified {profile.region} fish stock from {profile.requested_brand}: " + ", ".join(f"{row.model}" for row in suggested_boards[:5]) + "."
            else:
                alternative_profile = profile.model_copy(update={"requested_brand": None})
                alternatives = recommend_from_matrix(alternative_profile, limit=8)
                checked_alternatives = enrich_suggestions_with_inventory(alternatives, alternative_profile)
                suggested_boards = [board for board in checked_alternatives if board.available_count > 0]
                reply = f"I can’t see verified live {profile.region} fish stock from {profile.requested_brand} right now. "
                if suggested_boards:
                    reply += "The closest live fish alternatives are " + ", ".join(f"{row.brand} {row.model}" for row in suggested_boards[:5]) + "."
            questions = []
        elif direct_stock_request:
            checked = enrich_suggestions_with_inventory(canonical_boards, profile)
            suggested_boards = [board for board in checked if board.available_count > 0]
            reply = (
                f"I checked live {profile.region} fish stock around {profile.target_volume_litres:g}L. "
                "Here are the strongest live options before we fine-tune rider fit."
            ) if suggested_boards else (
                f"I can’t verify live fish stock around {profile.target_volume_litres:g}L in {profile.region} right now."
            )
            questions = []
        elif not profile.region or (
            not (profile.wave_type or profile.wave_size or profile.wave_power)
            and not (legacy_intent == "board_search_request" and profile.target_volume_litres)
        ):
            suggested_boards = []
            reply = fish_advice_reply(profile, canonical_boards)
            questions = ["Which region should I search: Australia, Europe, or Indonesia?"] if not profile.region else ["Are your waves mostly weak beach breaks, points, or reefs?"]
        else:
            checked = enrich_suggestions_with_inventory(canonical_boards, profile)
            suggested_boards = checked
            reply = fish_advice_reply(profile, canonical_boards, suggested_boards)
            questions = []
    elif legacy_intent == "board_search_request" and category and profile.region and not requested_board:
        if category in {"daily_driver", "performance_daily_driver"} and not profile.construction_preference:
            ranking_profile = profile.model_copy(update={"preferred_board_type": "Daily Driver"})
            canonical_boards = recommend_from_matrix(ranking_profile, limit=12)
            checked = enrich_suggestions_with_inventory(canonical_boards, ranking_profile)
            requested_stock = any(token in request.message.lower() for token in ("stock", "in stock", "available now", "available"))
            suggested_boards = [board for board in checked if board.available_count > 0] if requested_stock else checked
            if requested_limit := _requested_card_limit(request.message):
                suggested_boards = suggested_boards[:requested_limit]
        else:
            suggested_boards = search_live_category(profile, category)
        if not suggested_boards and profile.target_volume_litres:
            suggested_boards = search_live_category(profile, category)
        label = category.replace("_", " ")
        target = f" around {profile.target_volume_litres:g}L" if profile.target_volume_litres else ""
        if suggested_boards:
            count = sum(board.available_count for board in suggested_boards)
            brands = ", ".join(dict.fromkeys(board.brand for board in suggested_boards))
            construction_note = ""
            if profile.construction_preference:
                exact = sum("matches your carbon/epoxy" in board.why_it_fits for board in suggested_boards)
                construction_note = (
                    f" {exact} model group(s) match the requested carbon/epoxy construction."
                    + (" I found a few close non-carbon/epoxy options too." if exact < len(suggested_boards) else "")
                )
            reply = (
                f"I found {count} verified live {label} or {label}-style listings{target} in {profile.region}. "
                f"The live brand groups are {brands}.{construction_note} Here are the strongest matching models. "
                "Want me to narrow them by ability, waves, brand, or how forgiving you want the board to feel?"
            )
        else:
            reply = (
                f"I can’t verify a live {label} option{target} in {profile.region} right now. "
                "Tell me whether you want more paddle help, performance, or small-wave speed and I’ll check the closest category."
            )
        questions = []
    elif legacy_intent == "board_search_request" and category and not profile.region and not requested_board:
        suggested_boards = []
        reply = "I’ve got the board type and litres. Should I search Australia, Europe, or Indonesia?"
        questions = ["Which region should I search: Australia, Europe, or Indonesia?"]
    elif requested_board and profile.region:
        requested = enrich_suggestions_with_inventory(suggestions_for_board(requested_board), profile)
        if requested and requested[0].available_count:
            suggested_boards = requested
            reply = (
                f"I found {requested[0].available_count} live {requested_board['brand']} {requested_board['model']} "
                f"result(s) in {requested[0].region}."
            )
        else:
            alternatives = suggestions_for_board(requested_board, ["similarBoards", "alternativeBoards"])
            alternatives = enrich_suggestions_with_inventory(alternatives, profile)
            suggested_boards = [board for board in alternatives if board.available_count > 0]
            if suggested_boards:
                names = ", ".join(f"{board.brand} {board.model}" for board in suggested_boards[:3])
                reply = (
                    f"I can’t find a {requested_board['brand']} {requested_board['model']} available in "
                    f"{requested[0].region if requested else profile.region} right now. The closest live alternatives "
                    f"I’d check are {names}; they come from the same canonical board lane and similar design profile."
                )
            else:
                reply = (
                    f"I can’t verify a {requested_board['brand']} {requested_board['model']} or a controlled live "
                    f"alternative in {requested[0].region if requested else profile.region} right now."
                )
    elif legacy_intent == "alternative_request":
        if requested_board:
            suggested_boards = suggestions_for_board(requested_board, ["similarBoards", "alternativeBoards"])
            names = ", ".join(f"{board.brand} {board.model}" for board in suggested_boards[:4])
            reply = f"Boards in the closest canonical design lanes to {requested_board['brand']} {requested_board['model']} include {names}. Tell me a region only if you want verified stock."
        else:
            suggested_boards = []
            reply = "Tell me the exact board model and I’ll compare its canonical design lane with similar boards."
        questions = []
    elif not has_intake_signal(profile):
        suggested_boards = []
        reply = personalise_opening(opening_message(profile.region), profile, is_first_turn=is_first_turn)
    elif profile.weight_kg and profile.ability and not (profile.wave_size or profile.wave_type or profile.wave_power):
        suggested_boards = []
        reply = partial_volume_reply(profile, acknowledge_memory=is_memory_correction(request.message))
        questions = ["What size waves are you mostly surfing?"]
    elif enough_for_recommendations(profile):
        wants_performance = "performance" in " ".join(filter(None, [profile.desired_feel, profile.goal])).lower()
        if profile.current_board and wants_performance:
            performance_profile = profile.model_copy(update={"preferred_board_type": "Daily Driver"})
            expert_lane = recommend_from_matrix(performance_profile, limit=8)
            graph_lane = graph_suggestions(profile, "upgradeBoards")
            seen = set()
            suggested_boards = []
            for board in expert_lane + graph_lane:
                key = (board.brand.lower(), board.model.lower())
                if key not in seen:
                    suggested_boards.append(board)
                    seen.add(key)
            suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
        else:
            suggested_boards = recommend_from_matrix(profile)
            suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
        reply = recommendation_reply(profile, guidance, suggested_boards) if guidance else opening_message(profile.region)
        reply = personalise_opening(reply, profile, is_first_turn=is_first_turn)
        if questions:
            reply += " " + questions[0]
    else:
        suggested_boards = []
        reply = "Nice. " + " ".join(questions)
    source = "deterministic_intake_engine"
    duration = round(time.perf_counter() - started, 3)
    emit_event(
        "bodhi_recommendation_generated",
        "bodhi_api",
        region=profile.region or request.region,
        status="success",
        source=source,
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        intent=intent,
        intent_confidence=intent_result.confidence,
        conversation_turn=(request.conversation_state.conversation_turn + 1) if request.conversation_state else 1,
        missing_field_count=len(missing),
        suggested_board_count=len(suggested_boards),
        recommendation_count=len(suggested_boards),
        recommendation_brands=list(dict.fromkeys(board.brand for board in suggested_boards[:6])),
        availability_check_count=sum(1 for board in suggested_boards if board.availability_checked),
        recommendation_source="authenticated_profile" if auth_context.profile_loaded else "conversation_only",
        duration_seconds=duration,
        top_recommendation=(f"{suggested_boards[0].brand} {suggested_boards[0].model}" if suggested_boards else None),
        correlation_id=correlation_id,
    )
    llm_reply, model_deployment = safe_ask_bodhi(
        message=request.message,
        region=profile.region,
        page_context=request.page_context,
        recommendation_context=build_recommendation_context(suggested_boards),
        official_recommendation_context=build_official_recommendation_context(recommendation),
    )
    final_reply = llm_reply or reply
    public_cards = public_recommendations(suggested_boards)
    conversation_state = build_conversation_state(
        request,
        profile,
        intent,
        public_cards,
        questions,
        comparison_boards_override=comparison_boards_override,
    )
    follow_up_actions = build_follow_up_actions(intent, public_cards)
    response = BoardGuideResponse(
        guide_name="Bodhi, the Core Lord",
        reply=final_reply,
        profile=profile,
        recommendation=recommendation,
        suggested_boards=suggested_boards,
        missing_fields=missing,
        recommended_next_step="Refine the fit, then open a verified live source in the selected region. If none is available, try the closest controlled alternative.",
        source=source,
        intakeState=profile,
        missingQuestions=questions,
        volumeGuidance=guidance,
        recommendations=public_cards,
        intent=legacy_intent,
        normalizedIntent=intent,
        legacyIntent=legacy_intent,
        intentConfidence=intent_result.confidence,
        intentEntities=intent_result.entities,
        needsClarification=intent_result.needs_clarification,
        conversationProfile=profile,
        conversationState=conversation_state,
        profileCompleteness=profile_completeness(profile),
        profileConflicts=profile.profile_conflicts,
        volumeRecommendation=volume_recommendation,
        comparison=comparison,
        usefulFollowUpQuestions=questions,
        followUpActions=follow_up_actions,
        authenticated=auth_context.authenticated,
        profileLoaded=auth_context.profile_loaded,
        modelDeployment=model_deployment,
        recommendationVersion="bodhi-sprint-4",
        correlationId=correlation_id,
    )
    emit_event(
        "bodhi_response_completed",
        "bodhi_api",
        region=profile.region or request.region,
        status="success",
        source=source,
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        intent=intent,
        intent_confidence=intent_result.confidence,
        conversation_turn=conversation_state.conversation_turn if conversation_state else 0,
        missing_field_count=len(missing),
        suggested_board_count=len(suggested_boards),
        duration_seconds=duration,
        correlation_id=correlation_id,
    )
    return response
