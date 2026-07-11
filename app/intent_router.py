from __future__ import annotations

import re
from dataclasses import dataclass, field


LEGACY_INTENTS = {
    "inventory_count_question", "board_search_request", "surfer_fit_request",
    "alternative_request", "comparison_request", "general_board_question",
    "site_help_question", "capability_help_request", "volume_advice_request", "exact_board_location_request",
    "relationship_request", "greeting_request", "expert_board_question",
}

NORMALIZED_INTENTS = {
    "GREETING", "GENERAL_HELP", "BOARD_RECOMMENDATION", "BOARD_COMPARISON",
    "BOARD_DETAILS", "AVAILABILITY", "REGIONAL_SEARCH", "QUIVER_REVIEW",
    "QUIVER_GAP", "PROGRESSION", "VOLUME_GUIDANCE", "DIMENSION_GUIDANCE",
    "CONSTRUCTION_GUIDANCE", "FIN_GUIDANCE", "WAVE_GUIDANCE",
    "BOARD_CATEGORY_EDUCATION", "BRAND_QUESTION", "RETAILER_QUESTION",
    "FOLLOW_UP", "SMALL_TALK", "UNKNOWN",
}


@dataclass(frozen=True)
class IntentResult:
    intent: str
    legacy_intent: str
    confidence: float
    entities: dict[str, object] = field(default_factory=dict)
    needs_clarification: bool = False
    needs_board_pair: bool = False
    needs_region: bool = False
    relationship_hint: str | None = None


