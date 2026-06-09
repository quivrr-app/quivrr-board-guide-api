from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.azure_openai_client import ask_bodhi, build_official_recommendation_context, is_azure_openai_configured
from app.model_recommendation_engine import build_recommendation_context, recommend_models
from app.models import BoardGuideRequest, BoardGuideResponse
from app.profile_engine import (
    build_profile_reply,
    build_recommendation,
    extract_profile,
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
    profile = extract_profile(
        message=request.message,
        region=request.region,
    )

    missing = missing_profile_fields(profile)
    recommendation = build_recommendation(profile)
    suggested_boards = recommend_models(profile)
    recommendation_context = build_recommendation_context(suggested_boards)
    official_recommendation_context = build_official_recommendation_context(recommendation)

    if is_azure_openai_configured():
        reply = ask_bodhi(
            message=request.message,
            region=request.region,
            page_context=request.page_context,
            recommendation_context=recommendation_context,
            official_recommendation_context=official_recommendation_context,
        )
        source = "azure_openai"
    else:
        reply = build_profile_reply(
            profile=profile,
            missing=missing,
            recommendation=recommendation,
        )
        if suggested_boards:
            reply += "\n\nBoards worth checking in Quivrr:\n"
            for board in suggested_boards:
                reply += f"- {board.brand} {board.model}: {board.why_it_fits}\n"
        source = "local_profile_engine"

    return BoardGuideResponse(
        guide_name="Bodhi, the Core Lord",
        reply=reply,
        profile=profile,
        recommendation=recommendation,
        suggested_boards=suggested_boards,
        missing_fields=missing,
        recommended_next_step="Use the controlled board suggestions to refine Quivrr search direction. Availability will be added later through MFA and retailer inventory.",
        source=source,
    )
