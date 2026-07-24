from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Header
from fastapi import Request
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from dataclasses import dataclass
import os
import re
import time
import uuid

from app.azure_openai_client import (
    build_official_recommendation_context,
    is_azure_openai_configured,
    safe_ask_bodhi,
)
from app.authenticated_profile import load_authenticated_profile_context
from app.board_intelligence import find_board_record
from app.board_resolver import resolve_board
from app.manufacturer_intelligence import (
    canonical_manufacturer_name,
    compare_staged_models,
    construction_summaries,
    find_manufacturer,
    find_staged_model,
    list_manufacturers,
    load_manufacturer_expansion_catalogue,
    model_summary,
    models_for_manufacturer,
)
from app.comparison_engine import compare_board_models
from app.conversation_flow import (
    comparison_reply, enough_for_recommendations, expert_board_question_reply, find_requested_board,
    general_board_reply, graph_suggestions, greeting_reply, has_intake_signal, intake_questions, opening_message,
    personalise_opening,
    is_memory_correction, partial_volume_reply, fish_advice_reply, board_family_reply,
    public_recommendations, recommendation_reply, site_help_reply, suggestions_for_board,
    volume_advice_reply, volume_guidance, everyday_pushback_reply,
)
from app.active_topic import resolve_active_topic
from app.catalogue_search import extract_category, inventory_snapshot_reply, search_live_category
from app.intent_router import IntentResult, classify_intent, route_intent
from app.conversation_orchestration import ConversationDecision, decide_conversation
from app.conversation_controller import ConversationDirective, control_conversation
from app.conversation_policy import (
    FOLLOW_UP_CORRECTION, classify_language_tone, follow_up_kind, is_performance_fish_request,
    prompt_disclosure_reply, recovery_opening, response_signature,
)
from app.board_expert_matrix import recommend_from_matrix
from app.board_master import find_master_board, load_board_master
from app.family_intent import FamilyIntent, PUBLIC_FAMILY_LABELS, correction_acknowledgement, resolve_family_intent
from app.board_dna import find_board_dna, find_board_dna_by_id, load_board_dna, resolve_dna_brief, score_dna_fit
from app.board_relationship_graph import (
    relationship_reply, relationship_suggestions, relationship_type, source_board_from_message,
)
from app.model_recommendation_engine import build_recommendation_context, recommend_models
from app.inventory_client import available_manufacturer_models, enrich_suggestions_with_inventory, inventory_summary, locate_exact_board, model_availability, quivrr_search_url
from app.models import BoardComparison, BoardGuideRequest, BoardGuideResponse, BoardReference, BodhiRecommendation, ConversationState, FollowUpAction, ProfileUpdateProposal, SuggestedBoard
from app.profile_engine import (
    build_recommendation,
    extract_profile,
    merge_rider_profile,
    merge_profiles,
    missing_profile_fields,
    profile_completeness,
    with_profile_source,
)
from app.volume_engine_v2 import build_target_volume_context, build_volume_recommendation
from app.structured_logging import emit_event
from app.surfer_stage import BEGINNER_QUESTION, PREMIUM_BEGINNER_POSITIONING, STAGE_1, assess_surfer_stage, beginner_guidance, stage_allows_board
from app.topic_routing import classify_topic_route
from app.surf_domain import load_surf_domain_knowledge


load_dotenv()
SURF_DOMAIN_KNOWLEDGE = load_surf_domain_knowledge()

APP_NAME = "Quivrr Board Guide API"
BUILD_SHA = os.getenv("BODHI_BUILD_SHA") or os.getenv("WEBSITE_COMMIT_ID") or "unknown"
BUILD_GIT_SHA = os.getenv("BODHI_GIT_SHA") or os.getenv("WEBSITE_COMMIT_ID") or "unknown"
RECOMMENDATION_ENGINE_NAME = os.getenv("BODHI_ENGINE_VERSION") or "matrix_v2"
STARTUP_TIME_UTC = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
DEPLOYMENT_ID = (
    os.getenv("BODHI_DEPLOYMENT_ID")
    or os.getenv("WEBSITE_DEPLOYMENT_ID")
    or os.getenv("APPSETTING_WEBSITE_DEPLOYMENT_ID")
    or os.getenv("SCM_RUN_FROM_PACKAGE")
    or "unknown"
)
REGION_DISPLAY_NAMES = {
    "AU": "Australia",
    "EU": "Europe",
    "ID": "Indonesia",
    "US": "the United States",
}
RECOMMENDATION_INTENTS = {
    "board_search_request",
    "surfer_fit_request",
    "alternative_request",
}
NON_RECOMMENDATION_GUARD_INTENTS = {
    "AUTH_STATE_UPDATE", "IDENTITY_QUERY", "PROFILE_QUESTION", "NO_REQUEST", "ACKNOWLEDGEMENT_ONLY",
    "GREETING", "SMALL_TALK", "CONVERSATION",
}
STOCK_ONLY_CONSTRAINT = "VERIFIED_IN_STOCK"


def _model_classification_correction(message: str) -> dict | None:
    text = message.lower()
    if not re.search(r"\b(?:is not|isn't|not a|actually (?:a|an)|is (?:a|an))\b", text):
        return None
    board = find_requested_board(message)
    if board and board["model"].lower() in {"fish", "twin", "shortboard"}:
        # Generic family/fin language can collide with canonically named models.
        # Treat it as family intent unless the user also named the manufacturer.
        if board["brand"].lower() not in text:
            return None
    if not board:
        matches = [
            row for row in load_board_dna()["models"]
            if re.search(rf"\b{re.escape(row['model'].lower())}\b", text)
            and (
                row["model"].lower() not in {"fish", "twin", "shortboard"}
                or row["brand"].lower() in text
            )
        ]
        if matches:
            matches.sort(key=lambda row: len(row["model"]), reverse=True)
            board = {"brand": matches[0]["brand"], "model": matches[0]["model"]}
        else:
            return None
    dna = find_board_dna(board["brand"], board["model"])
    if not dna:
        return None
    family_phrases = (
        ("performance shortboard", "performance_shortboard"), ("daily driver", "daily_driver"),
        ("step up", "step_up"), ("mid length", "mid_length"), ("longboard", "longboard"),
        ("groveller", "groveller"), ("hybrid", "daily_driver"), ("fish", "fish"),
    )
    asserted = next((
        family for phrase, family in family_phrases
        if re.search(rf"\b(?:is|actually)\s+(?:a|an)?\s*{re.escape(phrase)}\b", text)
    ), None)
    if asserted is None:
        asserted = next((family for phrase, family in family_phrases if phrase in text), None)
    return {"board": board, "dna": dna, "asserted_family": asserted}


@dataclass(frozen=True)
class CategoryResolution:
    category: str | None
    confidence: float
    source: str


def _build_metadata() -> dict:
    return {
        "build": BUILD_SHA,
        "git_sha": BUILD_GIT_SHA,
        "recommendation_engine": RECOMMENDATION_ENGINE_NAME,
        "startup_time": STARTUP_TIME_UTC,
        "deployment_id": DEPLOYMENT_ID,
    }


def _set_debug_headers(response: Response, recommendation_path: str | None = None, ranking_engine: str | None = None):
    response.headers["X-Bodhi-Build"] = BUILD_SHA
    response.headers["X-Bodhi-Engine"] = ranking_engine or RECOMMENDATION_ENGINE_NAME
    if recommendation_path:
        response.headers["X-Bodhi-Path"] = recommendation_path


def _message_requests_stock_only(message: str) -> bool:
    lowered = message.lower()
    return bool(re.search(
        r"\b(?:what(?:'s| is) available|show me what(?:'s| is) available|available in my (?:size|volume)|"
        r"available in (?:indonesia|indo|bali)|what can i (?:buy|get)|boards? i can buy now|"
        r"do any (?:of )?(?:these|them|those) have stock(?: in (?:indonesia|indo|bali))?|"
        r"(?:have|has|check|show|find) stock in (?:indonesia|indo|bali)|"
        r"(?:do you have|have you got|show me|find me)?[^.?!]{0,40}\bin stock\b|"
        r"show me boards? in stock|i asked for (?:you to show me )?boards? in stock|"
        r"i only want available boards?|why are you showing unavailable boards?|remove (?:anything|boards?) not in stock|"
        r"remove unavailable boards?|only show what i can buy(?: now)?|only show available boards?|"
        r"only in stock|just show me ones in stock|show available boards|available now|currently available|"
        r"currently in stock|is in stock|ones i can buy|in stock in indo|in stock in indonesia|live stock(?: only)?|"
        r"only boards with stock|only show stock if (?:there is|there's|any)|"
        r"just show me .* in stock|only show .* in stock)\b",
        lowered,
    ))


def _message_requests_active_board_inventory(message: str) -> bool:
    """Deterministic inventory follow-up gate, evaluated before historical intent."""
    return bool(re.search(
        r"\b(?:available|availability|in stock|stock|what sizes|which sizes|show me sizes|"
        r"how much|price|where can i buy|who has it|retailers?|manufacturer stock|"
        r"show me the board|search for it|check if (?:it|that|this) is available)\b",
        (message or "").lower(),
    ))


def _message_removes_stock_constraint(message: str) -> bool:
    lowered = message.lower()
    return bool(re.search(
        r"\b(?:show catalogue options too|show catalog options too|ignore stock for now|include catalogue options|"
        r"include catalog options|don't worry about stock|do not worry about stock)\b",
        lowered,
    ))


def _sponsorship_explanation(message: str) -> str | None:
    lowered = message.lower()
    if not re.search(r"\b(?:sponsor|sponsored|sponsorship|promoted)\b", lowered):
        return None
    return (
        "Sponsored offers are paid placements and are always labelled. Sponsorship does not change Bodhi's "
        "board suitability, classification, or recommendation order; I recommend the board first, then show "
        "any region-matched offers separately after the organic options."
    )


def _requests_offer_price(message: str) -> bool:
    return bool(re.search(r"\b(?:lowest observed|compare offers?|compare prices?|listed price|how much|price for)\b", message.lower()))


def _offer_price_sort(board: SuggestedBoard) -> tuple:
    offer = board.offers[0] if board.offers else None
    return (
        offer.observed_price is None if offer else True,
        offer.observed_price if offer and offer.observed_price is not None else float("inf"),
    )


def _resolve_availability_constraint(request, intent_result) -> str | None:
    if _message_removes_stock_constraint(request.message):
        return None
    if _message_requests_stock_only(request.message):
        return STOCK_ONLY_CONSTRAINT
    previous = request.conversation_state.availability_constraint if request.conversation_state else None
    if previous == STOCK_ONLY_CONSTRAINT and intent_result.legacy_intent in RECOMMENDATION_INTENTS:
        return STOCK_ONLY_CONSTRAINT
    return previous


def _category_label(category: str | None) -> str:
    if not category:
        return "board"
    return {
        "performance_daily_driver": "performance daily driver",
        "performance_shortboard": "performance shortboard",
        "small_wave": "small wave board",
        "mid_length": "mid length",
        "step_up": "step up",
        "shortboard": "shortboard",
    }.get(category, category.replace("_", " "))


def _safe_profile_source(value: str | None) -> str:
    return {
        "saved_profile": "saved_profile",
        "account_profile": "saved_profile",
        "current_user": "current_message",
        "conversation_user": "conversation_context",
        "conversation_profile": "conversation_context",
        "inferred": "fallback",
    }.get(str(value or "").strip().lower(), "missing")


def _profile_field_source(profile, field: str) -> str:
    if not profile:
        return "missing"
    return _safe_profile_source(profile.field_provenance.get(field))


def _recommendation_lane(category: str | None, profile) -> str | None:
    if category in {"traditional_fish", "performance_fish"}:
        return category
    if category == "fish":
        if "reef" in (profile.wave_type or "").lower():
            return "performance_fish"
        if "point" in (profile.wave_type or "").lower():
            return "point_break_fish"
        if "traditional" in " ".join(filter(None, [profile.goal, profile.desired_feel, profile.preferred_board_type])).lower():
            return "traditional_fish"
        return "performance_fish"
    if category == "performance_twin":
        return "performance_fish"
    if category == "performance_shortboard":
        return "performance_shortboard"
    if category == "performance_daily_driver":
        return "performance_daily_driver"
    return None


def _apply_target_volume_context(profile, category: str | None):
    context = build_target_volume_context(profile, _recommendation_lane(category, profile))
    if context is None:
        return profile, None
    updated = profile.model_copy(update={
        "target_volume_litres": context.target_litres,
        "target_volume_min_litres": context.minimum_litres,
        "target_volume_max_litres": context.maximum_litres,
        "target_volume_source": context.source,
        "target_volume_confidence": context.confidence,
    })
    return updated, context


def _filter_volume_compatible(boards):
    filtered = [board for board in boards if (board.volume_compatibility or "good") in {"excellent", "good"}]
    return filtered or boards


def _volume_correction_requested(message: str) -> bool:
    lowered = (message or "").lower()
    return any(token in lowered for token in (
        "range is too broad",
        "volumes are all over the place",
        "keep it around my normal volume",
        "why is that one so small",
        "why is that one so big",
    ))


def _category_ranking_profile(profile, message: str, category: str | None):
    lowered = (message or "").lower()
    current_preference = (profile.preferred_board_type or "").lower()
    updates = {}

    if "forgiving" in lowered or "more support" in lowered or "paddle help" in lowered:
        updates["desired_feel"] = "more forgiving"

    if "performance twin" in lowered or ("twin" in lowered and "performance" in lowered):
        updates["preferred_board_type"] = "Performance Twin"
    elif category in {"fish", "traditional_fish", "performance_fish"}:
        updates["preferred_board_type"] = {
            "traditional_fish": "Traditional Fish",
            "performance_fish": "Performance Fish",
        }.get(category, "Fish")
    elif category in {"daily_driver", "performance_daily_driver"}:
        updates["preferred_board_type"] = "Performance Daily Driver"
    elif category == "performance_shortboard":
        if "true performance shortboard" in lowered or "competition shortboard" in lowered or "strict hpsb" in lowered:
            updates["preferred_board_type"] = "True performance shortboard"
        elif "true performance shortboard" in current_preference or "competition shortboard" in current_preference:
            updates["preferred_board_type"] = "True performance shortboard"
        else:
            updates["preferred_board_type"] = "Performance shortboard"
    elif category == "small_wave":
        updates["preferred_board_type"] = "Small wave board"
    elif category == "step_up":
        updates["preferred_board_type"] = "Step up"
    elif category == "mid_length":
        updates["preferred_board_type"] = "Mid length"
    elif category == "shortboard":
        updates["preferred_board_type"] = "Shortboard"

    return profile.model_copy(update=updates) if updates else profile


def _verified_in_stock(boards):
    return [
        board for board in boards
        if (board.available_count or 0) > 0
        and board.availability_checked
        and board.availability_status in {"manufacturer_stock", "retailer_stock", "manufacturer_and_retailer_stock", "available"}
    ]


def _unique_boards(boards):
    output, seen = [], set()
    for board in boards:
        key = (board.brand.lower(), board.model.lower())
        if key not in seen:
            seen.add(key)
            output.append(board)
    return output


