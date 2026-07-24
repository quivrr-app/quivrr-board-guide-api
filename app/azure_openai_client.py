import os
import time

from openai import AzureOpenAI

from app.models import BoardRecommendation
from app.prompts import BODHI_SYSTEM_PROMPT
from app.structured_logging import emit_event
from app.text_cleaning import clean_llm_text


def is_azure_openai_configured() -> bool:
    return all([
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        os.getenv("AZURE_OPENAI_API_VERSION"),
    ])


def configured_deployment(request_type: str = "response") -> str | None:
    if request_type == "profile":
        return os.getenv("AZURE_OPENAI_PROFILE_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    return os.getenv("AZURE_OPENAI_DEPLOYMENT")


def refinement_enabled() -> bool:
    return os.getenv("BODHI_ENABLE_LLM_REFINEMENT", "0") == "1"


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ["timeout", "temporar", "rate limit", "429", "500", "502", "503", "504", "connection"])


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
    deployment = configured_deployment("response")
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
    max_attempts = max(1, int(os.getenv("AZURE_OPENAI_RETRY_ATTEMPTS", "2")))
    timeout_seconds = float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "20"))
    request_payload = build_bodhi_request_payload(
        deployment=deployment,
        user_content=user_content,
        timeout_seconds=timeout_seconds,
    )

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(**request_payload)
            return clean_llm_text(response.choices[0].message.content or "")
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable(exc):
                emit_event(
                    "bodhi_openai_failure",
                    "bodhi_api",
                    region=region,
                    status="failed",
                    deployment=deployment,
                    request_type="response",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                raise
            time.sleep(0.25 * attempt)


def build_bodhi_request_payload(*, deployment: str | None, user_content: str, timeout_seconds: float) -> dict:
    """Return the complete Azure request for audit and deterministic test coverage.

    This deliberately has no tool definitions, tool choice, structured-output
    schema, or conversation transcript.  The current model is used only to
    refine a reply after the deterministic conversation router has selected the
    operation and its governed data.
    """
    return {
        "model": deployment,
        "messages": [
            {"role": "system", "content": BODHI_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.25,
        "max_tokens": int(os.getenv("AZURE_OPENAI_MAX_OUTPUT_TOKENS", "650")),
        "timeout": timeout_seconds,
    }


def safe_ask_bodhi(**kwargs) -> tuple[str | None, str | None]:
    if not refinement_enabled() or not is_azure_openai_configured():
        return None, None
    try:
        return ask_bodhi(**kwargs), configured_deployment("response")
    except Exception:
        return None, None
