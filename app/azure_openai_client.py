import os
from openai import AzureOpenAI

from app.prompts import BODHI_SYSTEM_PROMPT
from app.text_cleaning import clean_llm_text


def is_azure_openai_configured() -> bool:
    return all([
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        os.getenv("AZURE_OPENAI_API_VERSION"),
    ])


def ask_bodhi(
    message: str,
    region: str | None = None,
    page_context: str | None = None,
    recommendation_context: str | None = None,
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
    if recommendation_context:
        context.append(recommendation_context)

    user_content = "\n".join(context + [f"User message: {message}"])

    response = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": BODHI_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.35,
        max_tokens=650,
    )

    return clean_llm_text(response.choices[0].message.content or "")
