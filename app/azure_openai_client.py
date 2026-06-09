import os
from openai import AzureOpenAI

from app.models import BoardRecommendation
from app.prompts import BODHI_SYSTEM_PROMPT
from app.text_cleaning import clean_llm_text


def is_azure_openai_configured() -> bool:
    return all([
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        os.getenv("AZURE_OPENAI_API_VERSION"),
    ])


def build_official_recommendation_context(recommendation: BoardRecommendation | None) -> str:
    if recommendation is None:
        return "Official Quivrr recommendation: not enough rider data yet."

    return "\n".join([
        "Official Quivrr recommendation:",
        f"Board category: {recommendation.board_category}",
        f"Suggested length range: {recommendation.suggested_length_range}",
        f"Suggested volume range: {recommendation.suggested_volume_range_litres}",
        f"Construction notes: {recommendation.construction_notes or 'Not specified.'}",
        f"Why it fits: {recommendation.why_it_fits}",
        f"Quivrr search direction: {recommendation.quivrr_search_direction}",
        "",
        "Instruction:",
        "Use the official Quivrr recommendation exactly.",
        "Do not widen or change the length range.",
        "Do not widen or change the volume range.",
        "Do not invent board models outside the controlled board model context.",
        "Preserve the controlled board model ranking order exactly when listing suggested boards.",
    ])


def ask_bodhi(
    message: str,
    region: str | None = None,
    page_context: str | None = None,
    recommendation_context: str | None = None,
    official_recommendation_context: str | None = None,
) -> str:
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )

    context = []
    if region:
        context.append(f"Region: {region}")
    if page_context:
        context.append(f"Page context: {page_context}")
    if official_recommendation_context:
        context.append(official_recommendation_context)
    if recommendation_context:
        context.append(recommendation_context)

    user_content = "\n".join(context + [f"User message: {message}"])

    response = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": BODHI_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.25,
        max_tokens=650,
    )

    return clean_llm_text(response.choices[0].message.content or "")