def _shortlist_family_buckets(category: str | None, profile, message: str) -> tuple[set[str], set[str]]:
    lowered = (message or "").lower()
    if category == "traditional_fish":
        return {"Fish", "Traditional Fish"}, set()
    if category == "performance_fish":
        return {"Performance Fish"}, set()
    if category == "fish":
        if "reef" in lowered or "reef" in (profile.wave_type or "").lower():
            return {"Performance Fish", "Performance Twin", "Fish"}, set()
        return {"Fish", "Performance Fish", "Traditional Fish"}, set()
    if category == "performance_shortboard":
        primary = {"High Performance Shortboard", "Performance Shortboard"}
        secondary = set()
        support_signals = (
            "forgiving" in lowered
            or "support" in lowered
            or "weak wave" in lowered
            or "small wave" in lowered
            or (profile.ability or "").lower() in {"beginner", "progressing", "intermediate"}
        )
        if support_signals:
            secondary.add("Performance Daily Driver")
        return primary, secondary
    if category == "performance_daily_driver":
        return {"Performance Daily Driver"}, {"High Performance Shortboard"}
    if category == "performance_twin":
        return {"Performance Twin"}, {"Alternative Performance"}
    if category == "small_wave":
        return {"Groveller", "Small Wave Shortboard", "Performance Fish", "Fish", "Hybrid Shortboard"}, set()
    if category == "step_up":
        return {"Step Up", "Semi Gun", "Performance Shortboard"}, set()
    return set(), set()


def _enforce_shortlist_coherence(
    boards,
    category: str | None,
    profile,
    message: str,
    limit: int | None = None,
    family_intent: FamilyIntent | None = None,
):
    if family_intent and (family_intent.requested_public_family or family_intent.excluded_public_families):
        chosen = []
        for board in boards:
            master = find_master_board(board.brand, board.model) or {}
            public_family = board.authoritative_public_family or master.get("public_family")
            if family_intent.requested_public_family and public_family != family_intent.requested_public_family:
                continue
            if public_family in family_intent.excluded_public_families:
                continue
            board.authoritative_public_family = public_family
            board.detailed_category = board.detailed_category or master.get("detailed_category")
            board.primary_fin_setup = board.primary_fin_setup or master.get("primary_fin_setup")
            board.alternative_fin_setup = board.alternative_fin_setup or list(master.get("alternative_fin_setup") or [])
            board.recommendation_lanes = board.recommendation_lanes or list(master.get("recommendation_lanes") or [])
            board.excluded_recommendation_lanes = (
                board.excluded_recommendation_lanes
                or list(master.get("excluded_recommendation_lanes") or [])
            )
            board.match_reason = board.match_reason or "explicit_public_family"
            board.recommendation_role = "primary"
            chosen.append(board)
        return chosen if limit is None else chosen[:limit]

    primary, secondary = _shortlist_family_buckets(category, profile, message)
    if not boards or not primary:
        return boards if limit is None else boards[:limit]

    chosen = []
    seen = set()
    for board in boards:
        if board.category in primary:
            key = (board.brand.lower(), board.model.lower())
            if key not in seen:
                chosen.append(board)
                seen.add(key)
    if secondary and (limit is None or len(chosen) < limit):
        for board in boards:
            if board.category in secondary:
                key = (board.brand.lower(), board.model.lower())
                if key not in seen:
                    chosen.append(board)
                    seen.add(key)
    if not chosen:
        return boards if limit is None else boards[:limit]
    return chosen if limit is None else chosen[:limit]


def _family_education_reply(message: str) -> str | None:
    lowered = message.lower()
    if "difference" in lowered and "daily driver" in lowered and ("high performance" in lowered or "hpsb" in lowered):
        return (
            "Quivrr classifies Daily Drivers around everyday consistency: a broader usable wave range, more paddle support, "
            "and more accessible volume distribution. Performance Shortboards generally trade some of that forgiveness for "
            "more precise rails, rocker and responsiveness in better waves. Those are design-intent distinctions, not universal absolutes."
        )
    if not lowered.startswith("why"):
        return None
    board = find_requested_board(message)
    if not board:
        return None
    master = find_master_board(board["brand"], board["model"])
    if not master:
        return None
    family = master["public_family_label"]
    detail = master["detailed_category"]
    intent = master.get("manufacturer_intent") or "its governed manufacturer and design intent"
    return f"Quivrr classifies the {master['manufacturer']} {master['model']} as {family}, specifically {detail}, based on {intent}."


def _board_information_reply(board: dict, profile) -> str:
    """Present only governed intelligence for a resolved model; never defer to generic chat."""
    record = find_board_record(board["brand"], board["model"])
    master = find_master_board(board["brand"], board["model"]) or {}
    brand, model = board["brand"], board["model"]
    category = master.get("detailed_category") or (record.category if record else None) or "surfboard"
    parts = [f"{brand} {model} is a {category.replace('_', ' ')}."]
    if record and record.description:
        parts.append(record.description.rstrip(".") + ".")
    if record and record.ability_tags:
        parts.append(f"It is documented for {', '.join(record.ability_tags)} surfers.")
    if record and record.wave_types:
        parts.append(f"Its supported wave direction is {', '.join(record.wave_types)}.")
    if record and record.strengths:
        parts.append(f"Strengths: {', '.join(record.strengths)}.")
    if record and record.trade_offs:
        parts.append(f"Trade-offs: {', '.join(record.trade_offs)}.")
    dna = master.get("board_dna") or {}
    behaviour = dna.get("behaviour") or {}
    conditions = dna.get("conditions") or {}
    def character(field: str) -> str | None:
        value = behaviour.get(field)
        if not isinstance(value, (int, float)):
            return None
        return "high" if value >= 8 else "balanced" if value >= 5 else "limited"
    attributes = [
        ("paddle", "paddle character"), ("wave_entry", "wave entry"),
        ("speed_generation", "speed generation"), ("turning_radius", "turning radius"),
        ("hold", "hold"), ("forgiveness", "forgiveness"),
    ]
    documented = [f"{label}: {character(field)}" for field, label in attributes if character(field)]
    if documented:
        parts.append("Governed design signals — " + "; ".join(documented) + ".")
    wave_fit = [label for field, label in (("weak_waves", "weak surf"), ("average_waves", "average surf"), ("powerful_waves", "powerful surf")) if conditions.get(field, 0) >= 7]
    if wave_fit:
        parts.append(f"Its stronger documented wave fit is {', '.join(wave_fit)}.")
    if profile.ability and record and record.ability_tags:
        ability = profile.ability.lower()
        if ability not in {item.lower() for item in record.ability_tags}:
            parts.append(f"Based on your saved {profile.ability.lower()} profile, I would be cautious: it is not documented as an ideal fit for that ability.")
        else:
            parts.append(f"At your {profile.ability.lower()} level, it is a relevant board to consider; I would still need your weight and normal waves for a reliable size call.")
    if profile.current_volume_litres or profile.target_volume_litres:
        volume = profile.current_volume_litres or profile.target_volume_litres
        parts.append(f"Your current {volume:g}L reference is useful context, but it is not enough on its own to prescribe an exact size.")
    if profile.region:
        parts.append(f"I have not checked live {profile.region} stock for this model; ask and I’ll run a regional availability check.")
    return " ".join(parts)


def _resolved_board_suggestion(board: dict) -> SuggestedBoard:
    record = find_board_record(board["brand"], board["model"])
    master = find_master_board(board["brand"], board["model"]) or {}
    return SuggestedBoard(
        brand=board["brand"], model=board["model"],
        category=master.get("detailed_category") or (record.category if record else None) or "Surfboard",
        confidence=record.source_confidence if record else .75,
        why_it_fits="The board you asked about.",
        description=record.description if record else None,
        short_description=record.short_description if record else None,
        skill_fit=", ".join(record.ability_tags) if record and record.ability_tags else None,
        wave_range=", ".join(record.wave_types) if record and record.wave_types else None,
        board_model_id=board.get("boardModelId"),
        authoritative_public_family=master.get("public_family"),
        detailed_category=master.get("detailed_category"),
        primary_fin_setup=master.get("primary_fin_setup"),
        source="quivrr_controlled_knowledge",
    )


_PROFILE_UPDATE_FIELDS = {
    "weight_kg": ("weightKg", "weight"),
    "height_cm": ("heightCm", "height"),
    "ability": ("ability", "ability"),
    "region": ("homeRegion", "home region"),
    "home_break_type": ("homeBreak", "home break"),
    "wave_type": ("waveType", "normal wave type"),
    "wave_size": ("waveSize", "normal wave size"),
    "current_board": ("currentBoard", "regular board"),
    "current_volume_litres": ("currentVolumeLitres", "usual volume"),
    "goal": ("surfingGoal", "surfing goal"),
}
_PROFILE_CONFIRMATION = re.compile(r"^\s*(?:yes|yep|yeah|do it|update it|that is right|that's right|please change it)\s*[!.]*\s*$", re.I)


def _persistent_profile_statement(message: str) -> bool:
    text = (message or "").lower()
    if re.search(r"\b(?:this week|today|borrowed|friend'?s|trip|holiday|for portugal)\b", text):
        return False
    return bool(re.search(
        r"\b(?:change my|update my|save my|set my|in my profile|my profile says|"
        r"remember that i am|i weigh|i am now|my current volume is|my usual board is|"
        r"now|moved|mostly surf|regular board|usual board|from now on|these days)\b",
        text,
    ))


def _explicit_profile_changes(message: str) -> dict[str, object]:
    """Capture explicit save/change language that is intentionally stricter than general fit extraction."""
    text = (message or "").lower()
    if not re.search(r"\b(?:change|update|save|set|profile|remember)\b", text):
        return {}
    changes = {}
    volume = re.search(r"\b(?:volume|litres?|lts?)\s*(?:to|is|at)?\s*(\d+(?:\.\d+)?)\s*(?:l|lt|lts|litres?)\b", text)
    if volume:
        changes["current_volume_litres"] = float(volume.group(1))
    weight = re.search(r"\b(?:weight(?:\s+in\s+my\s+profile)?[^\d]{0,24}|i\s*(?:am|weigh))\s*(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilograms?)\b", text)
    if weight:
        changes["weight_kg"] = int(float(weight.group(1)))
    return changes


def _profile_update_proposal(account_profile, current_profile, message: str) -> ProfileUpdateProposal | None:
    if not account_profile or not _persistent_profile_statement(message):
        return None
    fields, current_values, labels = {}, {}, []
    for profile_field, (api_field, label) in _PROFILE_UPDATE_FIELDS.items():
        if current_profile.field_provenance.get(profile_field) != "current_user":
            continue
        incoming = getattr(current_profile, profile_field, None)
        existing = getattr(account_profile, profile_field, None)
        if incoming in (None, "", [], {}) or incoming == existing:
            continue
        fields[api_field] = incoming
        current_values[api_field] = existing
        labels.append(label)
    if not fields:
        return None
    return ProfileUpdateProposal(
        proposalId=str(uuid.uuid4()),
        fields=fields,
        currentValues=current_values,
        message=f"I’ll use that change in this chat. Would you like me to update your saved My Quivrr {' and '.join(labels)} too?",
    )


def _profile_pending_action(proposal: ProfileUpdateProposal | dict | None) -> dict | None:
    if not proposal:
        return None
    parsed = ProfileUpdateProposal.model_validate(proposal)
    field, new_value = next(iter(parsed.fields.items()), (None, None))
    return {
        "type": "profile_update",
        "proposalId": parsed.proposal_id or str(uuid.uuid4()),
        "field": field,
        "oldValue": parsed.current_values.get(field) if field else None,
        "newValue": new_value,
        "fields": parsed.fields,
        "currentValues": parsed.current_values,
    }


def _active_board_inventory_response(board: dict, region: str, profile) -> tuple[list[SuggestedBoard], str, dict]:
    """Build a size-specific answer from the authoritative regional availability contract."""
    try:
        payload = model_availability(int(board["boardModelId"]), region)
    except Exception:
        # A failed read must never be represented as checked stock or take down the chat.
        return [], (
            f"I could not complete the verified {board['brand']} {board['model']} inventory check just now. "
            "I have not treated it as in stock."
        ), {"boardModelId": board["boardModelId"], "regionCode": region, "resultCount": 0}
    sizes = payload.get("availableSizes") or []
    display_region = _region_display_name(region)
    if not sizes:
        return [], (
            f"I could not find verified {board['brand']} {board['model']} stock in {display_region} right now. "
            "I haven’t invented a substitute link. I can show you the closest available alternative if you like."
        ), {"boardModelId": board["boardModelId"], "regionCode": region, "resultCount": 0}

    suggestions = []
    lines = []
    target = profile.current_volume_litres or profile.target_volume_litres
    for size in sizes[:6]:
        price = size.get("minimumPrice")
        currency = size.get("currency")
        price_text = f"{currency} {price:,.0f}" if price is not None and currency else "Price not listed"
        offer = next((item for item in size.get("offers", []) if item.get("retailerName") or item.get("manufacturerName")), {})
        seller = offer.get("retailerName") or offer.get("manufacturerName") or "verified inventory"
        specs = " x ".join(str(size.get(key) or "—") for key in ("length", "width", "thickness"))
        volume = size.get("volumeLitres")
        lines.append(f"{specs} | {volume:g}L | {size.get('construction') or 'construction not listed'} | {price_text} at {seller}" if volume is not None else f"{specs} | {price_text} at {seller}")
        suggested = SuggestedBoard(
            brand=board["brand"], model=board["model"], category="Verified regional size",
            confidence=0.98, why_it_fits="Verified exact-size regional inventory.",
            suggested_size=specs, board_model_id=board["boardModelId"], board_size_id=size.get("boardSizeId"),
            selected_construction=size.get("construction"), selected_volume_litres=volume,
            region=region, region_code=region, availability_checked=True,
            availability_status="available", available_count=len(size.get("offers") or []),
            manufacturer_direct_count=1 if size.get("manufacturerAvailable") else 0,
            retailer_count=int(size.get("retailerCount") or 0), inventory_match_count=len(size.get("offers") or []),
            exact_size_inventory_count=len(size.get("offers") or []), exact_size_stock=True,
            model_level_stock=True, price_range=price_text,
            example_live_source_url=offer.get("productUrl"),
            source_product_url=offer.get("productUrl"),
        )
        suggestions.append(suggested.model_copy(update={
            "quivrr_search_url": quivrr_search_url(suggested, region, size),
        }))
    closest = ""
    if target is not None:
        closest_size = min((item for item in sizes if item.get("volumeLitres") is not None), key=lambda item: abs(float(item["volumeLitres"]) - target), default=None)
        if closest_size:
            closest = f" Your saved reference is {target:g}L, so {closest_size.get('length') or 'that size'} at {closest_size['volumeLitres']:g}L is the closest match."
    reply = f"Yes. I found the {board['brand']} {board['model']} in {display_region} in these verified sizes: " + "; ".join(lines) + closest + " Choose a size to open that exact Quivrr search."
    return suggestions, reply, {"boardModelId": board["boardModelId"], "regionCode": region, "resultCount": len(suggestions)}


def _stock_only_reply(label: str, region: str | None, boards, candidate_count: int | None = None, checked=None) -> str:
    region_name = _region_display_name(region)
    model_count = len(boards)
    volumes = [board.selected_volume_litres for board in boards if board.selected_volume_litres is not None]
    volume_note = f" between {min(volumes):g} and {max(volumes):g}L" if volumes else ""
    if model_count == 1:
        board = boards[0]
        size_note = (
            f" close to {board.selected_volume_litres:g}L" if board.exact_size_stock and board.selected_volume_litres is not None
            else ", although I have only verified model-level stock rather than the exact size"
        )
        return f"I found one suitable {label} with verified stock in {region_name}{size_note}."
    if model_count > 1:
        return f"I found {model_count} {label} models with verified stock in {region_name}{volume_note} that fit this brief."
    if checked and not any(board.availability_checked for board in checked):
        return f"I couldn’t verify {region_name} stock because the live inventory check did not return a usable response."
    if candidate_count:
        return f"I found matching {label} models, but none had verified {region_name} stock at this size or volume. I widened the board family before stopping."
    return f"I didn’t find an exact governed {label} match, so I widened the search rather than treating that as an inventory failure."


