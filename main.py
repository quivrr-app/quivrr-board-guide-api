from fastapi import FastAPI
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
from app.conversation_flow import (
    comparison_reply, enough_for_recommendations, expert_board_question_reply, find_requested_board,
    general_board_reply, graph_suggestions, greeting_reply, has_intake_signal, intake_questions, opening_message,
    is_memory_correction, partial_volume_reply, fish_advice_reply, board_family_reply,
    public_recommendations, recommendation_reply, site_help_reply, suggestions_for_board,
    volume_advice_reply, volume_guidance, everyday_pushback_reply,
)
from app.active_topic import resolve_active_topic
from app.catalogue_search import extract_category, inventory_snapshot_reply, search_live_category
from app.intent_router import route_intent
from app.board_expert_matrix import recommend_from_matrix
from app.board_relationship_graph import (
    relationship_reply, relationship_suggestions, relationship_type, source_board_from_message,
)
from app.model_recommendation_engine import build_recommendation_context, recommend_models
from app.inventory_client import enrich_suggestions_with_inventory, locate_exact_board
from app.models import BoardComparison, BoardGuideRequest, BoardGuideResponse, BoardReference
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
def board_guide_chat(request: BoardGuideRequest, response: Response, http_request: Request):
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
        correlation_id=correlation_id,
    )
    history_profiles = [with_profile_source(extract_profile(item.content, request.region), "conversation_user") for item in request.conversation if item and item.role == "user" and item.content]
    persisted_profile = with_profile_source(request.profile or request.intake_state or extract_profile(""), "conversation_profile")
    account_profile = with_profile_source(request.account_profile, "account_profile") if request.account_profile else None
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
    intent = route_intent(request.message)
    active_topic = resolve_active_topic(request, profile, intent)
    if active_topic.kind == "comparison" and active_topic.is_follow_up:
        intent = "comparison_request"
    category = extract_category(request.message, profile.preferred_board_type)
    requested_board = find_requested_board(request.message)
    if intent == "exact_board_location_request" and not requested_board:
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
        missing_field_count=len(missing),
        profile_completeness=profile_completeness(profile),
        correlation_id=correlation_id,
    )
    comparison = None

    if intent == "greeting_request":
        suggested_boards = []
        reply = greeting_reply(profile.region)
        questions = []
    elif intent == "expert_board_question":
        suggested_boards = []
        reply = expert_board_question_reply(request.message)
        questions = []
    elif intent == "exact_board_location_request" and not profile.region:
        suggested_boards = []
        reply = "I’ve got the board. Should I check Australia, Europe, or Indonesia?"
        questions = ["Which region should I search: Australia, Europe, or Indonesia?"]
    elif intent == "exact_board_location_request" and not requested_board:
        suggested_boards = []
        if "christenson fish" in request.message.lower():
            reply = "The Christenson Fish is a strong canonical point-break fish reference, but I can’t see a matching canonical model or verified live link in the selected regional inventory right now."
        else:
            reply = "Tell me the brand and model you want located, and I’ll check verified stock in that region."
        questions = []
    elif intent == "exact_board_location_request":
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
    elif intent == "volume_advice_request":
        suggested_boards = []
        reply = volume_advice_reply(profile)
        questions = []
    elif intent == "site_help_question":
        suggested_boards = []
        reply = site_help_reply(profile.region)
        questions = []
    elif intent == "general_board_question" and requested_board and "fish" in request.message.lower():
        suggested_boards = []
        reply = board_family_reply(requested_board, "fish")
        questions = []
    elif intent == "general_board_question":
        suggested_boards = []
        reply = general_board_reply(request.message)
        questions = []
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
        suggested_boards = [row for row in checked if row.available_count > 0]
        names = ", ".join(f"{row.brand} {row.model}" for row in suggested_boards)
        requested_names = ", ".join(f"{row['brand']} {row['model']}" for row in active_topic.boards)
        reply = (
            f"I checked live {profile.region} stock for {requested_names}. "
            + (f"The available matches are {names}." if suggested_boards else "I can’t verify a live match for those boards right now.")
        ) if profile.region else "Which region should I check for those boards: Australia, Europe, or Indonesia?"
        questions = []
    elif intent == "comparison_request":
        if len(active_topic.boards) >= 2:
            comparison = BoardComparison(
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
            suggested_boards = [row for row in checked if row.available_count > 0]
            reply = everyday_pushback_reply(profile.region, requested, suggested_boards)
        else:
            suggested_boards = []
            reply = comparison_reply(request.message, active_topic.boards, profile, active_topic.is_follow_up)
        questions = []
    elif intent == "relationship_request":
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
                suggested_boards = [row for row in checked if row.available_count > 0]
            else:
                suggested_boards = []
            reply = relationship_reply(source_board, relation, canonical_boards, suggested_boards, profile.region)
        questions = []
    elif intent == "inventory_count_question" and category and profile.region:
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
    elif intent == "inventory_count_question":
        suggested_boards = []
        reply = inventory_snapshot_reply(profile.region, category)
        questions = []
    elif category == "fish" and intent in {"board_search_request", "surfer_fit_request"}:
        canonical_boards = recommend_from_matrix(profile, limit=12)
        brand_stock_request = bool(profile.requested_brand and profile.region and intent == "board_search_request")
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
        elif not profile.region or (
            not (profile.wave_type or profile.wave_size or profile.wave_power)
            and not (intent == "board_search_request" and profile.target_volume_litres)
        ):
            suggested_boards = []
            reply = fish_advice_reply(profile, canonical_boards)
            questions = ["Which region should I search: Australia, Europe, or Indonesia?"] if not profile.region else ["Are your waves mostly weak beach breaks, points, or reefs?"]
        else:
            checked = enrich_suggestions_with_inventory(canonical_boards, profile)
            suggested_boards = [board for board in checked if board.available_count > 0]
            reply = fish_advice_reply(profile, canonical_boards, suggested_boards)
            questions = []
    elif intent == "board_search_request" and category and profile.region and not requested_board:
        if category in {"daily_driver", "performance_daily_driver"} and not profile.construction_preference:
            ranking_profile = profile.model_copy(update={"preferred_board_type": "Daily Driver"})
            canonical_boards = recommend_from_matrix(ranking_profile, limit=12)
            checked = enrich_suggestions_with_inventory(canonical_boards, ranking_profile)
            suggested_boards = [board for board in checked if board.available_count > 0]
            if "three" in request.message.lower() or "3" in request.message:
                suggested_boards = suggested_boards[:3]
        else:
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
    elif intent == "board_search_request" and category and not profile.region and not requested_board:
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
    elif intent == "alternative_request":
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
        reply = opening_message(profile.region)
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
        suggested_boards = [board for board in suggested_boards if board.available_count > 0]
        reply = recommendation_reply(profile, guidance, suggested_boards) if guidance else opening_message(profile.region)
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
        missing_field_count=len(missing),
        suggested_board_count=len(suggested_boards),
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
        recommendations=public_recommendations(suggested_boards),
        intent=intent,
        conversationProfile=profile,
        profileCompleteness=profile_completeness(profile),
        profileConflicts=profile.profile_conflicts,
        volumeRecommendation=volume_recommendation,
        comparison=comparison,
        usefulFollowUpQuestions=questions,
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
        missing_field_count=len(missing),
        suggested_board_count=len(suggested_boards),
        duration_seconds=duration,
        correlation_id=correlation_id,
    )
    return response
