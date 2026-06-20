from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.azure_openai_client import is_azure_openai_configured
from app.conversation_flow import (
    comparison_reply, enough_for_recommendations, find_requested_board, general_board_reply,
    graph_suggestions, has_intake_signal, intake_questions, opening_message,
    is_memory_correction, partial_volume_reply,
    public_recommendations, recommendation_reply, site_help_reply, suggestions_for_board,
    volume_advice_reply, volume_guidance,
)
from app.catalogue_search import extract_category, inventory_snapshot_reply, search_live_category
from app.intent_router import route_intent
from app.model_recommendation_engine import recommend_models
from app.inventory_client import enrich_suggestions_with_inventory
from app.models import BoardGuideRequest, BoardGuideResponse
from app.profile_engine import (
    build_recommendation,
    extract_profile,
    merge_profiles,
    missing_profile_fields,
)


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


@app.post("/api/board-guide/chat", response_model=BoardGuideResponse)
def board_guide_chat(request: BoardGuideRequest):
    history_profiles = [extract_profile(item.content) for item in request.conversation if item.role == "user"]
    persisted_profile = request.intake_state or extract_profile("")
    profile = merge_profiles(persisted_profile, *history_profiles, extract_profile(request.message, request.region))

    missing = missing_profile_fields(profile)
    recommendation = build_recommendation(profile)
    questions = intake_questions(profile)
    guidance = volume_guidance(profile)
    intent = route_intent(request.message)
    category = extract_category(request.message, profile.preferred_board_type)
    requested_board = find_requested_board(request.message)

    if intent == "volume_advice_request":
        suggested_boards = []
        reply = volume_advice_reply(profile)
        questions = []
    elif intent == "site_help_question":
        suggested_boards = []
        reply = site_help_reply(profile.region)
        questions = []
    elif intent == "general_board_question":
        suggested_boards = []
        reply = general_board_reply(request.message)
        questions = []
    elif intent == "comparison_request":
        suggested_boards = []
        reply = comparison_reply(request.message)
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
    elif intent == "board_search_request" and category and profile.region and not requested_board:
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
        suggested_boards = []
        reply = "Tell me the exact board model and region, and I’ll check live graph alternatives."
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
            expert_lane = recommend_models(performance_profile, limit=8)
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
            suggested_boards = recommend_models(profile)
            suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
        suggested_boards = [board for board in suggested_boards if board.available_count > 0]
        reply = recommendation_reply(profile, guidance, suggested_boards) if guidance else opening_message(profile.region)
        if questions:
            reply += " " + questions[0]
    else:
        suggested_boards = []
        reply = "Nice. " + " ".join(questions)
    source = "deterministic_intake_engine"

    return BoardGuideResponse(
        guide_name="Bodhi, the Core Lord",
        reply=reply,
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
    )