def _region_display_name(value: str | None) -> str:
    return REGION_DISPLAY_NAMES.get((value or "").upper(), value or "your region")


def _resolve_request_category(request_message: str, profile, *, allow_follow_up_profile_category: bool = False) -> CategoryResolution:
    category = extract_category(request_message)
    if category:
        return CategoryResolution(category=category, confidence=0.94, source="explicit_user_request")
    if allow_follow_up_profile_category and profile.preferred_board_type:
        follow_up_category = extract_category(profile.preferred_board_type)
        if follow_up_category:
            return CategoryResolution(category=follow_up_category, confidence=0.72, source="conversation_follow_up")
    if "weak wave" in request_message.lower() or "small wave" in request_message.lower():
        return CategoryResolution(category=None, confidence=0.2, source="unknown")
    return CategoryResolution(category=None, confidence=0.0, source="unknown")


def _clarifying_category_reply(request_message: str) -> tuple[str, list[str]]:
    lowered = request_message.lower()
    if "weak" in lowered or "small wave" in lowered:
        question = "Do you want easier paddling and speed, or something that still feels more performance-focused?"
        return question, [question]
    question = "What kind of board are we looking for: fish, small-wave board, daily driver, performance shortboard, step-up, or mid-length?"
    return question, [question]


def _should_clarify_category(request_message: str, category: str | None, requested_board, intent_result) -> bool:
    if category or requested_board:
        return False
    lowered = request_message.lower()
    explicit_board_language = any(
        phrase in lowered
        for phrase in (
            "want a",
            "want an",
            "want something",
            "looking for",
            "show me",
            "find me",
            "need a",
            "need an",
            "need something",
            "new board",
            "next board",
            "what should i ride",
            "recommend",
        )
    )
    ambiguous_wave_request = ("weak" in lowered or "small wave" in lowered) and "board" not in lowered and "fish" not in lowered
    return explicit_board_language and (intent_result.needs_clarification or ambiguous_wave_request)


def _state_cards(request: BoardGuideRequest):
    if not request.conversation_state:
        return []
    return [_normalise_active_recommendation(card) for card in request.conversation_state.last_recommendations or []]


def _state_card_index(message: str) -> int | None:
    import re
    lowered = message.lower()
    ordinals = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
        "sixth": 5,
        "top one": 0,
    }
    match = re.search(r"\b(?:number|#)\s*(\d+)\b", lowered)
    if match:
        return max(int(match.group(1)) - 1, 0)
    for token, index in ordinals.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return index
    return None


def _state_card_pair(message: str) -> tuple[int, int] | None:
    import re
    lowered = message.lower()
    ordinal_number = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
    }
    match = re.search(r"\bcompare\s+(?:number\s+)?(\d+)\s+(?:and|&)\s+(?:number\s+)?(\d+)\b", lowered)
    if match:
        return max(int(match.group(1)) - 1, 0), max(int(match.group(2)) - 1, 0)
    match = re.search(r"\bcompare\s+(?:the\s+)?(first|second|third|fourth|fifth|sixth)\s+(?:and|&)\s+(?:the\s+)?(first|second|third|fourth|fifth|sixth)\b", lowered)
    if match:
        return ordinal_number[match.group(1)] - 1, ordinal_number[match.group(2)] - 1
    if "top two" in lowered:
        return 0, 1
    return None


def _requested_card_limit(message: str) -> int | None:
    import re

    lowered = message.lower()
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
    }
    if match := re.search(r"\b([1-6])\b", lowered):
        return int(match.group(1))
    for word, value in number_words.items():
        if re.search(rf"\b{word}\b", lowered):
            return value
    return None


def _card_to_requested_board(card):
    return {"brand": card.brand, "model": card.model}


def _normalise_active_recommendation(card) -> BodhiRecommendation:
    if isinstance(card, BodhiRecommendation):
        return card
    if isinstance(card, SuggestedBoard):
        return public_recommendations([card])[0]
    if isinstance(card, dict):
        return BodhiRecommendation.model_validate(card)
    raise TypeError(f"Unsupported active recommendation record: {type(card)!r}")


def _card_to_suggested_board(card) -> SuggestedBoard:
    card = _normalise_active_recommendation(card)
    return SuggestedBoard(
        brand=card.brand,
        model=card.model,
        category=card.category,
        confidence=card.confidence,
        why_it_fits=card.short_reason or card.why_it_fits,
        region=card.region,
        region_code=card.region_code,
        quivrr_search_url=card.search_url or card.quivrr_search_url,
        available_count=card.available_count,
        manufacturer_direct_count=card.manufacturer_match_count,
        retailer_count=card.retailer_match_count,
        availability_checked=card.availability_checked,
        availability_status=card.availability_status,
        inventory_source=card.inventory_source,
        inventory_match_count=card.inventory_match_count,
        authoritative_public_family=card.authoritative_public_family,
        detailed_category=card.detailed_category,
        primary_fin_setup=card.primary_fin_setup,
        alternative_fin_setup=card.alternative_fin_setup,
        recommendation_lanes=card.recommendation_lanes,
        excluded_recommendation_lanes=card.excluded_recommendation_lanes,
        match_reason=card.match_reason,
        recommendation_role=card.recommendation_role,
    )


def _detail_reply(card) -> str:
    record = find_board_record(card.brand, card.model)
    if not record:
        return (
            f"{card.brand} {card.model} sits in the {card.category.lower()} lane. "
            f"It suits this brief because {card.short_reason or card.why_it_fits}. "
            "Want the design details, sizing guidance, similar boards, or availability?"
        )
    what_it_is = f"{record.brand} {record.model} is a {record.category or card.category}."
    conditions = f"Best in {', '.join(record.wave_types[:2])} waves." if record.wave_types else "Best when you want a clean fit for the same brief."
    feel = f"It tends to feel {', '.join(record.feel_tags[:3])}." if record.feel_tags else f"It should feel {card.short_reason or card.why_it_fits}."
    rider = f"It suits {', '.join(record.ability_tags[:2])} surfers." if record.ability_tags else "It suits the rider profile we have so far."
    trade_off = f"The main trade-off is {record.trade_offs[0]}." if record.trade_offs else "The main trade-off is that it stays specific to its lane."
    return " ".join([what_it_is, conditions, feel, rider, trade_off, "Want the design details, sizing guidance, similar boards, or availability?"])


def _best_paddler_reply(cards) -> str:
    scored = []
    for card in cards:
        record = find_board_record(card.brand, card.model)
        paddle = 0
        if record:
            paddle = record.design_scores.get("paddle") or record.design_scores.get("paddle_power") or 0
        scored.append((paddle, card))
    scored.sort(key=lambda item: (-item[0], item[1].brand.lower(), item[1].model.lower()))
    best = scored[0][1]
    return (
        f"Within this active shortlist, {best.brand} {best.model} looks like the strongest paddler. "
        "If you want, I can rank the rest of the set for paddle help, weak-wave speed, or forgiveness."
    )


def _comparison_follow_up_reply(left_card, right_card, profile: BoardGuideRequest | None = None):
    result = compare_board_models(left_card.brand, left_card.model, right_card.brand, right_card.model, profile)
    if not result:
        return f"{left_card.brand} {left_card.model} and {right_card.brand} {right_card.model} are the two boards in play. Want me to break down paddle power, forgiveness, or weak-wave performance?"
    left = result.left_fit.board if result.left_fit else None
    right = result.right_fit.board if result.right_fit else None
    paddle_winner = None
    if left and right:
        left_paddle = left.design_scores.get("paddle") or left.design_scores.get("paddle_power") or 0
        right_paddle = right.design_scores.get("paddle") or right.design_scores.get("paddle_power") or 0
        if left_paddle > right_paddle:
            paddle_winner = f"{left.brand} {left.model} has the stronger paddle bias."
        elif right_paddle > left_paddle:
            paddle_winner = f"{right.brand} {right.model} has the stronger paddle bias."
    parts = [
        f"Comparing {left_card.brand} {left_card.model} and {right_card.brand} {right_card.model}.",
        f"Paddle power: {paddle_winner or 'They are close, but the more forgiving board usually wins on easier entry.'}",
        f"Speed: {result.comparison.differences[0] if result.comparison.differences else 'They split speed differently through their lanes.'}",
        f"Forgiveness: {result.comparison.better_for_board_a[0] if result.comparison.better_for_board_a else result.comparison.better_for_board_b[0] if result.comparison.better_for_board_b else 'The easier board is the one that asks less of your positioning.'}",
        f"Main trade-off: {result.comparison.rider_specific_conclusion or 'One is cleaner for this rider brief.'}",
    ]
    return " ".join(parts)


def _handle_state_follow_up(request: BoardGuideRequest, profile, directive: ConversationDirective):
    message = request.message.strip()
    lowered = message.lower()
    cards = _state_cards(request)
    if not cards:
        return None

    if directive.needs_reference_clarification:
        names = ", ".join(f"{card.brand} {card.model}" for card in cards[:3])
        return {
            "reply": f"Which board do you mean: {names}?",
            "suggested_boards": [],
            "comparison": None,
            "questions": ["Which board do you mean?"],
        }

    if directive.rejected_board:
        remaining_cards = [
            card for card in cards
            if (card.brand.lower(), card.model.lower()) != (
                directive.rejected_board.brand.lower(), directive.rejected_board.model.lower()
            )
        ]
        if directive.refinement in {"more_paddle", "more_forgiving"}:
            score_name = "paddle_score" if directive.refinement == "more_paddle" else "forgiveness_score"
            remaining_cards.sort(
                key=lambda card: getattr(find_board_record(card.brand, card.model), score_name, 0) or 0,
                reverse=True,
            )
        remaining = [_card_to_suggested_board(card) for card in remaining_cards[:3]]
        direction = {
            "more_paddle": " and moved the easier-paddling options up",
            "more_forgiving": " and moved the more forgiving options up",
            "more_performance": " and kept the sharper alternatives",
        }.get(directive.refinement, "")
        reply = (
            f"Fair call. I’ve removed {directive.rejected_board.brand} {directive.rejected_board.model}{direction}."
            if remaining else
            f"Fair call. I’ve removed {directive.rejected_board.brand} {directive.rejected_board.model}. Tell me what felt wrong and I’ll take a different direction."
        )
        return {"reply": reply, "suggested_boards": remaining, "comparison": None, "questions": []}

    if directive.refinement in {"more_paddle", "more_forgiving"}:
        score_name = "paddle_score" if directive.refinement == "more_paddle" else "forgiveness_score"
        ordered = sorted(
            cards,
            key=lambda card: getattr(find_board_record(card.brand, card.model), score_name, 0) or 0,
            reverse=True,
        )
        suggested = [_card_to_suggested_board(card) for card in ordered[:3]]
        label = "paddle support" if directive.refinement == "more_paddle" else "forgiveness"
        return {
            "reply": f"I’ve reordered the active shortlist around {label} without changing your original wave brief.",
            "suggested_boards": suggested,
            "comparison": None,
            "questions": [],
        }

    if re.search(r"\bwhy (?:do|would) (?:these|they) (?:suit|fit|work)", lowered):
        detailed_category = next((card.detailed_category for card in cards if card.detailed_category), None)
        family_label = detailed_category or cards[0].category
        target = f" Around {profile.target_volume_litres:g}L," if profile.target_volume_litres else ""
        reply = (
            f"They stay inside the {family_label} category you asked for."
            f"{target} the closest viable sizes preserve that design's intended feel; "
            "the card notes explain each board's specific trade-off."
        )
        return {"reply": reply, "suggested_boards": [], "comparison": None, "questions": []}

    index = _state_card_index(message)
    if index is not None and index >= len(cards):
        return {
            "reply": f"I only have {len(cards)} boards in the current shortlist. Pick 1 to {len(cards)}.",
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }
    if index is not None and 0 <= index < len(cards) and ("tell me about" in lowered or "what is" in lowered):
        return {"reply": _detail_reply(cards[index]), "suggested_boards": [], "comparison": None, "questions": []}

    pair = _state_card_pair(message)
    if pair and (pair[0] >= len(cards) or pair[1] >= len(cards)):
        return {
            "reply": f"I only have {len(cards)} boards in the current shortlist. Pick 1 to {len(cards)}.",
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }
    if pair and pair[0] < len(cards) and pair[1] < len(cards):
        left_card = cards[pair[0]]
        right_card = cards[pair[1]]
        comparison = compare_board_models(left_card.brand, left_card.model, right_card.brand, right_card.model, profile)
        reply = _comparison_follow_up_reply(left_card, right_card, profile)
        return {
            "reply": reply,
            "suggested_boards": [],
            "comparison": comparison.comparison if comparison else None,
            "questions": [],
            "comparison_boards": [left_card, right_card],
        }

    if "trade off" in lowered or "trade-off" in lowered:
        if len(cards) >= 2:
            left_card, right_card = cards[:2]
            comparison = compare_board_models(left_card.brand, left_card.model, right_card.brand, right_card.model, profile)
            return {
                "reply": _comparison_follow_up_reply(left_card, right_card, profile),
                "suggested_boards": [],
                "comparison": comparison.comparison if comparison else None,
                "questions": [],
                "comparison_boards": [left_card, right_card],
            }

    if any(token in lowered for token in ("which paddles best", "which one paddles best")) and len(cards) >= 2:
        if request.conversation_state and len(request.conversation_state.comparison_boards) >= 2:
            left_card = request.conversation_state.comparison_boards[0]
            right_card = request.conversation_state.comparison_boards[1]
            return {
                "reply": _comparison_follow_up_reply(left_card, right_card, profile),
                "suggested_boards": [],
                "comparison": None,
                "questions": [],
                "comparison_boards": [left_card, right_card],
            }
        return {
            "reply": _best_paddler_reply(cards),
            "suggested_boards": [],
            "comparison": None,
            "questions": [],
        }

    if "remove pyzel" in lowered:
        remaining = [_card_to_suggested_board(card) for card in cards if card.brand.lower() != "pyzel"]
        reply = "I’ve taken Pyzel out of the active set." if remaining else "Taking Pyzel out leaves no active boards in this set."
        return {"reply": reply, "suggested_boards": remaining, "comparison": None, "questions": []}

    if _message_requests_stock_only(message):
        target_region = profile.region or request.region
        verified = [_card_to_suggested_board(card) for card in cards]
        inventory_profile = profile if profile.region else profile.model_copy(update={"region": target_region})
        checked = enrich_suggestions_with_inventory(verified, inventory_profile) if target_region and verified else []
        filtered = [row for row in checked if row.available_count > 0]
        region_name = _region_display_name(target_region)
        if filtered:
            reply = f"I filtered the active set to boards with verified current availability in {region_name}."
            suggested = filtered
        else:
            reply = (
                f"I couldn’t verify live {region_name} stock for those boards right now. "
                "These remain the best catalogue matches for the category you asked for."
            )
            suggested = verified[:3]
        return {"reply": reply, "suggested_boards": suggested, "comparison": None, "questions": []}

    return None