def _normalise_text(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


def _extract_entities(text: str) -> dict[str, object]:
    entities: dict[str, object] = {
        "region": None,
        "boardCategory": None,
        "brand": None,
        "models": [],
        "targetVolumeLitres": None,
        "waveType": None,
    }

    region_patterns = {
        "AU": r"\b(?:australia|australian|au)\b",
        "EU": r"\b(?:europe|european|eu)\b",
        "ID": r"\b(?:indonesia|indo|indonesian|id)\b",
        "US": r"\b(?:united states|usa|us)\b",
    }
    for region, pattern in region_patterns.items():
        if re.search(pattern, text):
            entities["region"] = region
            break

    category_patterns = {
        "Fish": r"\bfish\b",
        "Hybrid": r"\bhybrid\b",
        "Daily driver": r"\bdaily driver\b",
        "Performance shortboard": r"\b(?:performance shortboard|shortboard)\b",
        "Groveller": r"\b(?:groveller|groveler)\b",
        "Step up": r"\bstep[ -]?up\b",
        "Mid length": r"\bmid[ -]?length\b",
    }
    for category, pattern in category_patterns.items():
        if re.search(pattern, text):
            entities["boardCategory"] = category
            break

    volume_match = re.search(r"\b(\d{2}(?:\.\d+)?)\s*(?:l|litre|litres)\b", text)
    if volume_match:
        entities["targetVolumeLitres"] = float(volume_match.group(1))

    if re.search(r"\breef\b", text):
        entities["waveType"] = "Reef Break"
    elif re.search(r"\bpoint\b", text):
        entities["waveType"] = "Point Break"
    elif re.search(r"\bbeach\b", text):
        entities["waveType"] = "Beach Break"
    elif re.search(r"\bweak\b", text):
        entities["waveType"] = "Weak waves"

    if re.search(r"\bpyzel\b", text):
        entities["brand"] = "Pyzel"
    elif re.search(r"\bjs\b", text):
        entities["brand"] = "JS Industries"
    elif re.search(r"\blost\b", text):
        entities["brand"] = "Lost"

    model_patterns = ["phantom", "monsta", "ghost", "hypto", "hypto krypto", "rnf 96", "seaside", "bom dia"]
    for model in model_patterns:
        if model in text:
            entities["models"].append(model.title() if model != "rnf 96" else "RNF 96")

    return entities


def classify_intent(message: str) -> IntentResult:
    text = _normalise_text(message)
    entities = _extract_entities(text)

    if not text:
        return IntentResult("GREETING", "greeting_request", 0.96, entities)
    if re.fullmatch(r"(?:hey|hi|hello|gday|g'day|yo|morning|afternoon|evening|good morning|good afternoon|good evening|hi bodhi|hey bodhi|hello bodhi)[!. ]*", text):
        return IntentResult("GREETING", "greeting_request", 0.98, entities)
    if re.fullmatch(r"(?:thanks|thank you|cheers|nice one|legend)[!. ]*", text):
        return IntentResult("SMALL_TALK", "greeting_request", 0.93, entities)
    if re.fullmatch(r"(?:australia|europe|indonesia|indo|united states|usa|us|au|eu|id)", text):
        return IntentResult("FOLLOW_UP", "surfer_fit_request", 0.78, entities)
    if re.fullmatch(r"(?:point breaks?|reef breaks?|beach breaks?|weak waves?)", text):
        return IntentResult("FOLLOW_UP", "surfer_fit_request", 0.8, entities)
    if re.search(r"\b(?:what can you do|can you help me|help me|what should i ask|what can you help me with)\b", text):
        return IntentResult("GENERAL_HELP", "capability_help_request", 0.96, entities)
    if re.search(r"\b(?:how do i use the site|how do i use quivrr|how do i use this site|how can i use the site)\b", text):
        return IntentResult("GENERAL_HELP", "site_help_question", 0.96, entities)
    if re.search(r"\b(?:how many boards do you know about|how many boards are there|how many boards do you have)\b", text):
        return IntentResult("AVAILABILITY", "inventory_count_question", 0.9, entities)
    if re.search(r"\b(?:what volume|volume should i|how many litres)\b", text):
        return IntentResult("VOLUME_GUIDANCE", "volume_advice_request", 0.97, entities)
    if re.search(r"\b(?:best|top|favourite|favorite|what would you ride)\b", text) and re.search(r"\b(?:shortboard|fish|groveller|daily driver|step up|board)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "expert_board_question", 0.82, entities)
    if re.search(r"\b(?:instead of|alternative|what else is similar|out of stock)\b", text):
        return IntentResult("FOLLOW_UP", "alternative_request", 0.9, entities)
    if re.search(r"\b(?:compare|comparison|versus|vs\.?|difference between|trade offs?)\b", text):
        return IntentResult("BOARD_COMPARISON", "comparison_request", 0.97, entities, needs_board_pair=True)
    if re.search(r"\bbetter\b.+\bthan\b", text):
        return IntentResult("BOARD_COMPARISON", "comparison_request", 0.9, entities, needs_board_pair=True)
    if re.search(r"\b(?:tell me about|what is the .* like|explain the)\b", text):
        return IntentResult("BOARD_DETAILS", "general_board_question", 0.9, entities)
    if re.search(r"\b(?:where can i buy|is .* available|who has|manufacturer stock|retailer stock)\b", text):
        return IntentResult("AVAILABILITY", "exact_board_location_request", 0.95, entities, needs_region=entities["region"] is None)
    if "where is this exact board" in text:
        return IntentResult("AVAILABILITY", "exact_board_location_request", 0.88, entities)
    if re.search(r"\b(?:search|open .* region|regional search)\b", text):
        return IntentResult("REGIONAL_SEARCH", "board_search_request", 0.82, entities, needs_region=entities["region"] is None)
    if re.search(r"\b(?:what is missing from my quiver|review my quiver)\b", text):
        return IntentResult("QUIVER_REVIEW", "relationship_request", 0.9, entities)
    if re.search(r"\b(?:quiver gap|next board in my quiver|overlap my quiver)\b", text):
        return IntentResult("QUIVER_GAP", "relationship_request", 0.88, entities)
    if re.search(r"\b(?:improve turns|help me progress|ready for|reduce volume)\b", text):
        return IntentResult("PROGRESSION", "surfer_fit_request", 0.86, entities)
    if re.search(r"\b(?:help choosing a board|need help choosing a board|what should i ride next)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "surfer_fit_request", 0.88, entities, needs_clarification=True)
    if re.search(r"\b(?:do you have any boards|boards in stock|show me .* in stock)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.9, entities, needs_clarification=False)
    if re.search(r"\b(?:easier than|more forgiving than|more performance than|better for point breaks|better for weak waves)\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.9, entities)
    if re.search(r"\bwhat is like\b.+\bbetter for\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.9, entities)
    if re.search(r"\b\d{2,3}\s*kg\b", text) and re.search(r"\b(?:shortboard|fish|daily driver|step up|hybrid|groveller|groveler)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "surfer_fit_request", 0.9, entities)
    if re.search(r"\b(?:show me|find me|looking for|i need|i want|want a|chasing)\b", text):
        needs = not entities["boardCategory"] and entities["targetVolumeLitres"] is None and entities["waveType"] is None
        legacy = "surfer_fit_request" if "help" in text and "board" in text else "board_search_request"
        return IntentResult("BOARD_RECOMMENDATION", legacy, 0.91, entities, needs_clarification=needs)
    if re.search(r"\b(?:dimensions|length|width|thickness)\b", text):
        return IntentResult("DIMENSION_GUIDANCE", "general_board_question", 0.82, entities)
    if re.search(r"\b(?:eps|pu|construction|hyfi|carbon|epoxy)\b", text):
        return IntentResult("CONSTRUCTION_GUIDANCE", "general_board_question", 0.84, entities)
    if re.search(r"\b(?:fin|thruster|quad|twin fin|twin)\b", text):
        return IntentResult("FIN_GUIDANCE", "general_board_question", 0.84, entities)
    if re.search(r"^(?:what|which|how)\b", text) and re.search(r"\b(?:reef waves|beach breaks|point breaks|wave size|weak waves)\b", text):
        return IntentResult("WAVE_GUIDANCE", "general_board_question", 0.8, entities)
    if re.search(r"\bis .+\b(?:a |an )?(?:fish|daily driver|groveller|step[ -]?up)\b", text):
        return IntentResult("BOARD_CATEGORY_EDUCATION", "general_board_question", 0.86, entities)
    if re.search(r"\b(?:what is a|what does|explain)\b", text) and re.search(r"\b(?:fish|daily driver|groveller|step up|rocker|rails?|concave|tail)\b", text):
        return IntentResult("BOARD_CATEGORY_EDUCATION", "general_board_question", 0.88, entities)
    if re.search(r"\b(?:which pyzel|which lost|which js|brand)\b", text):
        return IntentResult("BRAND_QUESTION", "expert_board_question", 0.84, entities)
    if re.search(r"\b(?:retailer|shop|store|merchant)\b", text):
        return IntentResult("RETAILER_QUESTION", "site_help_question", 0.76, entities)
    if re.search(r"\b(?:number \d|compare \d|tell me about \d|remove pyzel|only show|show australian brands)\b", text):
        return IntentResult("FOLLOW_UP", "alternative_request", 0.87, entities)
    if re.search(r"\b(?:more performance|more forgiving|more paddle|easier paddle|sharper|less demanding|similar to|alternative to|step up from|step down from)\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.82, entities)
    if re.search(r"^(?:what|why|how|when)\b", text) and re.search(r"\b(?:surfboard|board|volume|litres?|rocker|rails?|concave|fins?|epoxy|pu|construction)\b", text):
        return IntentResult("BOARD_CATEGORY_EDUCATION", "general_board_question", 0.74, entities)
    return IntentResult("UNKNOWN", "surfer_fit_request", 0.45, entities, needs_clarification=True)


def route_intent(message: str) -> str:
    return classify_intent(message).legacy_intent
