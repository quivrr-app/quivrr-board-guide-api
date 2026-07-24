from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.manufacturer_intelligence import canonical_manufacturer_name


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
    "IDENTITY_QUERY", "PROFILE_QUESTION", "AUTH_STATE_UPDATE", "NO_REQUEST", "ACKNOWLEDGEMENT_ONLY",
    "OFF_TOPIC", "ABUSIVE", "PROMPT_INJECTION",
    "CONVERSATION_RESET",
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


def _normalise_greeting_text(message: str) -> str:
    text = re.sub(r"[^a-z0-9\s']", " ", (message or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bbohdi\b", "bodhi", text)
    text = re.sub(r"\bbodi\b", "bodhi", text)
    return text


def _is_greeting_or_small_talk(message: str) -> bool:
    text = _normalise_greeting_text(message)
    greeting_patterns = (
        r"(?:hey|hi|hello)(?: there| mate| again)?(?: bodhi)?",
        r"(?:good )?morning",
        r"good afternoon",
        r"good evening",
        r"what'?s up",
        r"how are you",
    )
    return any(re.fullmatch(pattern, text) for pattern in greeting_patterns)


def _extract_entities(text: str) -> dict[str, object]:
    entities: dict[str, object] = {
        "region": None,
        "boardCategory": None,
        "availabilityConstraint": None,
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
        "Performance shortboard": r"\b(?:performance shortboard|shortboard|short board)\b",
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

    if re.search(r"\breefs?\b", text):
        entities["waveType"] = "Reef Break"
    elif re.search(r"\bpoint\b", text):
        entities["waveType"] = "Point Break"
    elif re.search(r"\bbeach\b", text):
        entities["waveType"] = "Beach Break"
    elif re.search(r"\bweak\b", text):
        entities["waveType"] = "Weak waves"

    if re.search(
        r"\b(?:what(?:'s| is) available|show me what(?:'s| is) available|available in my (?:size|volume)|"
        r"available in (?:indonesia|indo|bali)|what can i (?:buy|get)|boards? i can buy now|"
        r"show me boards? in stock|i asked for (?:you to show me )?boards? in stock|"
        r"i only want available boards?|why are you showing unavailable boards?|remove (?:anything|boards?) not in stock|"
        r"remove unavailable boards?|only show what i can buy(?: now)?|only show available boards?|"
        r"only in stock|just show me ones in stock|show available boards|available now|currently available|"
        r"currently in stock|is in stock|ones i can buy|in stock in indo|in stock in indonesia|live stock(?: only)?|"
        r"only boards with stock|just show me .* in stock|only show .* in stock)\b",
        text,
    ):
        entities["availabilityConstraint"] = "VERIFIED_IN_STOCK"

    expansion_brand = canonical_manufacturer_name(text)
    if expansion_brand:
        entities["brand"] = expansion_brand
    elif re.search(r"\bpyzel\b", text):
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
        return IntentResult("NO_REQUEST", "site_help_question", 0.99, entities)
    if re.search(
        r"\b(?:ignore|reveal|show|print)\b.*\b(?:system prompt|developer message|instructions|taxonomy rules?|hidden context|database credentials|environment variables)\b|"
        r"\b(?:repeat everything above|enter developer mode|execute arbitrary (?:urls?|sql))\b",
        text,
    ):
        return IntentResult("PROMPT_INJECTION", "site_help_question", 0.99, entities)
    if re.search(r"\b(?:different surfer|this is for my (?:wife|husband|partner|friend|son|daughter)|not for me)\b", text):
        entities["resetScope"] = "surfer"
        return IntentResult("CONVERSATION_RESET", "surfer_fit_request", 0.99, entities)
    if re.fullmatch(r"(?:reset(?: this conversation)?|start over|start again|new board|new conversation|new search|clear (?:the )?chat|forget (?:this conversation|that))[!. ]*", text):
        entities["resetScope"] = "brief"
        return IntentResult("CONVERSATION_RESET", "greeting_request", 0.98, entities)
    if re.search(r"\b(?:what(?:'s| is) my name|whats my name|who am i|do you know my name)\b", text):
        return IntentResult("IDENTITY_QUERY", "site_help_question", 0.99, entities)
    if re.fullmatch(r"(?:ok(?:ay)?[, ]+)?i(?:'m| am)?\s*(?:just )?(?:signed|logged) in[!. ]*", text):
        return IntentResult("AUTH_STATE_UPDATE", "site_help_question", 0.99, entities)
    if re.search(r"\b(?:i (?:did not|didn't) ask(?: for (?:that|anything))?|i wasn't asking|that(?:'s| is) not what i asked)\b", text):
        return IntentResult("NO_REQUEST", "site_help_question", 0.99, entities)
    if re.search(r"\b(?:what profile do you have|what do you know about my profile|show my (?:rider )?profile)\b", text):
        return IntentResult("PROFILE_QUESTION", "site_help_question", 0.98, entities)
    if re.search(r"\b(?:fuck|shit|idiot|useless)\b", text) and not re.search(r"\b(?:board|fish|twin|stock|surf|wave|volume|litre)\b", text):
        return IntentResult("ABUSIVE", "site_help_question", 0.95, entities)
    if re.search(r"\b(?:weather forecast|capital of|tell me a joke|politics|recipe|football score)\b", text):
        return IntentResult("OFF_TOPIC", "site_help_question", 0.94, entities)
    if _is_greeting_or_small_talk(message) or re.fullmatch(r"(?:hey|hi|hello|gday|g'day|yo|morning|afternoon|evening|good morning|good afternoon|good evening|hi bodhi|hey bodhi|hello bodhi)[!. ]*", text):
        return IntentResult("GREETING", "greeting_request", 0.98, entities)
    if re.fullmatch(r"(?:ok|okay|thanks|thank you|cheers|nice one|legend|got it)[!. ]*", text):
        return IntentResult("ACKNOWLEDGEMENT_ONLY", "site_help_question", 0.96, entities)
    if re.fullmatch(r"(?:australia|europe|indonesia|indo|united states|usa|us|au|eu|id)", text):
        return IntentResult("FOLLOW_UP", "surfer_fit_request", 0.78, entities)
    if re.fullmatch(r"(?:point breaks?|reef breaks?|beach breaks?|weak waves?)", text):
        return IntentResult("FOLLOW_UP", "surfer_fit_request", 0.8, entities)
    if re.search(r"\b(?:help choosing a board|need help choosing a board|what should i ride next)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "surfer_fit_request", 0.88, entities, needs_clarification=True)
    if re.search(r"\b(?:what can you do|can you help me|help me|i need help|what should i ask|what can you help me with|show me how quivrr works)\b", text):
        return IntentResult("GENERAL_HELP", "capability_help_request", 0.96, entities)
    if re.search(r"\b(?:how do i use the site|how do i use quivrr|how do i use this site|how can i use the site)\b", text):
        return IntentResult("GENERAL_HELP", "site_help_question", 0.96, entities)
    if re.search(r"\b(?:how many boards do you know about|how many boards are there|how many boards do you have)\b", text):
        return IntentResult("AVAILABILITY", "inventory_count_question", 0.9, entities)
    if entities.get("brand") and re.search(r"\b(?:do you have|do you know|know about|show me|what .* models|which .* models)\b", text):
        if re.search(r"\b(?:stock|available|buy|retailer)\b", text):
            return IntentResult("AVAILABILITY", "board_search_request", 0.97, entities, needs_region=entities["region"] is None)
        return IntentResult("BRAND_QUESTION", "general_board_question", 0.97, entities)
    if re.search(r"\b(?:what volume|volume should i|how many litres|wat litres|how many ltrs|volume for \d+\s*kg|keep it near \d+(?:\.\d+)?\s*l)\b", text):
        return IntentResult("VOLUME_GUIDANCE", "volume_advice_request", 0.97, entities)
    if re.search(r"\b(?:recommend|recomend|pick|choose)\b", text) and re.search(r"\b(?:board|shortboard|fish|fsh|groveller|daily driver|step[ -]?up|mid[ -]?length|twin|reefs?)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.94, entities, needs_clarification=not bool(entities.get("boardCategory") or entities.get("waveType")))
    if re.search(r"\b(?:need a fish|fish for mush|fsh for weak waves|find a twin)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.9, entities)
    if re.search(r"\b(?:best|top|favourite|favorite|what would you ride)\b", text) and re.search(r"\b(?:shortboard|fish|groveller|daily driver|step up|board)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "expert_board_question", 0.82, entities)
    if re.search(r"\b(?:instead of|alternative|what else is similar|out of stock)\b", text):
        return IntentResult("FOLLOW_UP", "alternative_request", 0.9, entities)
    if re.search(r"\b(?:i (?:do not|don't) like|not keen on|rubbish recommendation|bad recommendation|show me something easier|more paddle|easier to paddle)\b", text):
        return IntentResult("FOLLOW_UP", "alternative_request", 0.96, entities)
    if re.search(r"\b(?:how does it|would (?:that|it)|what about the xl|is there a twin version|that one|this one)\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.9, entities)
    if re.search(r"\b(?:compare|comparison|versus|vs\.?|difference between|difference\s+\w+\s+\w+|trade offs?|\w+\s+v\s+\w+)\b", text):
        return IntentResult("BOARD_COMPARISON", "comparison_request", 0.97, entities, needs_board_pair=True)
    if re.search(r"\bwhich is better\b", text) or re.search(r"\b(?:ghost|phantom|monsta|seaside|rnf 96)\s+or\s+(?:ghost|phantom|monsta|seaside|rnf 96)\b", text):
        return IntentResult("BOARD_COMPARISON", "comparison_request", 0.92, entities, needs_board_pair=True)
    if re.search(r"\bbetter\b.+\bthan\b", text):
        return IntentResult("BOARD_COMPARISON", "comparison_request", 0.9, entities, needs_board_pair=True)
    if re.search(r"\b(?:tell me about|what is the .* like|explain the)\b", text):
        return IntentResult("BOARD_DETAILS", "general_board_question", 0.9, entities)
    if re.search(r"^why\b.*\b(?:fish|daily driver|groveller|groveler|step[ -]?up|mid[ -]?length|twin)\b", text):
        return IntentResult("BOARD_CATEGORY_EDUCATION", "general_board_question", 0.94, entities)
    if re.search(r"\bis .+\b(?:a |an )?(?:fish|daily driver|groveller|groveler|step[ -]?up|mid[ -]?length)\b", text):
        return IntentResult("BOARD_CATEGORY_EDUCATION", "general_board_question", 0.94, entities)
    if entities.get("availabilityConstraint") == "VERIFIED_IN_STOCK" and re.search(
        r"\b(?:available|buy|in stock|live stock|unavailable)\b", text
    ):
        return IntentResult("AVAILABILITY", "board_search_request", 0.97, entities, needs_region=entities["region"] is None)
    if re.search(r"\b(?:where can i buy|can i buy|is .* available|who has|manufacturer stock|retailer stock)\b", text):
        return IntentResult("AVAILABILITY", "exact_board_location_request", 0.95, entities, needs_region=entities["region"] is None)
    if re.search(r"\b(?:find .* stock|which retailers have|check regional availability|wots in stock|got any .* stock|stock near me|only stuff i can buy)\b", text):
        entities["availabilityConstraint"] = "VERIFIED_IN_STOCK"
        return IntentResult("AVAILABILITY", "board_search_request", 0.92, entities, needs_region=entities["region"] is None)
    if re.search(r"\b(?:lowest observed|compare offers?|compare prices?|listed price|how much|price for|sponsored offer|why is .* sponsored|sponsorship affect)\b", text):
        legacy = "exact_board_location_request" if re.search(r"\b(?:price|offer|how much)\b", text) else "site_help_question"
        return IntentResult("AVAILABILITY", legacy, 0.94, entities, needs_region=entities["region"] is None)
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
    if re.search(r"\b(?:show catalogue options too|show catalog options too|ignore stock for now|include catalogue options|include catalog options)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.9, entities, needs_clarification=False)
    if re.search(r"\b(?:do you have any boards|boards in stock|show me .* in stock)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.9, entities, needs_clarification=False)
    if re.search(r"\b(?:easier than|more forgiving than|more performance than|better for point breaks|better for weak waves)\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.9, entities)
    if re.search(r"\bwhat is like\b.+\bbetter for\b", text):
        return IntentResult("FOLLOW_UP", "relationship_request", 0.9, entities)
    if re.search(r"\b\d{2,3}\s*kg\b", text) and re.search(r"\b(?:shortboard|fish|daily driver|step up|hybrid|groveller|groveler)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "surfer_fit_request", 0.9, entities)
    if re.search(r"\b(?:show me|find me|give me|looking for|i need|i want|want a|chasing)\b", text):
        needs = not entities["boardCategory"] and entities["targetVolumeLitres"] is None and entities["waveType"] is None
        legacy = "surfer_fit_request" if "help" in text and "board" in text else "board_search_request"
        return IntentResult("BOARD_RECOMMENDATION", legacy, 0.91, entities, needs_clarification=needs)
    if re.search(r"\b(?:wat|what|wht)\b.*\bfish\b.*\b(?:shuld|should|get|buy)\b", text):
        return IntentResult("BOARD_RECOMMENDATION", "board_search_request", 0.88, entities)
    if re.search(r"\b(?:whts|whats|what is)\b.*\b(?:stok|stock)\b", text):
        entities["availabilityConstraint"] = "VERIFIED_IN_STOCK"
        return IntentResult("AVAILABILITY", "board_search_request", 0.9, entities, needs_region=entities["region"] is None)
    if re.search(r"\b(?:dimensions|length|width|thickness)\b", text):
        return IntentResult("DIMENSION_GUIDANCE", "general_board_question", 0.82, entities)
    if re.search(r"\b(?:eps|pu|construction|hyfi|carbon|epoxy)\b", text):
        return IntentResult("CONSTRUCTION_GUIDANCE", "general_board_question", 0.84, entities)
    if re.search(r"\b(?:fin|fins|wot fins|thruster|quad|twin fin|twin|2\+1)\b", text):
        return IntentResult("FIN_GUIDANCE", "general_board_question", 0.84, entities)
    if re.search(r"\b(?:would|will|does|can)\b.*\b(?:work|suit|handle)\b.*\b(?:reefs?|waves?|weak|powerful|hollow)\b", text):
        return IntentResult("WAVE_GUIDANCE", "general_board_question", 0.86, entities)
    if re.search(r"^(?:what|which|how)\b", text) and re.search(r"\b(?:reef waves|beach breaks|point breaks|wave size|weak waves)\b", text):
        return IntentResult("WAVE_GUIDANCE", "general_board_question", 0.8, entities)
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
    # Compatibility keeps the legacy label for downstream educational and stage
    # safety paths.  The conversation orchestration guard is the authority that
    # prevents this unknown input from invoking the recommendation engine.
    return IntentResult("UNKNOWN", "surfer_fit_request", 0.45, entities, needs_clarification=True)


def route_intent(message: str) -> str:
    return classify_intent(message).legacy_intent