def build_follow_up_actions(intent: str, boards: list) -> list[FollowUpAction]:
    if intent == "BOARD_RECOMMENDATION" and boards:
        top_two = boards[:2]
        labels = [
            FollowUpAction(id="compare_top_two", label="Compare top two", prompt=f"Compare {top_two[0].brand} {top_two[0].model} and {top_two[1].brand} {top_two[1].model}") if len(top_two) >= 2 else None,
            FollowUpAction(id="only_in_stock", label="Only in stock", prompt="Only show the ones in stock"),
            FollowUpAction(id="more_paddle", label="More paddle power", prompt="Show me the ones with more paddle power"),
            FollowUpAction(id="details_first", label="Tell me more", prompt=f"Tell me about {boards[0].brand} {boards[0].model}"),
        ]
        return [item for item in labels if item is not None]
    if intent == "BOARD_COMPARISON":
        return [
            FollowUpAction(id="paddle_best", label="Which paddles best?", prompt="Which one paddles best?"),
            FollowUpAction(id="more_forgiving", label="Which is more forgiving?", prompt="Which one is more forgiving?"),
        ]
    if intent == "AVAILABILITY":
        return [FollowUpAction(id="open_region_search", label="Open region search", prompt="Show me similar boards in this region")]
    return []


def build_conversation_state(
    request: BoardGuideRequest,
    profile,
    normalized_intent: str,
    public_cards: list,
    questions: list[str],
    availability_constraint: str | None = None,
    comparison_boards_override: list | None = None,
    directive: ConversationDirective | None = None,
    authenticated: bool = False,
    family_intent: FamilyIntent | None = None,
    previous_outcome: str | None = None,
    previous_failure_reason: str | None = None,
    previous_reply_signature: str | None = None,
    pending_profile_update: dict | None = None,
    pending_action: dict | None = None,
    pending_clarification: dict | None = None,
    surfer_stage: str | None = None,
    active_board_override: dict | None = None,
    last_inventory_query: dict | None = None,
    clear_response_plan: bool = False,
    correction_detected: bool = False,
) -> ConversationState:
    active_region = profile.region or request.region
    last_question = questions[0] if questions else None
    previous_state = request.conversation_state
    previous_turn = previous_state.conversation_turn if previous_state else 0
    clear_previous = (
        bool(directive and directive.clears_rider_brief)
        or normalized_intent.startswith("PLATFORM_")
        or clear_response_plan
    )
    previous_recommendations = previous_state.last_recommendations if previous_state and not clear_previous else []
    mentioned = previous_state.mentioned_boards if previous_state and not clear_previous else []
    comparison_boards = previous_state.comparison_boards if previous_state and not clear_previous else []
    if comparison_boards_override:
        comparison_boards = [_normalise_active_recommendation(card) for card in comparison_boards_override]
    if normalized_intent == "BOARD_COMPARISON" and len(public_cards) >= 2:
        comparison_boards = public_cards[:2]
    last_recommendations = public_cards[:6] or previous_recommendations[:6]
    previous_brief = previous_state.active_board_brief if previous_state and not clear_previous else {}
    active_board = active_board_override or (previous_state.active_board if previous_state and not clear_previous else None)
    inventory_query = last_inventory_query or (previous_state.last_inventory_query if previous_state and not clear_previous else None)
    active_board_brief = resolve_dna_brief(request.message, profile, previous_brief)
    if re.search(r"\b(?:reset|start over|new search|clear)\b", request.message.lower()):
        active_board_brief = {}
    correction = _model_classification_correction(request.message)
    if correction:
        active_board_brief["public_family"] = correction["dna"]["public_family"]
    discussed = [] if clear_previous else list(previous_state.boards_discussed if previous_state else [])
    for card in last_recommendations:
        reference = BoardReference(brand=card.brand, model=card.model)
        if not any(item.brand.lower() == reference.brand.lower() and item.model.lower() == reference.model.lower() for item in discussed):
            discussed.append(reference)
    rejected = [] if clear_previous else list(previous_state.rejected_recommendations if previous_state else [])
    if directive and directive.rejected_board:
        rejected.append({
            "brand": directive.rejected_board.brand,
            "model": directive.rejected_board.model,
            "reason": directive.rejection_reason or "user_rejected",
        })
    rejected = list({(item["brand"].lower(), item["model"].lower()): item for item in rejected}.values())
    preferred_families = [] if clear_previous else list(previous_state.preferred_families if previous_state else [])
    if active_board_brief.get("public_family") and active_board_brief["public_family"] not in preferred_families:
        preferred_families.append(active_board_brief["public_family"])
    fin_setups = [] if clear_previous else list(previous_state.preferred_fin_setups if previous_state else [])
    for fin in ("twin", "thruster", "quad", "2+1"):
        if re.search(rf"\b{re.escape(fin)}\b", request.message.lower()) and fin not in fin_setups:
            fin_setups.append(fin)
    return ConversationState(
        lastIntent=normalized_intent,
        activeRegion=active_region,
        availabilityConstraint=availability_constraint,
        activeProfile=profile.model_dump(exclude={"profile_sources", "profile_conflicts", "field_provenance"}, exclude_none=True),
        activeBoardBrief=active_board_brief,
        activeBoard=active_board,
        lastInventoryQuery=inventory_query,
        lastRecommendations=last_recommendations,
        mentionedBoards=(last_recommendations or mentioned[:8]),
        comparisonBoards=comparison_boards[:4],
        lastQuestion=last_question,
        conversationTurn=previous_turn + 1,
        phase=directive.phase if directive else "DISCOVERY",
        currentTopic=active_board_brief.get("public_family") or normalized_intent.lower(),
        targetSurfer=directive.target_surfer if directive else "account_holder",
        authenticated=authenticated,
        preferredName=(profile.display_name.split()[0] if authenticated and profile.display_name else None),
        boardsDiscussed=discussed[:20],
        rejectedRecommendations=rejected[:20],
        lastUnresolvedQuestion=last_question,
        preferredFamilies=preferred_families,
        preferredFinSetups=fin_setups,
        goals=[profile.goal] if profile.goal else [],
        painPoints=[profile.current_board_feedback] if profile.current_board_feedback else [],
        requestedPublicFamily=family_intent.requested_public_family if family_intent else None,
        requestedDetailedCategory=family_intent.requested_detailed_category if family_intent else None,
        requestedFinSetup=family_intent.requested_fin_setup if family_intent else None,
        excludedPublicFamilies=list(family_intent.excluded_public_families) if family_intent else [],
        excludedDetailedCategories=list(family_intent.excluded_detailed_categories) if family_intent else [],
        excludedFinSetups=list(family_intent.excluded_fin_setups) if family_intent else [],
        allowAdjacentAlternatives=family_intent.allow_adjacent_alternatives if family_intent else False,
        lastRejectedModels=[
            BoardReference(brand=item["brand"], model=item["model"])
            for item in rejected[-6:]
        ],
        lastRejectedFamily=(
            family_intent.excluded_public_families[-1]
            if family_intent and family_intent.excluded_public_families else None
        ),
        familyCorrectionReason=family_intent.correction_reason if family_intent else None,
        familyIntentConfidence=family_intent.confidence if family_intent else 0.0,
        stockFilterRequested=availability_constraint == STOCK_ONLY_CONSTRAINT,
        stockCheckOffered=bool(
            last_recommendations and active_region and availability_constraint != STOCK_ONLY_CONSTRAINT
        ),
        stockCheckAccepted=availability_constraint == STOCK_ONLY_CONSTRAINT,
        lastPresentedCategory=(
            family_intent.requested_detailed_category or family_intent.requested_public_family
            if family_intent else active_board_brief.get("public_family")
        ),
        lastPresentedModels=[
            BoardReference(brand=item.brand, model=item.model)
            for item in last_recommendations[:6]
        ],
        correctionDetected=correction_detected or bool(family_intent and family_intent.correction),
        previousOutcome=previous_outcome,
        previousSearchConstraints={
            "region": active_region,
            "category": family_intent.requested_public_family if family_intent else active_board_brief.get("public_family"),
            "stockOnly": availability_constraint == STOCK_ONLY_CONSTRAINT,
            "targetVolumeLitres": profile.target_volume_litres,
        },
        previousFailureReason=previous_failure_reason,
        previousReplySignature=previous_reply_signature,
        pendingProfileUpdate=pending_profile_update,
        pendingAction=pending_action,
        pendingClarification=pending_clarification,
        surferStage=surfer_stage,
    )


def _customer_manufacturer_name(canonical: str) -> str:
    return {
        "AIPA Surf": "AIPA",
        "Timmy Patterson Surfboards": "Timmy Patterson",
    }.get(canonical, canonical)


def _expansion_catalogue_suggestions(brand: str, category: str | None = None) -> list[SuggestedBoard]:
    rows = models_for_manufacturer(brand)
    if category == "fish":
        rows = [
            row for row in rows
            if re.search(r"\bfish\b", f"{row.get('model', '')} {row.get('official_description', '')}", re.I)
        ]
    output = []
    for row in rows:
        sizes = row.get("sizes") or []
        volumes = [size.get("volume_litres") for size in sizes if isinstance(size.get("volume_litres"), (int, float))]
        volume_range = f"{min(volumes):g}-{max(volumes):g}L" if volumes else None
        output.append(SuggestedBoard(
            brand=row["manufacturer"],
            model=row["model"],
            category="Official model information",
            confidence=0.9,
            why_it_fits=(
                "The official model information references a fish design; Quivrr has not assigned an editorial family"
                if category == "fish" else
                "The model is present in the governed manufacturer catalogue"
            ),
            description=row.get("official_description"),
            volume_range=volume_range,
            source_product_url=row.get("official_product_url"),
        ))
    return output


def get_allowed_origins() -> list[str]:
    origins = os.getenv("BOARD_GUIDE_ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


app = FastAPI(title=APP_NAME)

emit_event(
    "bodhi_startup",
    "bodhi_api",
    status="success",
    build=BUILD_SHA,
    git_sha=BUILD_GIT_SHA,
    recommendation_engine=RECOMMENDATION_ENGINE_NAME,
    startup_time=STARTUP_TIME_UTC,
    deployment_id=DEPLOYMENT_ID,
    module_name=__name__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins() or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health(response: Response):
    _set_debug_headers(response)
    return {
        "status": "ok",
        "service": APP_NAME,
        "persona": "Bodhi, the Core Lord",
        "azure_openai_configured": is_azure_openai_configured(),
        "stage2_model_recommendations": True,
        **_build_metadata(),
    }


@app.get("/api/manufacturer-intelligence")
def manufacturer_intelligence(response: Response):
    """Expose owner-approved evidence without presenting it as imported production data."""
    _set_debug_headers(response)
    catalogue = load_manufacturer_expansion_catalogue()
    return {
        "catalogueState": catalogue.get("catalogue_state", "unavailable"),
        "familyPolicy": "Unknown is retained where official public-family evidence is absent.",
        "manufacturers": list_manufacturers(),
        "constructionSummaries": construction_summaries(),
    }


@app.get("/api/manufacturer-intelligence/models")
def manufacturer_intelligence_models(response: Response, brand: str):
    _set_debug_headers(response)
    manufacturer_models = models_for_manufacturer(brand)
    if not manufacturer_models:
        raise HTTPException(status_code=404, detail="No canonical manufacturer models found.")
    return {
        "brand": manufacturer_models[0]["manufacturer"],
        "catalogueState": load_manufacturer_expansion_catalogue().get("catalogue_state", "unavailable"),
        "models": [model_summary(model) for model in manufacturer_models],
    }


@app.get("/api/manufacturer-intelligence/model")
def manufacturer_intelligence_model(response: Response, brand: str, model: str):
    _set_debug_headers(response)
    staged = find_staged_model(brand, model)
    if not staged:
        raise HTTPException(status_code=404, detail="No canonical model found.")
    return {**model_summary(staged), "officialDescription": staged["official_description"], "standardSizes": staged["sizes"]}


@app.get("/api/manufacturer-intelligence/compare")
def manufacturer_intelligence_compare(
    response: Response,
    left_brand: str,
    left_model: str,
    right_brand: str,
    right_model: str,
):
    _set_debug_headers(response)
    left = find_staged_model(left_brand, left_model)
    right = find_staged_model(right_brand, right_model)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Both canonical models are required for comparison.")
    return compare_staged_models(left, right)


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
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Bodhi-Build": BUILD_SHA,
            "X-Bodhi-Engine": RECOMMENDATION_ENGINE_NAME,
        },
    )


