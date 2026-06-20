from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.azure_openai_client import is_azure_openai_configured
from app.conversation_flow import (
    enough_for_recommendations, find_requested_board, graph_suggestions, has_intake_signal,
    intake_questions, opening_message, public_recommendations, recommendation_reply,
    suggestions_for_board, volume_guidance,
)
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
    profile = merge_profiles(*history_profiles, extract_profile(request.message, request.region))

    missing = missing_profile_fields(profile)
    recommendation = build_recommendation(profile)
    questions = intake_questions(profile)
    guidance = volume_guidance(profile)
    requested_board = find_requested_board(request.message)
    if requested_board and profile.region:
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
    elif not has_intake_signal(profile):
        suggested_boards = []
        reply = opening_message(profile.region)
    elif enough_for_recommendations(profile):
        wants_performance = "performance" in " ".join(filter(None, [profile.desired_feel, profile.goal])).lower()
        suggested_boards = graph_suggestions(profile, "upgradeBoards") if profile.current_board and wants_performance else recommend_models(profile)
        suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
        suggested_boards = [board for board in suggested_boards if board.available_count > 0]
        reply = recommendation_reply(profile, guidance, suggested_boards) if guidance else opening_message(profile.region)
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
    )
