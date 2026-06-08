
def clean_llm_text(value: str) -> str:
    if not value:
        return ""

    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }

    cleaned = value
    for bad, good in replacements.items():
        cleaned = cleaned.replace(bad, good)

    return cleaned