@app.post("/api/board-guide/chat", response_model=BoardGuideResponse)
def board_guide_chat(
    request: BoardGuideRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
):
    started = time.perf_counter()
    correlation_id = http_request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    try:
        request_attempt = max(1, int(http_request.headers.get("X-Bodhi-Attempt", "1")))
    except ValueError:
        request_attempt = 1
    http_request.state.correlation_id = correlation_id
    response.headers["X-Correlation-ID"] = correlation_id
    recommendation_path = "unresolved"
    ranking_engine_used = "none"
    candidate_source = "none"
    inventory_stage = "not_run"
    candidate_count_before_inventory = 0
    active_inventory_query = None
    emit_event(
        "bodhi_request_received",
        "bodhi_api",
        region=request.region,
        status="success",
        source="deterministic_intake_engine",
        build=BUILD_SHA,
        conversation_turn_count=len(request.conversation),
        authenticated=bool(authorization),
        request_attempt=request_attempt,
        correlation_id=correlation_id,
    )
    auth_context = load_authenticated_profile_context(authorization, correlation_id=correlation_id)
    intent_result = classify_intent(request.message)
    if request.event_type == "AUTH_STATE_UPDATE":
        intent_result = IntentResult("AUTH_STATE_UPDATE", "site_help_question", 1.0, {"eventType": request.event_type})
    topic_route = classify_topic_route(request.message)
    language_tone = classify_language_tone(request.message)
    recovery_kind = follow_up_kind(
        request.message,
        request.conversation_state.previous_outcome if request.conversation_state else None,
    )
    if request_attempt > 1:
        emit_event(
            "bodhi_request_retry",
            "bodhi_api",
            region=request.region,
            status="retry",
            request_attempt=request_attempt,
            intent=intent_result.intent,
            correlation_id=correlation_id,
        )
    directive = control_conversation(request.message, intent_result.intent, request.conversation_state)
    family_intent = resolve_family_intent(
        request.message,
        request.conversation_state,
        reset=directive.clears_rider_brief,
    )
    # A platform/inventory question is a new object of conversation. Do not let a
    # previous rider brief regenerate recommendations for it.
    preserve_prior_rider = not directive.clears_rider_brief and not topic_route.pivot
    history_profiles = [
        with_profile_source(extract_profile(item.content, request.region), "conversation_user")
        for item in request.conversation if preserve_prior_rider and item and item.role == "user" and item.content
    ]
    legacy_account_profile = (
        with_profile_source(request.account_profile, "conversation_profile")
        if request.account_profile and preserve_prior_rider else None
    )
    retain_supplied_profile = preserve_prior_rider or directive.target_surfer == "account_holder"
    persisted_profile = with_profile_source(
        (request.profile or request.intake_state or extract_profile("")) if retain_supplied_profile else extract_profile(""),
        "conversation_profile",
    )
    if preserve_prior_rider and request.conversation_state and request.conversation_state.active_profile:
        restored_profile = with_profile_source(
            type(persisted_profile).model_validate(request.conversation_state.active_profile),
            "conversation_profile",
        )
        persisted_profile = merge_rider_profile(restored_profile, persisted_profile)
    if legacy_account_profile:
        persisted_profile = merge_rider_profile(legacy_account_profile, persisted_profile)
    account_profile = auth_context.profile if auth_context.profile else None
    if directive.clears_rider_brief and directive.target_surfer == "different_surfer":
        profile = extract_profile("").model_copy(update={
            "display_name": account_profile.display_name if account_profile else None,
            "region": request.region or (account_profile.region if account_profile else None),
        })
    else:
        profile = account_profile or extract_profile("")
    for historical in history_profiles:
        profile = merge_rider_profile(profile, historical)
    profile = merge_rider_profile(
        profile,
        persisted_profile,
        account_profile=account_profile if preserve_prior_rider else None,
    )
    current_profile = with_profile_source(extract_profile(request.message, request.region), "current_user")
    explicit_profile_changes = _explicit_profile_changes(request.message)
    if explicit_profile_changes:
        current_profile = current_profile.model_copy(update={
            **explicit_profile_changes,
            "field_provenance": {**current_profile.field_provenance, **{field: "current_user" for field in explicit_profile_changes}},
        })
    profile = merge_rider_profile(
        profile,
        current_profile,
        account_profile=account_profile if preserve_prior_rider else None,
    )
    profile_update_proposal = _profile_update_proposal(account_profile, current_profile, request.message)
    pending_profile_update = profile_update_proposal.model_dump(by_alias=True) if profile_update_proposal else (
        request.conversation_state.pending_profile_update if request.conversation_state else None
    )
    prior_pending_action = request.conversation_state.pending_action if request.conversation_state else None
    pending_action = (
        _profile_pending_action(profile_update_proposal)
        if profile_update_proposal
        else (prior_pending_action or _profile_pending_action(pending_profile_update))
    )
    semantic_decision = decide_conversation(
        request.message,
        normalized_intent=intent_result.intent,
        topic_kind=topic_route.kind,
        state=request.conversation_state,
        event_type=request.event_type,
        profile_change_requested=bool(profile_update_proposal),
        has_conversation_history=bool(request.conversation or request.intake_state),
    )
    profile_update_confirmation_requested = bool(
        pending_profile_update and semantic_decision.candidate_tool == "confirm_profile_update"
    )
    if profile_update_confirmation_requested:
        profile_update_proposal = ProfileUpdateProposal.model_validate(pending_profile_update)
        pending_profile_update = None
        pending_action = None
    elif pending_profile_update and semantic_decision.candidate_tool == "reject_profile_update":
        pending_profile_update = None
        pending_action = None
    stage_assessment = assess_surfer_stage(
        request.message,
        profile.ability,
        request.conversation_state.pending_clarification if request.conversation_state else None,
    )
    if stage_assessment.stage:
        profile = profile.model_copy(update={"surfer_stage": stage_assessment.stage})
    reset_requested = directive.clears_rider_brief
    if family_intent.requested_public_family:
        preferred_type = family_intent.requested_detailed_category or PUBLIC_FAMILY_LABELS[family_intent.requested_public_family]
        profile = profile.model_copy(update={"preferred_board_type": preferred_type})
    dna_probe = resolve_dna_brief(request.message, profile, {})
    if (
        not reset_requested
        and not profile.preferred_board_type
        and (dna_probe.get("behaviour") or dna_probe.get("conditions"))
        and re.search(r"\b(?:board|something)\b", request.message.lower())
    ):
        profile = profile.model_copy(update={"preferred_board_type": "Daily Driver"})
    prior_brief = request.conversation_state.active_board_brief if request.conversation_state and preserve_prior_rider else {}
    if prior_brief.get("public_family") and not current_profile.preferred_board_type:
        profile = profile.model_copy(update={
            "preferred_board_type": {
                "fish": "fish", "groveller": "groveller", "daily_driver": "daily driver",
                "performance_shortboard": "performance shortboard", "step_up": "step up",
                "mid_length": "mid length", "longboard": "longboard",
            }.get(prior_brief["public_family"], profile.preferred_board_type)
        })
    volume_correction_requested = _volume_correction_requested(request.message)

    missing = missing_profile_fields(profile)
    legacy_intent = intent_result.legacy_intent
    intent = intent_result.intent
    if topic_route.kind not in {"CONTINUE_CURRENT_TOPIC", "NEW_GENERAL_TOPIC"}:
        legacy_intent = topic_route.kind.lower()
        intent = topic_route.kind
    acknowledgement_turn = bool(
        prior_pending_action
        or (request.conversation_state and request.conversation_state.pending_profile_update)
        or re.fullmatch(
            r"(?:ok(?:ay)?|thanks?|thank you|great|nice|cool|cheers|got it|sounds good|all good)(?:[,.! ]+(?:thanks?|thank you|great|nice|cool|cheers|got it|sounds good|all good))*[!. ]*",
            request.message.strip().lower(),
        )
    )
    if semantic_decision.interaction_type == "correction":
        # A correction invalidates any earlier response plan.  Other ordinary
        # turns retain their classified intent so stage safety and educational
        # replies can still run, while the action guard below prevents cards.
        legacy_intent = "site_help_question"
        intent = "NO_REQUEST"
    elif semantic_decision.interaction_type == "conversation" and acknowledgement_turn:
        # Acknowledgements close the current turn without creating a new rider
        # brief.  Preserve greetings and factual safety statements for their
        # existing specialised response paths.
        legacy_intent = "site_help_question"
    if recovery_kind and intent not in NON_RECOMMENDATION_GUARD_INTENTS:
        # A failed stock search is recoverable context, not a new generic question.
        legacy_intent = "board_search_request"
        intent = "BOARD_RECOMMENDATION"
    if reset_requested and family_intent.explicit and directive.target_surfer == "account_holder":
        legacy_intent = "board_search_request"
        intent = "BOARD_RECOMMENDATION"
    if family_intent.correction and intent not in NON_RECOMMENDATION_GUARD_INTENTS and not _family_education_reply(request.message):
        legacy_intent = "board_search_request"
        intent = "BOARD_RECOMMENDATION"
    stock_constraint_removed = _message_removes_stock_constraint(request.message)
    availability_constraint = _resolve_availability_constraint(request, intent_result)
    if recovery_kind and request.conversation_state and request.conversation_state.previous_search_constraints.get("stockOnly"):
        availability_constraint = STOCK_ONLY_CONSTRAINT
    if reset_requested:
        availability_constraint = None
    if (
        availability_constraint == STOCK_ONLY_CONSTRAINT
        and _message_requests_stock_only(request.message)
        and family_intent.requested_public_family
    ):
        legacy_intent = "board_search_request"
        intent = "BOARD_RECOMMENDATION"
    active_topic = resolve_active_topic(request, profile, legacy_intent)
    if active_topic.kind == "comparison" and active_topic.is_follow_up:
        legacy_intent = "comparison_request"
        intent = "BOARD_COMPARISON"
    allow_contextual_profile_category = semantic_decision.candidate_tool == "recommend_boards" and bool(
        request.profile or request.intake_state or request.conversation_state or request.conversation
    )
    category_resolution = _resolve_request_category(
        request.message,
        profile,
        allow_follow_up_profile_category=allow_contextual_profile_category,
    )
    if family_intent.requested_public_family:
        detailed_category_route = {
            "Traditional Fish": "traditional_fish",
            "Performance Fish": "performance_fish",
            "Performance Daily Driver": "performance_daily_driver",
            "Competition HPSB": "performance_shortboard",
        }.get(family_intent.requested_detailed_category or "")
        category_resolution = CategoryResolution(
            category=detailed_category_route or family_intent.requested_public_family,
            confidence=family_intent.confidence,
            source="family_correction" if family_intent.correction else (
                "explicit_user_request" if family_intent.explicit else "conversation_follow_up"
            ),
        )
    category = category_resolution.category
    prior_dna_brief = request.conversation_state.active_board_brief if request.conversation_state and preserve_prior_rider else {}
    resolved_dna_brief = resolve_dna_brief(request.message, profile, prior_dna_brief)
    if family_intent.requested_public_family:
        resolved_dna_brief["public_family"] = family_intent.requested_public_family
    resolved_dna_brief["excluded_public_families"] = list(family_intent.excluded_public_families)
    if family_intent.requested_fin_setup:
        resolved_dna_brief["fin_configurations"] = [family_intent.requested_fin_setup]
    emit_event(
        "bodhi_dna_brief_resolved",
        "bodhi_api",
        region=resolved_dna_brief.get("region"),
        status="success",
        public_family=resolved_dna_brief.get("public_family"),
        requested_feel=resolved_dna_brief.get("desired_feel") or [],
        requested_wave_context={"type": resolved_dna_brief.get("wave_type"), "power": resolved_dna_brief.get("wave_power")},
        stock_requirement=resolved_dna_brief.get("stock_required", False),
        restored=bool(prior_dna_brief),
        correlation_id=correlation_id,
    )
    if prior_dna_brief:
        emit_event(
            "bodhi_conversation_brief_restored",
            "bodhi_api",
            region=resolved_dna_brief.get("region"),
            status="success",
            public_family=resolved_dna_brief.get("public_family"),
            stock_requirement=resolved_dna_brief.get("stock_required", False),
            correlation_id=correlation_id,
        )
    profile, target_volume = _apply_target_volume_context(profile, category)
    missing = missing_profile_fields(profile)
    recommendation = build_recommendation(profile)
    volume_recommendation = build_volume_recommendation(profile, _recommendation_lane(category, profile))
    questions = intake_questions(profile)
    guidance = volume_guidance(profile)
    context_board = None
    prior_active_board = request.conversation_state.active_board if request.conversation_state else None
    if prior_active_board and prior_active_board.get("brand") and prior_active_board.get("model"):
        context_board = (prior_active_board["brand"], prior_active_board["model"])
    elif request.conversation_state and len(request.conversation_state.last_presented_models) == 1:
        card = request.conversation_state.last_presented_models[0]
        context_board = (card.brand, card.model)
    # A pronoun can safely refer to the last single board. An explicit-looking
    # unknown model (for example M23) must never be silently replaced by it.
    message_lower = request.message.lower()
    uses_board_pronoun = bool(re.search(r"\b(?:it|that|this|one)\b", message_lower))
    # Deliberately narrow this guard to an uppercase model-style token. Numeric
    # rider inputs such as 75kg, 28L and 175cm must retain their normal route.
    names_unknown_model = bool(re.search(r"\b[A-Z]{1,8}\d{1,4}\b", request.message))
    board_resolution = resolve_board(
        request.message,
        context_board=context_board if uses_board_pronoun and not names_unknown_model else None,
    )
    requested_board = (
        {
            "brand": board_resolution.brand,
            "model": board_resolution.model,
            "boardModelId": board_resolution.canonical_model_id,
            "canonicalKey": board_resolution.canonical_key,
        }
        if board_resolution.status == "resolved" else find_requested_board(request.message)
    )
    if requested_board and not requested_board.get("boardModelId") and prior_active_board and (
        requested_board.get("brand"), requested_board.get("model")
    ) == (prior_active_board.get("brand"), prior_active_board.get("model")):
        requested_board = {**prior_active_board, **requested_board}
    active_board_override = requested_board if board_resolution.status == "resolved" else prior_active_board
    active_inventory_request = bool(active_board_override and _message_requests_active_board_inventory(request.message))
    mixed_profile_and_board_request = bool(re.search(r"\b(?:show|find|recommend|board)\b", request.message, re.I))
    if semantic_decision.candidate_tool == "reject_profile_update":
        legacy_intent = "profile_update_reject"
        intent = "PROFILE_UPDATE_REJECT"
    elif (profile_update_proposal or profile_update_confirmation_requested) and not mixed_profile_and_board_request:
        # An explicit profile mutation request always outranks prior stock or family state.
        legacy_intent = "profile_update_request"
        intent = "PROFILE_UPDATE"
    elif active_inventory_request:
        legacy_intent = "active_board_inventory_request"
        intent = "AVAILABILITY"
    if board_resolution.status == "resolved":
        match_event = (
            "exact_match" if board_resolution.match_type.startswith("exact")
            else "alias_match" if board_resolution.match_type == "alias_match"
            else "fuzzy_match" if board_resolution.match_type == "fuzzy_model"
            else board_resolution.match_type
        )
        emit_event(
            "board_intent_detected", "bodhi_api", status="success",
            resolution=match_event, brand=board_resolution.brand,
            canonical_model_id=board_resolution.canonical_model_id,
            confidence=board_resolution.confidence, region=profile.region or request.region,
            correlation_id=correlation_id,
        )
        emit_event(
            f"board_resolution_{board_resolution.match_type}", "bodhi_api", status="success",
            brand=board_resolution.brand, canonical_model_id=board_resolution.canonical_model_id,
            confidence=board_resolution.confidence, region=profile.region or request.region,
            correlation_id=correlation_id,
        )
    elif board_resolution.status == "ambiguous":
        emit_event("board_intent_detected", "bodhi_api", status="success", resolution="ambiguous_match",
                   region=profile.region or request.region, correlation_id=correlation_id)
        emit_event("board_resolution_ambiguous", "bodhi_api", status="success", region=profile.region or request.region,
                   correlation_id=correlation_id)
    if board_resolution.status == "resolved" and legacy_intent in {"surfer_fit_request", "greeting_request"}:
        legacy_intent = "general_board_question"
        intent = "BOARD_DETAILS"
    if (
        legacy_intent == "comparison_request"
        and len(active_topic.boards) < 2
        and context_board
        and requested_board
        and (requested_board["brand"], requested_board["model"]) != context_board
    ):
        # “Compare it with X” is a valid two-board request when the immediately
        # preceding controlled board detail supplied the pronoun reference.
        active_topic.kind = "comparison"
        active_topic.boards = [
            {"brand": context_board[0], "model": context_board[1]},
            requested_board,
        ]
        active_topic.is_follow_up = True
    if (
        board_resolution.status == "resolved"
        and board_resolution.match_type == "conversation_context"
        and re.search(r"\b(?:would it suit me|how .*feel|paddle(?: more| better| easily)?)\b", message_lower)
    ):
        legacy_intent = "general_board_question"
        intent = "BOARD_DETAILS"
    if names_unknown_model and board_resolution.status == "not_found" and not requested_board:
        legacy_intent = "general_board_question"
        intent = "BOARD_DETAILS"
    classification_correction = _model_classification_correction(request.message)
    if classification_correction:
        correction_dna = classification_correction["dna"]
        emit_event(
            "bodhi_model_classification_correction",
            "bodhi_api",
            status="success",
            canonical_model_id=correction_dna["canonical_model_id"],
            existing_family=correction_dna["public_family"],
            user_asserted_family=classification_correction["asserted_family"],
            correlation_id=correlation_id,
        )
    if legacy_intent == "exact_board_location_request" and not requested_board:
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
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        profile_fields_used=sorted(
            field for field, value in profile.model_dump().items()
            if field not in {"profile_sources", "profile_conflicts", "field_provenance"} and value not in (None, "", [], {})
        ),
        missing_field_count=len(missing),
        profile_completeness=profile_completeness(profile),
        correlation_id=correlation_id,
    )
    comparison = None
    comparison_boards_override = None
    force_controlled_reply = False
    is_first_turn = not any(item.role == "assistant" for item in request.conversation if item)
    state_follow_up = _handle_state_follow_up(request, profile, directive)
    education_reply = _family_education_reply(request.message)
    asks_name = intent == "IDENTITY_QUERY"
    non_recommendation_guard = intent in NON_RECOMMENDATION_GUARD_INTENTS
    current_message_is_correction = intent == "NO_REQUEST" and bool(request.message.strip())
    allow_recommendations = semantic_decision.candidate_tool in {"recommend_boards", "check_model_availability"} and not non_recommendation_guard
    response_mode = "recommendations" if allow_recommendations else "conversation"
    catalogue_match_status = None
    explicit_expansion_manufacturer = canonical_manufacturer_name(request.message)
    active_expansion_manufacturer = find_manufacturer(profile.requested_brand) if profile.requested_brand else None
    manufacturer_stock_request = bool(re.search(r"\b(?:stock|available|buy|retailer)\b", request.message, re.I))
    if legacy_intent in {"greeting_request", "capability_help_request", "site_help_question"}:
        recommendation = None
        volume_recommendation = None
        guidance = None

    if intent == "AUTH_STATE_UPDATE":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = (
            f"You’re signed in as {profile.display_name}. I’ve refreshed your saved My Quivrr profile for this chat."
            if auth_context.profile_loaded and profile.display_name
            else "You’re signed in, but I did not receive a verified display name. I’ve refreshed your saved My Quivrr context for this chat."
            if auth_context.authenticated
            else "I can’t see a verified signed-in session yet. Please refresh and try again."
        )
        questions = []
        force_controlled_reply = True
        response_mode = "conversation_only"
    elif intent == "IDENTITY_QUERY":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = (
            f"You’re {profile.display_name}. I’ve refreshed your saved rider profile from My Quivrr for this chat."
            if auth_context.profile_loaded and profile.display_name
            else "You’re signed in, but I did not receive a verified display name."
            if auth_context.authenticated
            else "I can’t verify your name while you’re signed out."
        )
        questions = []
        force_controlled_reply = True
        response_mode = "conversation_only"
    elif intent == "NO_REQUEST":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = (
            "You’re right. I misread that. What would you like help with?"
            if current_message_is_correction
            else "Hey. What are you looking for today?"
        )
        questions = []
        force_controlled_reply = True
        response_mode = "conversation_only"
    elif intent == "ACKNOWLEDGEMENT_ONLY":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = (
            "No worries. I’ll keep that profile update ready if you decide you want to save it."
            if pending_action else "No problem. What would you like help with?"
        )
        questions = []
        force_controlled_reply = True
        response_mode = "conversation_only"
    elif intent == "CONVERSATION" or acknowledgement_turn:
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = (
            "No worries. I’ll keep that profile update ready if you decide you want to save it."
            if pending_action
            else "I’m not sure what you’d like me to do next. Are you asking about a board, your profile, or something else?"
        )
        questions = []
        force_controlled_reply = True
        response_mode = "conversation"
    elif intent == "PROFILE_UPDATE_REJECT":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = "No worries. I’ll leave your saved profile unchanged."
        questions = []
        force_controlled_reply = True
        response_mode = "conversation"
    elif topic_route.kind == "PLATFORM_CATALOGUE_COUNT":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        count = int(load_board_master().get("model_count") or len(load_board_master().get("models") or []))
        reply = f"Quivrr's canonical board knowledge is global rather than Australian. I currently know {count} governed premium board models overall; regional inventory is layered onto that catalogue."
        questions = []
        force_controlled_reply = True
        response_mode = "platform_answer"
    elif topic_route.kind == "REGIONAL_AVAILABLE_BOARD_COUNT":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        region = topic_route.region or profile.region or request.region
        summary = inventory_summary(region) if region else {}
        if summary:
            reply = (
                f"{REGION_DISPLAY_NAMES.get(summary.get('regionCode'), summary.get('regionCode'))} currently has "
                f"{summary.get('availableCanonicalSizeCount', 0):,} distinct canonical board sizes with verified availability across "
                f"{summary.get('availableCanonicalModelCount', 0):,} models. Behind that are "
                f"{summary.get('retailerOfferCount', 0):,} retailer offers and {summary.get('manufacturerAvailabilityCount', 0):,} manufacturer-direct records; those raw records can overlap."
            )
        elif region:
            reply = f"I could not retrieve the current {REGION_DISPLAY_NAMES.get(region, region)} inventory summary just now, so I will not guess at the count."
        else:
            reply = "Which region should I summarise: Australia, Europe, Indonesia, or the United States?"
        questions = [] if region else ["Which region should I summarise?"]
        force_controlled_reply = True
        response_mode = "platform_answer"
    elif topic_route.kind == "PLATFORM_BRAND_COUNT":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = f"Quivrr currently governs {len({row.get('manufacturer') for row in load_board_master().get('models', []) if row.get('manufacturer')})} established premium surfboard manufacturers."
        questions = []
        force_controlled_reply = True
        response_mode = "platform_answer"
    elif topic_route.kind == "PLATFORM_REGION_LIST":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = "Quivrr has live regional search and inventory coverage for Australia, Europe, Indonesia and the United States."
        questions = []
        force_controlled_reply = True
        response_mode = "platform_answer"
    elif topic_route.kind == "PLATFORM_CATALOGUE_SCOPE":
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = SURF_DOMAIN_KNOWLEDGE.premium_positioning["canonical_statement"] + " " + SURF_DOMAIN_KNOWLEDGE.premium_positioning["beginner_statement"]
        questions = []
        force_controlled_reply = True
        response_mode = "guidance_only"
    elif stage_assessment.clarification_required:
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        reply = BEGINNER_QUESTION
        questions = [BEGINNER_QUESTION]
        force_controlled_reply = True
        response_mode = "guidance_only"
        catalogue_match_status = "stage_clarification_required"
    elif stage_assessment.stage == STAGE_1:
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        saved_volume_ignored = bool(profile.current_volume_litres or profile.target_volume_litres)
        reply = beginner_guidance(STAGE_1, profile.weight_kg, saved_volume_ignored)
        questions = []
        force_controlled_reply = True
        response_mode = "guidance_only"
        catalogue_match_status = "no_safe_supported_match"
    elif legacy_intent == "profile_update_request":
        suggested_boards = []
        recommendation = None
        volume_recommendation = None
        guidance = None
        reply = profile_update_proposal.message if profile_update_proposal else "Your saved profile update is ready to be confirmed."
        questions = []
        force_controlled_reply = True
        response_mode = "tool_result"
    elif legacy_intent == "active_board_inventory_request" and active_board_override and active_board_override.get("boardModelId"):
        recommendation_path = "active_board_exact_availability"
        candidate_source = "model_availability"
        ranking_engine_used = "regional_exact_size_inventory"
        inventory_stage = "model_availability"
        suggested_boards, reply, active_inventory_query = _active_board_inventory_response(
            active_board_override, profile.region or request.region, profile,
        ) if (profile.region or request.region) else ([], "Which region should I check for that board?", None)
        candidate_count_before_inventory = len(suggested_boards)
        questions = []
        force_controlled_reply = True
    elif legacy_intent == "active_board_inventory_request":
        suggested_boards = []
        reply = "Which board should I check? Name the brand and model and I’ll look for verified regional sizes."
        questions = ["Which board should I check?"]
        force_controlled_reply = True
    elif active_expansion_manufacturer and intent != "BOARD_COMPARISON" and (explicit_expansion_manufacturer or category):
        canonical_brand = active_expansion_manufacturer["manufacturer"]
        customer_brand = _customer_manufacturer_name(canonical_brand)
        catalogue_models = models_for_manufacturer(canonical_brand)
        recommendation_path = "explicit_manufacturer_catalogue"
        candidate_source = "manufacturer_expansion_catalogue"
        ranking_engine_used = "evidence_limited_catalogue"
        if manufacturer_stock_request and profile.region:
            available = available_manufacturer_models(canonical_brand, profile.region)
            suggested_boards = available[:3]
            candidate_count_before_inventory = len(available)
            inventory_stage = "live_manufacturer_summary"
            total_boards = sum(board.available_count for board in available)
            if available:
                reply = (
                    f"Yes. I found {total_boards} currently available {customer_brand} board listings across "
                    f"{len(available)} models in {REGION_DISPLAY_NAMES.get(profile.region, profile.region)}. "
                    "These are the leading live models; I can open the full regional search for any of them."
                )
            else:
                reply = (
                    f"Quivrr knows {len(catalogue_models)} {customer_brand} models, but I can’t verify current "
                    f"{REGION_DISPLAY_NAMES.get(profile.region, profile.region)} stock right now."
                )
            questions = []
        elif category:
            evidence_matches = _expansion_catalogue_suggestions(canonical_brand, category)
            suggested_boards = evidence_matches[:3]
            candidate_count_before_inventory = len(evidence_matches)
            if evidence_matches:
                names = ", ".join(board.model for board in evidence_matches[:5])
                reply = (
                    f"I kept your {customer_brand} constraint. Its official model information references fish design for {names}. "
                    "Quivrr has not assigned editorial board-family or rider-fit claims to these models, so I’m showing factual catalogue matches rather than inventing a ranking."
                )
            else:
                reply = (
                    f"I kept your {customer_brand} constraint, but I can’t verify a governed {category.replace('_', ' ')} "
                    "classification in its current official model information. I haven’t substituted another manufacturer."
                )
            questions = ["Would you like me to check current stock in your region?"] if evidence_matches else []
        else:
            suggested_boards = []
            reply = (
                f"Yes. Quivrr currently knows {len(catalogue_models)} {customer_brand} models. I can help you explore "
                f"{customer_brand} models, compare two models, or check current stock in your region. "
                f"Are you looking for a particular {customer_brand} model or board type?"
            )
            questions = [f"Are you looking for a particular {customer_brand} model or board type?"]
    elif asks_name:
        suggested_boards = []
        if auth_context.profile_loaded and profile.display_name:
            reply = f"You’re {profile.display_name}. I’ve also got your saved rider profile available for this session."
        elif auth_context.authenticated:
            reply = "You’re signed in, but I did not receive a verified display name."
        else:
            reply = "I can’t verify your name while you’re signed out."
        questions = []
    elif intent == "PROFILE_QUESTION":
        suggested_boards = []
        if auth_context.profile_loaded:
            known = [label for value, label in ((profile.ability, "ability"), (profile.target_volume_litres, "volume"), (profile.region, "region"), (profile.home_break, "home break")) if value not in (None, "")]
            reply = f"I’ve verified your saved rider profile for this session. Available fields include {', '.join(known) if known else 'no completed surfing details yet'}."
        elif auth_context.authenticated:
            reply = "You’re signed in, but I couldn’t load your saved rider profile just now."
        else:
            reply = "I can’t verify a saved rider profile while you’re signed out."
        questions = []
    elif intent == "PROMPT_INJECTION":
        suggested_boards = []
        reply = prompt_disclosure_reply()
        questions = []
    elif language_tone.level == "threatening":
        suggested_boards = []
        reply = "I can help with the board search, but I can’t help with threats or harm. If someone may be in immediate danger, contact local emergency services now."
        questions = []
    elif intent in {"OFF_TOPIC", "ABUSIVE"}:
        suggested_boards = []
        reply = "I’m built for surfboards, board choice and Quivrr stock. I can help you choose a board, compare models or check regional availability."
        questions = []
    elif intent == "CONVERSATION_RESET":
        suggested_boards = []
        if directive.target_surfer == "different_surfer":
            reply = "Got it. I’ve cleared the previous rider brief. What is their ability, approximate weight or usual volume, and the waves they normally surf?"
            questions = ["What is their ability and approximate weight or usual volume?", "What waves do they normally surf?"]
        else:
            reply = personalise_opening("Fresh start. What are we working on today?", profile, is_first_turn=True)
            questions = []
    elif education_reply:
        suggested_boards = []
        reply = education_reply
        questions = []
    elif allow_recommendations and auth_context.authenticated and not auth_context.profile_loaded and not current_profile.ability and not current_profile.weight_kg:
        suggested_boards = []
        recommendation = None
        volume_recommendation = None
        guidance = None
        if auth_context.status == "failed":
            reply = "I couldn’t load your saved ability just now. Are you still surfing at an advanced level?"
            questions = ["Are you still surfing at an advanced level?"]
        else:
            reply = "Loading your saved rider profile..."
            questions = []
    elif state_follow_up:
        suggested_boards = state_follow_up.get("suggested_boards", [])
        comparison = state_follow_up.get("comparison")
        comparison_boards_override = state_follow_up.get("comparison_boards")
        reply = state_follow_up["reply"]
        questions = state_follow_up.get("questions", [])
    elif _sponsorship_explanation(request.message):
        suggested_boards = []
        reply = _sponsorship_explanation(request.message)
        questions = []
    elif intent == "AVAILABILITY" and legacy_intent == "board_search_request" and not category and not requested_board:
        suggested_boards = []
        region_name = {"AU": "Australia", "EU": "Europe", "ID": "Indonesia", "US": "the United States"}.get(profile.region or request.region, "your region")
        reply = f"I can check verified stock in {region_name}. Are you after a fish, daily driver, performance shortboard, mid-length, or a specific brand and model?"
        questions = ["Which board type, brand, or model should I check?"]
    elif legacy_intent == "greeting_request":
        suggested_boards = []
        if auth_context.authenticated and request.conversation_state and request.conversation_state.conversation_turn > 0:
            first_name = (profile.display_name or "").split()[0].strip(" ,.!?")
            reply = f"Welcome back, {first_name}. Where should we pick up?" if first_name else "Welcome back. Where should we pick up?"
        else:
            reply = personalise_opening(greeting_reply(profile.region), profile, is_first_turn=is_first_turn)
        questions = []
    elif legacy_intent == "capability_help_request":
        suggested_boards = []
        reply = (
            "I can help you choose a board, compare models, understand design features, check regional availability, "
            "review your quiver, work through volume and sizing, or figure out what will help your surfing progress. "
            "What are we looking at today?"
        )
        questions = []
    elif legacy_intent == "site_help_question":
        suggested_boards = []
        reply = site_help_reply(profile.region)
        questions = []
    elif legacy_intent == "expert_board_question":
        suggested_boards = []
        reply = expert_board_question_reply(request.message)
        questions = []
    elif legacy_intent == "exact_board_location_request" and not profile.region:
        suggested_boards = []
        reply = "I’ve got the board. Should I check Australia, Europe, or Indonesia?"
        questions = ["Which region should I search: Australia, Europe, or Indonesia?"]
    elif legacy_intent == "exact_board_location_request" and not requested_board:
        suggested_boards = []
        if "christenson fish" in request.message.lower():
            reply = "The Christenson Fish is a strong canonical point-break fish reference, but I can’t see a matching canonical model or verified live link in the selected regional inventory right now."
        else:
            reply = "Tell me the brand and model you want located, and I’ll check verified stock in that region."
        questions = []
    elif legacy_intent == "exact_board_location_request":
        base = suggestions_for_board(requested_board)[:1]
        suggested_boards, exact = locate_exact_board(base[0], profile) if base else ([], False)
        if _requests_offer_price(request.message):
            suggested_boards.sort(key=_offer_price_sort)
        if suggested_boards:
            source_names = []
            if any(board.manufacturer_direct_count for board in suggested_boards):
                source_names.append("manufacturer-direct")
            if any(board.retailer_count for board in suggested_boards):
                source_names.append("retailer")
            if _requests_offer_price(request.message):
                priced = [board.offers[0] for board in suggested_boards if board.offers and board.offers[0].observed_price is not None]
                price_note = ""
                if priced:
                    lowest = priced[0]
                    price_note = (
                        f" The lowest observed listed price among these matching offers is "
                        f"{lowest.observed_price:g} {lowest.currency or ''} from {lowest.retailer_name or 'the listed source'}."
                    )
                reply = (
                    f"I found {len(suggested_boards)} {'exact' if exact else 'close'} verified {profile.region} offer(s) "
                    f"for {requested_board['brand']} {requested_board['model']}.{price_note} "
                    "Prices are observations and should be confirmed with the retailer."
                )
            else:
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
    elif legacy_intent == "volume_advice_request":
        suggested_boards = []
        reply = volume_advice_reply(profile)
        questions = []
    elif classification_correction:
        suggested_boards = []
        dna = classification_correction["dna"]
        reply = (
            f"You’re right to check the classification. The governed record places "
            f"{dna['brand']} {dna['model']} in {dna['public_family'].replace('_', ' ')}, "
            f"with the detailed category {dna['primary_category'].replace('_', ' ')}. "
            "I’ll use that classification for this conversation without changing the authoritative record at runtime."
        )
        questions = []
    elif legacy_intent == "general_board_question" and requested_board and re.search(r"\b(?:what type|what kind|which family|classification)\b", request.message.lower()):
        suggested_boards = []
        dna = find_board_dna(requested_board["brand"], requested_board["model"])
        if dna:
            family = dna["public_family"].replace("_", " ").title()
            category = dna["primary_category"].replace("_", " ").title()
            reply = (
                f"{dna['brand']} {dna['model']} is a {family}. "
                f"Its detailed governed category is {category}."
            )
        else:
            reply = general_board_reply(request.message)
        questions = []
    elif legacy_intent == "general_board_question" and requested_board and re.search(r"\b(?:fin|fins|fin setup|thruster|quad|twin)\b", request.message.lower()):
        suggested_boards = []
        dna = find_board_dna(requested_board["brand"], requested_board["model"])
        if dna:
            alternatives = dna.get("alternative_fin_setup") or []
            alternative_text = f" It also supports {', '.join(alternatives)}." if alternatives else ""
            reply = (
                f"{dna['brand']} {dna['model']} uses {dna['primary_fin_setup']} as its primary fin setup."
                f"{alternative_text} Quivrr classifies the board as "
                f"{dna['public_family'].replace('_', ' ').title()}, with the detailed category "
                f"{dna['primary_category'].replace('_', ' ').title()}; fin setup and family are separate."
            )
        else:
            reply = general_board_reply(request.message)
        questions = []
    elif legacy_intent == "general_board_question" and requested_board and "fish" in request.message.lower():
        suggested_boards = []
        reply = board_family_reply(requested_board, "fish")
        questions = []
    elif legacy_intent == "general_board_question" and requested_board:
        suggested_boards = [_resolved_board_suggestion(requested_board)]
        if profile.region or request.region:
            suggested_boards[0] = suggested_boards[0].model_copy(
                update={"region": profile.region or request.region, "region_code": profile.region or request.region}
            )
        reply = _board_information_reply(requested_board, profile)
        questions = []
        force_controlled_reply = True
    elif board_resolution.status == "ambiguous":
        suggested_boards = []
        options = [f"{brand} {model}" for brand, model in board_resolution.alternatives]
        reply = "I found a board name that needs a little more detail. " + (
            f"Did you mean {', '.join(options)}?" if options else "Which brand and model did you mean?"
        )
        questions = ["Which brand and model did you mean?"]
        force_controlled_reply = True
    elif legacy_intent == "general_board_question" and re.search(r"\b(?:tell me about|what is|would|is an?)\b", request.message.lower()):
        suggested_boards = []
        reply = "I can’t resolve that to a current canonical board model yet. Please share the manufacturer and exact model name so I don’t guess."
        questions = ["Which manufacturer and model did you mean?"]
        force_controlled_reply = True
    elif legacy_intent == "general_board_question":
        suggested_boards = []
        reply = general_board_reply(request.message)
        questions = []
    elif (
        allow_recommendations
        and legacy_intent in {"board_search_request", "surfer_fit_request"}
        and not family_intent.requested_fin_setup
        and _should_clarify_category(request.message, category, requested_board, intent_result)
    ):
        suggested_boards = []
        recommendation = None
        volume_recommendation = None
        guidance = None
        reply, questions = _clarifying_category_reply(request.message)
    elif (
        legacy_intent == "board_search_request"
        and profile.target_volume_litres
        and not profile.weight_kg
        and not (category == "fish" and profile.region)
        and "stock" not in request.message.lower()
        and "available" not in request.message.lower()
    ):
        suggested_boards = []
        reply = (
            f"I can work around {profile.target_volume_litres:g}L, but I still need your weight before I treat that as a real fit target. "
            "Give me your rough weight and I’ll tighten the range properly."
        )
        questions = ["Roughly how much do you weigh?"]
    elif active_topic.stock_check:
        recommendation_path = "active_topic_stock_check"
        candidate_source = "active_topic"
        ranking_engine_used = "relationship_graph" if active_topic.kind == "relationship" else "direct_board_lookup"
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
        candidate_count_before_inventory = len(canonical)
        inventory_stage = "post_ranking"
        suggested_boards = checked
        available = [row for row in suggested_boards if row.available_count > 0]
        names = ", ".join(f"{row.brand} {row.model}" for row in available)
        requested_names = ", ".join(f"{row['brand']} {row['model']}" for row in active_topic.boards)
        reply = (
            f"I checked live {profile.region} stock for {requested_names}. "
            + (f"The available matches are {names}." if available else "I can’t verify a live match for those boards right now.")
        ) if profile.region else "Which region should I check for those boards: Australia, Europe, or Indonesia?"
        questions = []
    elif legacy_intent == "comparison_request":
        recommendation_path = "comparison_request"
        candidate_source = "conversation_state"
        ranking_engine_used = "comparison_engine"
        if len(active_topic.boards) >= 2:
            engine_comparison = compare_board_models(
                active_topic.boards[0]["brand"],
                active_topic.boards[0]["model"],
                active_topic.boards[1]["brand"],
                active_topic.boards[1]["model"],
                profile,
            )
            comparison = engine_comparison.comparison if engine_comparison else BoardComparison(
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
            suggested_boards = checked
            reply = everyday_pushback_reply(profile.region, requested, suggested_boards)
        else:
            suggested_boards = []
            reply = comparison_reply(request.message, active_topic.boards, profile, active_topic.is_follow_up)
        questions = []
    elif legacy_intent == "relationship_request":
        recommendation_path = "relationship_request"
        candidate_source = "relationship_graph"
        ranking_engine_used = "relationship_graph"
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
                candidate_count_before_inventory = len(canonical_boards)
                inventory_stage = "post_ranking"
                suggested_boards = checked
            else:
                suggested_boards = []
            reply = relationship_reply(source_board, relation, canonical_boards, suggested_boards, profile.region)
        questions = []
    elif legacy_intent == "inventory_count_question" and category and profile.region:
        recommendation_path = "inventory_count_question"
        candidate_source = "live_category_search"
        ranking_engine_used = "catalogue_search"
        suggested_boards = search_live_category(profile, category)
        count = sum(board.available_count for board in suggested_boards)
        models = len(suggested_boards)
        candidate_count_before_inventory = len(suggested_boards)
        inventory_stage = "live_search"
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
    elif legacy_intent == "inventory_count_question":
        suggested_boards = []
        reply = inventory_snapshot_reply(profile.region, category)
        questions = []
    elif allow_recommendations and category in {"fish", "performance_fish"} and legacy_intent in {"board_search_request", "surfer_fit_request"}:
        recommendation_path = "fish_family_request"
        ranking_profile = _category_ranking_profile(profile, request.message, category)
        canonical_boards = recommend_from_matrix(ranking_profile, limit=12, family_intent=family_intent)
        candidate_source = "matrix"
        ranking_engine_used = RECOMMENDATION_ENGINE_NAME
        candidate_count_before_inventory = len(canonical_boards)
        if not canonical_boards and profile.region:
            canonical_boards = search_live_category(profile, category)
            recommendation_path = "fish_family_fallback_live_search"
            candidate_source = "live_category_search"
            ranking_engine_used = "catalogue_search"
            candidate_count_before_inventory = len(canonical_boards)
        direct_stock_request = availability_constraint == STOCK_ONLY_CONSTRAINT and bool(profile.region)
        brand_stock_request = bool(profile.requested_brand and direct_stock_request)
        if brand_stock_request:
            checked = enrich_suggestions_with_inventory(canonical_boards, ranking_profile)
            inventory_stage = "post_ranking"
            suggested_boards = _filter_volume_compatible(_enforce_shortlist_coherence([board for board in checked if board.available_count > 0], category, ranking_profile, request.message, family_intent=family_intent))
            if suggested_boards:
                reply = f"I found verified {profile.region} fish stock from {profile.requested_brand}: " + ", ".join(f"{row.model}" for row in suggested_boards[:5]) + "."
            else:
                alternative_profile = ranking_profile.model_copy(update={"requested_brand": None})
                alternatives = recommend_from_matrix(alternative_profile, limit=8, family_intent=family_intent)
                checked_alternatives = enrich_suggestions_with_inventory(alternatives, alternative_profile)
                suggested_boards = _filter_volume_compatible(_enforce_shortlist_coherence([board for board in checked_alternatives if board.available_count > 0], category, alternative_profile, request.message, family_intent=family_intent))
                reply = f"I can’t see verified live {profile.region} fish stock from {profile.requested_brand} right now. "
                if suggested_boards:
                    reply += "The closest live fish alternatives are " + ", ".join(f"{row.brand} {row.model}" for row in suggested_boards[:5]) + "."
            questions = []
        elif direct_stock_request:
            checked = enrich_suggestions_with_inventory(canonical_boards, ranking_profile)
            inventory_stage = "post_ranking"
            suggested_boards = _filter_volume_compatible(_enforce_shortlist_coherence(_verified_in_stock(checked), category, ranking_profile, request.message, family_intent=family_intent))
            performance_request = category == "performance_fish" or is_performance_fish_request(request.message)
            if not suggested_boards and performance_request:
                # "Pro fish" is an intent-level design brief, not a public catalogue family.
                expanded_profile = ranking_profile.model_copy(update={"preferred_board_type": "Fish"})
                expanded_candidates = recommend_from_matrix(expanded_profile, limit=16)
                expanded_candidates = _unique_boards([*canonical_boards, *expanded_candidates])
                expanded_checked = enrich_suggestions_with_inventory(expanded_candidates, expanded_profile)
                suggested_boards = _filter_volume_compatible(_verified_in_stock(expanded_checked))
                checked = expanded_checked
                candidate_count_before_inventory = len(expanded_candidates)
                recommendation_path = "performance_fish_expanded_stock_search"
                candidate_source = "matrix_progressive_widening"
            reply = _stock_only_reply(
                "performance fish and hybrid", profile.region, suggested_boards,
                candidate_count=len(canonical_boards), checked=checked,
            )
            if performance_request and suggested_boards:
                reply = "I widened “pro fish” to performance-oriented fish and hybrid shapes. " + reply
            questions = []
        else:
            suggested_boards = canonical_boards[:3]
            detail = (family_intent.requested_detailed_category or "fish").lower()
            if detail == "traditional fish":
                reply = "A traditional fish sounds right: fuller, faster and more relaxed. These three are the best catalogue matches for that feel."
            else:
                reply = "A fish sounds right. These are the strongest catalogue matches for what you described."
            if target_volume and target_volume.minimum_litres is not None and target_volume.maximum_litres is not None:
                if profile.target_volume_source == "saved_profile":
                    reply += f" Using your saved {target_volume.target_litres:g}L target keeps the sizing focused."
                else:
                    reply += f" A sensible starting range is {target_volume.minimum_litres:g} to {target_volume.maximum_litres:g}L."
            reef_context = "reef" in " ".join(filter(None, [profile.wave_type, profile.home_break_type, profile.desired_feel])).lower()
            if reef_context and any("performance fish" in (board.category or "").lower() for board in canonical_boards):
                reply += "; performance fish and reef-capable twin designs are the right lane here."
            if profile.region and not (profile.wave_type or profile.wave_size or profile.wave_power):
                reply += " Are your waves mostly weak beach breaks, points, or reefs?"
            elif profile.region:
                reply += f" I haven't filtered them by live stock yet. Want me to check what is available in {profile.region}?"
            else:
                reply += " Which region should I check if you want a live-stock overlay?"
            questions = []
            if volume_correction_requested and target_volume and target_volume.minimum_litres is not None and target_volume.maximum_litres is not None:
                reply = (
                    f"You’re right. That range is too broad for your {target_volume.target_litres:g}L target. "
                    f"I’ve tightened this to roughly {target_volume.minimum_litres:g} to {target_volume.maximum_litres:g}L and removed boards that only fit at unrealistic sizes. "
                    + reply
                )
            questions = []
    elif allow_recommendations and legacy_intent == "board_search_request" and category and profile.region and not requested_board:
        recommendation_path = "explicit_category_request"
        ranking_profile = _category_ranking_profile(profile, request.message, category)
        canonical_boards = recommend_from_matrix(ranking_profile, limit=12, family_intent=family_intent)
        if not canonical_boards and family_intent.requested_public_family:
            # A saved home-break profile can conflict with a user's current,
            # explicit family correction. Keep the authoritative family gate,
            # but retry the catalogue ranking without inherited wave constraints
            # so the current request is not erased by stale profile context.
            current_message_mentions_waves = bool(re.search(
                r"\b(?:wave|reef|point|beach|hollow|weak|powerful|small surf|big surf)\b",
                request.message,
                re.I,
            ))
            if not current_message_mentions_waves:
                family_first_profile = ranking_profile.model_copy(update={
                    "home_break_type": None,
                    "wave_type": None,
                    "wave_size": None,
                    "wave_size_min_ft": None,
                    "wave_size_max_ft": None,
                    "wave_power": None,
                    "wave_quality": None,
                })
                canonical_boards = recommend_from_matrix(
                    family_first_profile,
                    limit=12,
                    family_intent=family_intent,
                )
                if canonical_boards:
                    ranking_profile = family_first_profile
        candidate_count_before_inventory = len(canonical_boards)
        candidate_source = "matrix"
        ranking_engine_used = RECOMMENDATION_ENGINE_NAME
        candidate_count = len(canonical_boards)
        if availability_constraint == STOCK_ONLY_CONSTRAINT:
            if profile.construction_preference and category in {"performance_daily_driver", "performance_shortboard"}:
                stock_matches = search_live_category(profile, category)
                inventory_stage = "live_search"
                candidate_source = "live_category_search"
                ranking_engine_used = "catalogue_search"
            else:
                checked = enrich_suggestions_with_inventory(canonical_boards, ranking_profile)
                inventory_stage = "post_ranking"
                stock_matches = _filter_volume_compatible(_enforce_shortlist_coherence(
                    _verified_in_stock(checked), category, ranking_profile, request.message,
                    family_intent=family_intent,
                ))
            suggested_boards = stock_matches or canonical_boards[:3]
        else:
            suggested_boards = canonical_boards[:3]
        if requested_limit := _requested_card_limit(request.message):
            suggested_boards = suggested_boards[:requested_limit]
        label = _category_label(category)
        target = f" around {profile.target_volume_litres:g}L" if profile.target_volume_litres else ""
        if availability_constraint == STOCK_ONLY_CONSTRAINT:
            if stock_matches:
                reply = _stock_only_reply(label, profile.region, stock_matches, candidate_count=candidate_count)
            else:
                reply = (
                    f"I couldn't verify any live {label} stock{target} in {profile.region} right now. "
                    "These are still the best catalogue matches for what you described. "
                    "I can broaden the size or region if you want."
                )
        elif suggested_boards:
            reply = f"A {label} sounds right. These are the strongest catalogue matches for what you described."
            if profile.region:
                reply += f" I haven't filtered them by live stock yet. Want me to check what is available in {profile.region}?"
            if volume_correction_requested and target_volume and target_volume.minimum_litres is not None and target_volume.maximum_litres is not None:
                reply = (
                    f"You’re right. That range is too broad for your {target_volume.target_litres:g}L target. "
                    f"I’ve tightened this to roughly {target_volume.minimum_litres:g} to {target_volume.maximum_litres:g}L and removed boards that only fit at unrealistic sizes. "
                    + reply
                )
        else:
            reply = (
                f"I couldn't find a governed {label} catalogue match{target}. "
                "Tell me whether you want more paddle help, performance, or small-wave speed and I'll check the closest category."
            )
        questions = []
    elif legacy_intent == "board_search_request" and category and not profile.region and not requested_board:
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
    elif legacy_intent == "alternative_request":
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
        reply = personalise_opening(opening_message(profile.region), profile, is_first_turn=is_first_turn)
    elif profile.weight_kg and profile.ability and not (profile.wave_size or profile.wave_type or profile.wave_power):
        suggested_boards = []
        reply = partial_volume_reply(profile, acknowledge_memory=is_memory_correction(request.message))
        questions = ["What size waves are you mostly surfing?"]
    elif allow_recommendations and enough_for_recommendations(profile):
        recommendation_path = "general_recommendation"
        wants_performance = "performance" in " ".join(filter(None, [profile.desired_feel, profile.goal])).lower()
        if profile.current_board and wants_performance:
            performance_profile = profile.model_copy(update={"preferred_board_type": "Daily Driver"})
            expert_lane = recommend_from_matrix(performance_profile, limit=8, family_intent=family_intent)
            graph_lane = graph_suggestions(profile, "upgradeBoards")
            candidate_source = "matrix_plus_graph"
            ranking_engine_used = "matrix_plus_graph"
            candidate_count_before_inventory = len(expert_lane) + len(graph_lane)
            seen = set()
            suggested_boards = []
            for board in expert_lane + graph_lane:
                key = (board.brand.lower(), board.model.lower())
                if key not in seen:
                    suggested_boards.append(board)
                    seen.add(key)
            suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
            inventory_stage = "post_ranking"
        else:
            suggested_boards = recommend_from_matrix(profile, family_intent=family_intent)
            suggested_boards = enrich_suggestions_with_inventory(suggested_boards, profile)
            candidate_source = "matrix"
            ranking_engine_used = RECOMMENDATION_ENGINE_NAME
            candidate_count_before_inventory = len(suggested_boards)
            inventory_stage = "post_ranking"
        if availability_constraint == STOCK_ONLY_CONSTRAINT:
            suggested_boards = _verified_in_stock(suggested_boards)
            lane_label = (category or extract_category(profile.preferred_board_type or "") or "board").replace("_", " ")
            reply = _stock_only_reply(lane_label, profile.region, suggested_boards)
        else:
            reply = recommendation_reply(profile, guidance, suggested_boards) if guidance else opening_message(profile.region)
        reply = personalise_opening(reply, profile, is_first_turn=is_first_turn)
        if questions:
            reply += " " + questions[0]
    else:
        suggested_boards = []
        reply = "Nice. " + " ".join(questions)
    rejected_keys = {
        (item.get("brand", "").lower(), item.get("model", "").lower())
        for item in (request.conversation_state.rejected_recommendations if request.conversation_state else [])
    }
    if rejected_keys and not reset_requested:
        suggested_boards = [
            board for board in suggested_boards
            if (board.brand.lower(), board.model.lower()) not in rejected_keys
        ]
    # Final fail-closed contract: no inventory or recommendation path may render
    # a primary result outside the user's explicit Board Master family.
    suggested_boards = _enforce_shortlist_coherence(
        suggested_boards,
        category,
        profile,
        request.message,
        family_intent=family_intent,
    )
    correction_text = correction_acknowledgement(family_intent)
    if correction_text:
        if suggested_boards:
            reply = f"{correction_text} {reply}"
        else:
            family_label = PUBLIC_FAMILY_LABELS.get(
                family_intent.requested_public_family or "",
                "requested family",
            )
            reply = (
                f"{correction_text} I couldn’t find a matching {family_label} result for the remaining stock, "
                "volume and region constraints, so I haven’t substituted another family."
            )
    source = "deterministic_intake_engine"
    duration = round(time.perf_counter() - started, 3)
    verified_stock_count = sum(1 for board in suggested_boards if (board.available_count or 0) > 0)
    selected_family = suggested_boards[0].category if suggested_boards else (category_resolution.category or category)
    for suggested in suggested_boards[:6]:
        dna = find_board_dna_by_id(suggested.board_model_id)
        if not dna:
            continue
        dna_fit = score_dna_fit(dna, profile, resolved_dna_brief)
        emit_event(
            "bodhi_dna_fit_scored",
            "bodhi_api",
            region=profile.region or request.region,
            status="success",
            canonical_model_id=dna["canonical_model_id"],
            public_family=dna["public_family"],
            requested_feel=resolved_dna_brief.get("desired_feel") or [],
            dna_fit_score=dna_fit.get("score"),
            confidence=dna["evidence"]["behaviour_confidence"],
            stock_requirement=resolved_dna_brief.get("stock_required", False),
            exclusion_count=len(dna_fit.get("exclusions") or []),
            correlation_id=correlation_id,
        )
        if dna["evidence"]["review_required"]:
            emit_event(
                "bodhi_dna_low_confidence",
                "bodhi_api",
                region=profile.region or request.region,
                status="warning",
                canonical_model_id=dna["canonical_model_id"],
                public_family=dna["public_family"],
                confidence=dna["evidence"]["behaviour_confidence"],
                correlation_id=correlation_id,
            )
    emit_event(
        "bodhi_recommendation_generated",
        "bodhi_api",
        region=profile.region or request.region,
        status="success",
        source=source,
        build=BUILD_SHA,
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        intent=intent,
        intent_confidence=intent_result.confidence,
        conversation_turn=(request.conversation_state.conversation_turn + 1) if request.conversation_state else 1,
        missing_field_count=len(missing),
        availability_constraint=availability_constraint,
        requested_region=profile.region or request.region,
        recommendation_path=recommendation_path,
        function_name="board_guide_chat",
        module_name=__name__,
        ranking_engine_used=ranking_engine_used,
        candidate_source=candidate_source,
        inventory_stage=inventory_stage,
        selected_family=selected_family,
        candidate_count_before_inventory=candidate_count_before_inventory,
        verified_stock_count=verified_stock_count,
        suggested_board_count=len(suggested_boards),
        recommendation_count=len(suggested_boards),
        recommendation_brands=list(dict.fromkeys(board.brand for board in suggested_boards[:6])),
        availability_check_count=sum(1 for board in suggested_boards if board.availability_checked),
        recommendation_source="authenticated_profile" if auth_context.profile_loaded else "conversation_only",
        reasoning_trace={
            "request_interpretation": intent,
            "public_family": selected_family,
            "fin_requirement_present": bool(resolved_dna_brief.get("fin_configurations")),
            "hard_exclusions_applied": ranking_engine_used != "none",
            "candidate_pool_count": candidate_count_before_inventory,
            "rider_fit_applied": bool(profile.ability or profile.weight_kg or profile.target_volume_litres),
            "wave_fit_applied": bool(profile.wave_type or profile.wave_power or profile.wave_size),
            "ability_fit_applied": bool(profile.ability),
            "paddle_volume_fit_applied": bool(profile.target_volume_litres or profile.weight_kg),
            "availability_applied": inventory_stage != "not_run",
            "final_order_count": len(suggested_boards),
        },
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
    # Stock-constrained prose must derive from the same enriched boards as the cards.
    if auth_context.authenticated and is_first_turn:
        reply = personalise_opening(reply, profile, is_first_turn=True)
    final_reply = (
        reply
        if availability_constraint == STOCK_ONLY_CONSTRAINT or family_intent.correction or force_controlled_reply
        else (llm_reply or reply)
    )
    if profile_update_proposal and not profile_update_confirmation_requested and legacy_intent != "profile_update_request":
        final_reply = final_reply.rstrip() + " " + profile_update_proposal.message
    elif profile_update_confirmation_requested:
        final_reply = final_reply.rstrip() + " I’ll update your saved My Quivrr profile now."
    previous_outcome = None
    previous_failure_reason = None
    if availability_constraint == STOCK_ONLY_CONSTRAINT and inventory_stage != "not_run":
        if suggested_boards and any(board.available_count > 0 for board in suggested_boards):
            previous_outcome = "SUCCESS_WITH_RESULTS"
        elif candidate_count_before_inventory:
            previous_outcome = "SUCCESS_NO_EXPANDED_MATCH"
            previous_failure_reason = "matching models had no verified regional stock"
        else:
            previous_outcome = "SUCCESS_NO_EXACT_MATCH"
            previous_failure_reason = "no exact governed category match"
    if recovery_kind and availability_constraint == STOCK_ONLY_CONSTRAINT:
        final_reply = recovery_opening(recovery_kind, language_tone) + " " + final_reply
    if language_tone.level in {"frustrated", "abusive"} and availability_constraint == STOCK_ONLY_CONSTRAINT and not recovery_kind:
        final_reply = recovery_opening(None, language_tone) + " " + final_reply
    reply_signature = response_signature(final_reply, previous_outcome or "OTHER")
    if (
        previous_outcome and request.conversation_state
        and request.conversation_state.previous_reply_signature == reply_signature
    ):
        final_reply = (
            "I’m changing the search rather than repeating that result. "
            "I’ll include performance-oriented fish and hybrid shapes with verified regional stock."
        )
        reply_signature = response_signature(final_reply, "RECOVERY")
    if stage_assessment.stage in {"STAGE_2_PROGRESSING_BEGINNER", "STAGE_3_EARLY_INTERMEDIATE"} and suggested_boards:
        safe_boards = [board for board in suggested_boards if stage_allows_board(stage_assessment.stage, board)]
        if not safe_boards:
            suggested_boards = []
            reply = beginner_guidance(stage_assessment.stage, profile.weight_kg, bool(profile.current_volume_litres)) + " I could not find a safe supported hardboard match, so I will not widen into performance boards."
            response_mode = "guidance_only"
            catalogue_match_status = "no_safe_supported_match"
        else:
            suggested_boards = safe_boards
    public_cards = public_recommendations(suggested_boards)
    if non_recommendation_guard or topic_route.pivot or response_mode in {"guidance_only", "platform_answer"}:
        public_cards = []
        suggested_boards = []
        recommendation = volume_recommendation = guidance = None
        active_inventory_query = None
    pending_stage_clarification = (
        {"type": "surfer_stage", "reason": "beginner_ability_ambiguous", "question": BEGINNER_QUESTION}
        if stage_assessment.clarification_required else None
    )
    _set_debug_headers(response, recommendation_path=recommendation_path, ranking_engine=ranking_engine_used)
    conversation_state = build_conversation_state(
        request,
        profile,
        intent,
        public_cards,
        questions,
        availability_constraint=availability_constraint,
        comparison_boards_override=comparison_boards_override,
        directive=directive,
        authenticated=auth_context.authenticated,
        family_intent=family_intent,
        previous_outcome=previous_outcome,
        previous_failure_reason=previous_failure_reason,
        previous_reply_signature=reply_signature,
        pending_profile_update=pending_profile_update,
        pending_action=pending_action,
        pending_clarification=pending_stage_clarification,
        surfer_stage=stage_assessment.stage,
        active_board_override=active_board_override,
        last_inventory_query=active_inventory_query,
        clear_response_plan=topic_route.correction or non_recommendation_guard,
        correction_detected=topic_route.correction or current_message_is_correction,
    )
    follow_up_actions = build_follow_up_actions(intent, public_cards)
    if stage_assessment.clarification_required:
        follow_up_actions = [
            FollowUpAction(id="stage-whitewater", label="Still learning to stand", prompt="I am still learning to stand in the whitewater."),
            FollowUpAction(id="stage-some-green", label="Catching green waves sometimes", prompt="I can catch green waves sometimes and ride along the face."),
            FollowUpAction(id="stage-consistent-green", label="Catching green waves consistently", prompt="I catch green waves consistently and can ride along the face."),
        ]
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
        recommendations=public_cards,
        intent=legacy_intent,
        normalizedIntent=intent,
        legacyIntent=legacy_intent,
        intentConfidence=intent_result.confidence,
        intentEntities=intent_result.entities,
        needsClarification=intent_result.needs_clarification,
        conversationProfile=profile,
        conversationState=conversation_state,
        profileCompleteness=profile_completeness(profile),
        profileConflicts=profile.profile_conflicts,
        profileUpdateProposal=profile_update_proposal,
        profileUpdateConfirmationRequested=profile_update_confirmation_requested,
        volumeRecommendation=volume_recommendation,
        category=category_resolution.category,
        categoryConfidence=category_resolution.confidence,
        categorySource=category_resolution.source,
        comparison=comparison,
        usefulFollowUpQuestions=questions,
        followUpActions=follow_up_actions,
        authenticated=auth_context.authenticated,
        profileLoaded=auth_context.profile_loaded,
        profileAbilitySource=_profile_field_source(profile, "ability"),
        profileVolumeSource=_safe_profile_source(profile.target_volume_source or profile.field_provenance.get("target_volume_litres") or profile.field_provenance.get("current_volume_litres")),
        profileWeightSource=_profile_field_source(profile, "weight_kg"),
        targetVolume=target_volume,
        modelDeployment=model_deployment,
        recommendationVersion="bodhi-sprint-4",
        correlationId=correlation_id,
        responseMode=response_mode,
        catalogueMatchStatus=catalogue_match_status,
        surferStage=stage_assessment.stage,
    )
    emit_event(
        "bodhi_turn_routing",
        "bodhi_api",
        status="success",
        current_message_intent=intent_result.intent,
        context_intent=(request.conversation_state.last_intent if request.conversation_state else None),
        resolved_intent=intent,
        active_board=active_board_override,
        active_region=profile.region or request.region,
        profile_update_detected=bool(profile_update_proposal or profile_update_confirmation_requested),
        surf_knowledge_pack_version=SURF_DOMAIN_KNOWLEDGE.version,
        surfer_stage_resolved=stage_assessment.stage,
        surfer_stage_source=stage_assessment.source,
        stage_clarification_requested=stage_assessment.clarification_required,
        topic_pivot_detected=topic_route.pivot,
        correction_detected=topic_route.correction or current_message_is_correction,
        raw_current_message=request.message,
        authenticated_before_refresh=(request.conversation_state.authenticated if request.conversation_state else False),
        bearer_present_before_hydration=bool(authorization),
        auth_state_after_hydration=auth_context.authenticated,
        previous_intent=(request.conversation_state.last_intent if request.conversation_state else None),
        current_classified_intent=intent_result.intent,
        recommendation_engine_invoked=ranking_engine_used != "none",
        previous_response_plan_reused=bool(
            request.conversation_state and request.conversation_state.last_recommendations and not (topic_route.correction or non_recommendation_guard)
        ),
        interaction_type=semantic_decision.interaction_type,
        requires_tool=semantic_decision.requires_tool,
        candidate_tool=semantic_decision.candidate_tool,
        references_pending_action=semantic_decision.references_pending_action,
        references_active_board=semantic_decision.references_active_board,
        saved_profile_hydration_event=auth_context.status,
        active_conversation_state=(request.conversation_state.model_dump(by_alias=True) if request.conversation_state else {}),
        response_mode=response_mode,
        inventory_lookup_performed=inventory_stage == "model_availability",
        inventory_result_count=(active_inventory_query or {}).get("resultCount", 0),
        correlation_id=correlation_id,
    )
    emit_event(
        "bodhi_response_completed",
        "bodhi_api",
        region=profile.region or request.region,
        status="success",
        source=source,
        build=BUILD_SHA,
        authenticated=auth_context.authenticated,
        profile_loaded=auth_context.profile_loaded,
        intent=intent,
        intent_confidence=intent_result.confidence,
        conversation_turn=conversation_state.conversation_turn if conversation_state else 0,
        missing_field_count=len(missing),
        availability_constraint=availability_constraint,
        requested_region=profile.region or request.region,
        verified_stock_count=verified_stock_count,
        suggested_board_count=len(suggested_boards),
        duration_seconds=duration,
        correlation_id=correlation_id,
    )
    return response
