from __future__ import annotations

import re

from app.board_graph_engine import load_graph
from app.inventory_client import normalise_region
from app.manufacturer_intelligence import canonical_manufacturer_name
from app.models import BoardRecommendation, ProfileExtractionResult, RiderProfile
from app.rider_fit import recommend_rider_fit


ABILITY_ORDER = {
    "Beginner": 1,
    "Progressing Beginner": 2,
    "Lower Intermediate": 3,
    "Intermediate": 4,
    "Upper Intermediate": 5,
    "Advanced": 6,
    "Expert": 7,
}

PREFERENCE_TOKENS = {
    "forgiving": "Forgiving",
    "stable": "Stable",
    "fast": "Fast",
    "loose": "Loose",
    "drive": "Drivey",
    "drivey": "Drivey",
    "responsive": "Responsive",
    "performance": "High Performance",
    "balanced": "Balanced",
}

GOAL_TOKENS = {
    "catch more waves": "Catch more waves",
    "paddle": "More paddle power",
    "improve turns": "Improve turns",
    "turn": "Improve turns",
    "step up": "Step up board",
    "larger waves": "Surf larger waves",
    "replace": "Replace a board",
    "quiver": "Build a quiver",
}

PROFILE_COMPLETENESS_FIELDS = (
    "weight_kg",
    "ability",
    "region",
    "wave_size_min_ft",
    "wave_size_max_ft",
    "wave_power",
)

SOURCE_PRIORITY = {
    "default": 0,
    "inferred": 1,
    "account_profile": 2,
    "saved_profile": 2,
    "conversation_user": 3,
    "conversation_profile": 3,
    "current_user": 4,
}

CORRECTION_FIELDS = {
    "weight_kg",
    "target_volume_litres",
    "current_volume_litres",
    "current_board_volume_litres",
    "ability",
    "region",
    "wave_size_min_ft",
    "wave_size_max_ft",
}


def _extract_height_cm(text: str) -> int | None:
    match = re.search(r"\b(1[4-9][0-9]|20[0-9]|21[0-9])\s*(?:cm|(?:in\s+)?height)\b", text)
    return int(match.group(1)) if match else None


def _extract_weight_kg(text: str) -> int | None:
    match = re.search(r"\b([4-9][0-9]|1[0-4][0-9])\s*(?:kgs?|kilograms?|kilos?)\b", text)
    return int(match.group(1)) if match else None


def _extract_current_volume(text: str) -> float | None:
    riding = re.search(
        r"\b(?:i ride|i'm riding|im riding|currently ride|currently riding|my current board(?: is)?)\D{0,60}"
        r"([1-9][0-9](?:\.[0-9])?)\s*(?:l|litre|litres)\b",
        text,
    )
    if riding:
        return float(riding.group(1))
    if any(token in text for token in ["around", "looking for", "want", "target"]):
        return None
    match = re.search(r"\b([1-9][0-9](?:\.[0-9])?)\s*(?:l|litre|litres)\b", text)
    return float(match.group(1)) if match else None


def _extract_target_volume(text: str) -> float | None:
    match = re.search(
        r"(?:around|about|roughly|target(?:ing)?|looking for|want(?:ing)?|near)\D{0,24}"
        r"([1-9][0-9](?:\.[0-9])?)\s*(?:l|lits?|litres?)\b",
        text,
    )
    if match:
        return float(match.group(1))
    if any(token in text for token in ["stock", "board", "do you have", "find me", "show me"]):
        match = re.search(r"\b([1-9][0-9](?:\.[0-9])?)\s*(?:l|lits?|litres?)\b", text)
        return float(match.group(1)) if match else None
    return None


def _extract_age(text: str) -> int | None:
    match = re.search(r"\b(?:age(?:d)?\s*)?([1-8][0-9])\s*(?:years? old|yo)\b", text)
    if not match:
        match = re.search(
            r"\b(?:i(?:'m|m| am))\s+([1-8][0-9])\b"
            r"(?!\s*(?:kgs?|kilograms?|kilos?|cm|ft|feet|foot|l|litre|litres)\b)",
            text,
        )
    if not match:
        match = re.search(r"\b([1-8][0-9])\b(?=,\s*(?:intermediate|advanced|expert|beginner|goofy|regular|fit|surfer))", text)
    return int(match.group(1)) if match else None


def _age_band(age: int | None) -> str | None:
    if age is None:
        return None
    if age < 18:
        return "Teen"
    if age < 30:
        return "20s"
    if age < 40:
        return "30s"
    if age < 50:
        return "40s"
    if age < 60:
        return "50s"
    return "60+"


def _extract_fitness(text: str) -> str | None:
    if re.search(r"\bfit\b", text):
        return "High"
    if re.search(r"\bsurf(?:ing)?\s+(?:every\s*day|everyday|daily)\b", text):
        return "High"
    for token, label in [
        ("low fitness", "Low"),
        ("not very fit", "Low"),
        ("poor fitness", "Low"),
        ("high fitness", "High"),
        ("very fit", "High"),
        ("strong paddler", "High"),
        ("average fitness", "Average"),
        ("moderate fitness", "Average"),
    ]:
        if token in text:
            return label
    return None


def _extract_paddle_strength(text: str) -> str | None:
    if any(token in text for token in ["strong paddler", "strong paddle"]):
        return "Strong"
    if any(token in text for token in ["weak paddler", "poor paddler", "weak paddle"]):
        return "Weak"
    if "average paddler" in text:
        return "Average"
    return None


def _extract_frequency(text: str) -> float | None:
    match = re.search(r"\b([0-7](?:\.5)?)\s*(?:times?|sessions?)\s*(?:a|per)\s*week\b", text)
    if match:
        return float(match.group(1))
    if ((re.search(r"\b(?:daily|every\s*day|everyday)\b", text) and "daily driver" not in text) or "most days" in text):
        return 5.0
    if "once or twice a week" in text or "one or two times a week" in text:
        return 1.5
    if "twice a week" in text or "two times a week" in text:
        return 2.0
    if "weekly" in text or "once a week" in text:
        return 1.0
    if "weekend surfer" in text or "surf on weekends" in text:
        return 1.5
    return None


def _extract_board_type(text: str) -> str | None:
    options = [
        "performance shortboard",
        "daily shortboard",
        "daily driver",
        "everyday shortboard",
        "shortboard",
        "groveller",
        "groveler",
        "hybrid",
        "fish",
        "mid-length",
        "mid length",
        "longboard",
        "step up",
        "step-up",
    ]
    value = next((item for item in options if item in text), None)
    return value.title() if value else None


def _extract_preferred_feel(text: str) -> str | None:
    for token, label in PREFERENCE_TOKENS.items():
        if token in text:
            return label
    return None


def _extract_ability(text: str) -> str | None:
    ability_phrases = [
        ("Expert", [r"\bexpert\b"]),
        ("Advanced", [r"\badvanced\b", r"\bexperienced(?: surfer)?\b"]),
        ("Upper Intermediate", [r"\bupper intermediate\b"]),
        ("Intermediate", [
            r"\bintermediate\b",
            r"\bgood\s*(?:or|/)\s*average(?:\s+surfer)?\b",
            r"\bgood\s+surfer\b",
            r"\baverage\s+surfer\b",
            r"\bdecent(?:\s+surfer)?\b",
        ]),
        ("Lower Intermediate", [r"\blower intermediate\b"]),
        ("Progressing Beginner", [r"\bprogressing beginner\b"]),
        ("Beginner", [r"\bbeginner\b", r"\bnovice\b", r"\blearning\b"]),
    ]
    for ability, patterns in ability_phrases:
        if any(re.search(pattern, text) for pattern in patterns):
            return ability
    return None


def _extract_wave_size(text: str) -> tuple[str | None, float | None, float | None]:
    match = re.search(r"\b([1-9](?:\.[0-9])?)\s*(?:to|-)\s*([1-9](?:\.[0-9])?)\s*(?:ft|foot|feet)\b", text)
    if match:
        low = float(match.group(1))
        high = float(match.group(2))
        return f"{low:g}-{high:g}ft", low, high
    match = re.search(r"\b([1-9](?:\.[0-9])?)\s*(?:ft|foot|feet)\b", text)
    if match:
        value = float(match.group(1))
        return f"{value:g}ft", value, value
    return None, None, None


def _extract_wave_type(text: str) -> str | None:
    options = {
        "beachie": "Beach Break",
        "beach": "Beach Break",
        "reef": "Reef Break",
        "point": "Point Break",
        "slab": "Slab",
        "river": "River Mouth",
        "mixed": "Mixed",
    }
    for token, label in options.items():
        if re.search(rf"\b{re.escape(token)}(?:es|s)?\b", text):
            return label
    return None


def _extract_wave_power(text: str) -> str | None:
    if any(token in text for token in ["small waves", "weak waves", "weaker surf", "soft waves", "gutless", "mushy"]):
        return "Weak"
    if any(token in text for token in ["powerful waves", "heavy waves", "punchy"]):
        return "Powerful"
    if "very powerful" in text:
        return "Very Powerful"
    if re.search(r"\bgood (?:waves?|reef|beach|point)", text):
        return "Average to Powerful"
    return None


def _extract_wave_quality(text: str) -> str | None:
    if any(token in text for token in ["clean", "good waves", "quality waves"]):
        return "Clean"
    if any(token in text for token in ["average waves", "wind affected", "messy"]):
        return "Average"
    return None


def _extract_goal(text: str) -> str | None:
    found = []
    for token, label in GOAL_TOKENS.items():
        if token in text:
            found.append(label)
    return ", ".join(dict.fromkeys(found)) or None


def _extract_stance(text: str) -> str | None:
    if "goofy" in text:
        return "Goofy"
    if "regular" in text:
        return "Regular"
    return None


def _extract_construction_preference(text: str) -> str | None:
    carbon_epoxy = [
        "carbon", "carbotune", "spinetek", "spine-tek", "eps", "epoxy", "hyfi",
        "helium", "ibolic", "i-bolic", "futureflex", "dark arts", "black sheep",
        "lightspeed", "lib-tech", "varial", "thunderbolt", "xtr",
    ]
    return "carbon_or_epoxy" if any(token in text for token in carbon_epoxy) else None


def _extract_requested_construction(text: str) -> str | None:
    constructions = [
        "carbotune", "spinetek", "spine-tek", "hyfi", "helium", "ibolic", "i-bolic",
        "futureflex", "lightspeed", "black sheep", "lib-tech", "dark arts", "xtr", "pu", "eps",
    ]
    found = next((value for value in constructions if re.search(rf"\b{re.escape(value)}\b", text)), None)
    return found.replace("-", " ").title() if found else None


def _extract_requested_length(text: str) -> str | None:
    match = re.search(r"\b([4-9])\s*['’]\s*(\d{1,2})(?:\s*(?:\"|in))?\b", text)
    return f"{match.group(1)}'{int(match.group(2))}" if match else None


def _extract_requested_brand(text: str) -> str | None:
    if not text.strip():
        return None
    expansion_brand = canonical_manufacturer_name(text)
    if expansion_brand:
        return expansion_brand
    aliases = {"js": "JS Industries", "ci": "Channel Islands", "lost": "Lost"}
    for token, brand in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return brand
    try:
        brands = sorted({str(row.get("brand") or "") for row in load_graph().get("boards", [])}, key=len, reverse=True)
    except Exception:
        return None
    return next((brand for brand in brands if brand and re.search(rf"\b{re.escape(brand.lower())}\b", text)), None)


def _extract_region(text: str, explicit_region: str | None = None) -> str | None:
    aliases = [
        (r"\b(?:europe|eu)\b", "EU"),
        (r"\b(?:australia|australian|aus|au)\b", "AU"),
        (r"\b(?:united states|usa|us)\b", "US"),
        (r"\b(?:indonesia|indonesian|indo|bali|id)\b", "ID"),
    ]
    for pattern, code in aliases:
        if re.search(pattern, text):
            return code
    return normalise_region(explicit_region) or ("US" if (explicit_region or "").strip().upper() == "US" else explicit_region)


def _extract_current_board(text: str) -> str | None:
    if not re.search(r"\b(?:i ride|i'm riding|im riding|my current board|currently ride)\b", text):
        return None
    aliases = {
        "hypto": "Haydenshapes Hypto Krypto",
        "rnf": "Lost RNF 96",
        "seaside": "Firewire Seaside",
        "monsta": "JS Industries Monsta",
        "phantom": "Pyzel Phantom",
    }
    for alias, canonical in aliases.items():
        if re.search(rf"\b{alias}\b", text):
            return canonical
    matches = []
    for board in load_graph().get("boards", []):
        brand = str(board.get("brand") or "")
        model = str(board.get("model") or "")
        if model.lower() in {"what", "why", "how", "when", "where"}:
            continue
        if model and re.search(rf"\b{re.escape(model.lower())}\b", text):
            matches.append((len(model), f"{brand} {model}"))
    return max(matches, default=(0, None))[1]


def _board_parts(board_name: str | None) -> tuple[str | None, str | None]:
    if not board_name:
        return None, None
    for board in load_graph().get("boards", []):
        candidate = f"{board.get('brand')} {board.get('model')}".strip().lower()
        if candidate == board_name.lower():
            return board.get("brand"), board.get("model")
    parts = board_name.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, board_name


def _extract_current_board_feedback(text: str) -> str | None:
    feedback_tokens = [
        "too small", "too big", "too corky", "hard to paddle", "easy to paddle",
        "too stiff", "too tracky", "too loose", "feels good", "works well",
    ]
    found = [token for token in feedback_tokens if token in text]
    return ", ".join(found) or None


def extract_profile_result(message: str, region: str | None = None) -> ProfileExtractionResult:
    text = (message or "").lower()
    wave_size, wave_min, wave_max = _extract_wave_size(text)
    age = _extract_age(text)
    current_board = _extract_current_board(text)
    current_board_brand, current_board_model = _board_parts(current_board)
    current_volume = _extract_current_volume(text)
    explicit_region = _extract_region(text, None)
    resolved_region = explicit_region or _extract_region(text, region)

    profile = RiderProfile(
        height_cm=_extract_height_cm(text),
        weight_kg=_extract_weight_kg(text),
        age=age,
        age_band=_age_band(age),
        ability=_extract_ability(text),
        surf_frequency_per_week=_extract_frequency(text),
        fitness=_extract_fitness(text),
        paddle_strength=_extract_paddle_strength(text),
        stance=_extract_stance(text),
        region=resolved_region,
        home_break_type=_extract_wave_type(text),
        wave_type=_extract_wave_type(text),
        wave_size=wave_size,
        wave_size_min_ft=wave_min,
        wave_size_max_ft=wave_max,
        wave_power=_extract_wave_power(text),
        wave_quality=_extract_wave_quality(text),
        preferred_board_type=_extract_board_type(text),
        preferred_feel=_extract_preferred_feel(text),
        goal=_extract_goal(text),
        construction_preference=_extract_construction_preference(text),
        requested_construction=_extract_requested_construction(text),
        requested_length=_extract_requested_length(text),
        requested_brand=_extract_requested_brand(text),
        current_board=current_board,
        current_board_brand=current_board_brand,
        current_board_model=current_board_model,
        current_board_length=_extract_requested_length(text) if current_board else None,
        current_volume_litres=current_volume,
        current_board_volume_litres=current_volume,
        current_board_feedback=_extract_current_board_feedback(text),
        target_volume_litres=_extract_target_volume(text),
        profile_sources=["message"] if message else [],
    )

    confidence_by_field = {}
    evidence_by_field = {}
    field_provenance = {}
    for field, value in profile.model_dump(exclude_none=True).items():
        if field in {"profile_sources", "field_provenance"}:
            continue
        confidence_by_field[field] = 0.85 if field in {"weight_kg", "height_cm", "age", "wave_size_min_ft", "wave_size_max_ft"} else 0.7
        evidence_by_field[field] = message.strip()
        field_provenance[field] = "inferred" if field == "region" and resolved_region and not explicit_region else "current_user"

    profile.field_provenance = field_provenance

    return ProfileExtractionResult(
        profile=profile,
        confidence_by_field=confidence_by_field,
        evidence_by_field=evidence_by_field,
        conflicts=[],
    )


def extract_profile(message: str, region: str | None = None) -> RiderProfile:
    return extract_profile_result(message, region).profile


def with_profile_source(profile: RiderProfile, source: str) -> RiderProfile:
    clone = profile.model_copy(deep=True)
    clone.profile_sources = [source]
    provenance = dict(clone.field_provenance)
    for field, value in clone.model_dump().items():
        if field in {"profile_sources", "profile_conflicts", "field_provenance"} or value in (None, "", [], {}):
            continue
        if provenance.get(field) in {None, "", "default"}:
            provenance[field] = source
    clone.field_provenance = provenance
    return clone


def _source_priority(source: str | None) -> int:
    return SOURCE_PRIORITY.get(source or "default", 0)


def _field_source(profile: RiderProfile | None, field: str) -> str:
    if not profile:
        return "default"
    if profile.field_provenance.get(field):
        return profile.field_provenance[field]
    return profile.profile_sources[0] if profile.profile_sources else "default"


def _merge_scalar(current: object, incoming: object, current_source: str, incoming_source: str) -> object:
    if incoming in (None, "", [], {}):
        return current
    if current in (None, "", [], {}):
        return incoming
    return incoming if _source_priority(incoming_source) >= _source_priority(current_source) else current


def _merge_sources(*profiles: RiderProfile | None) -> list[str]:
    values = []
    for profile in profiles:
        if not profile:
            continue
        for source in profile.profile_sources:
            if source not in values:
                values.append(source)
    return values


def _build_conflict(field: str, existing: object, incoming: object) -> str | None:
    if existing in (None, "", [], {}) or incoming in (None, "", [], {}) or existing == incoming:
        return None
    if field == "ability":
        old_rank = ABILITY_ORDER.get(str(existing), 0)
        new_rank = ABILITY_ORDER.get(str(incoming), 0)
        if abs(new_rank - old_rank) <= 1:
            return None
    return f"{field}: {existing} -> {incoming}"


def merge_rider_profile(
    existing_profile: RiderProfile | None,
    extracted_profile: RiderProfile,
    account_profile: RiderProfile | None = None,
) -> RiderProfile:
    base = (account_profile or RiderProfile()).model_dump()
    field_provenance = dict((account_profile.field_provenance if account_profile else {}) or {})
    if account_profile:
        for field, value in account_profile.model_dump().items():
            if field in {"profile_sources", "profile_conflicts", "field_provenance"} or value in (None, "", [], {}):
                continue
            field_provenance.setdefault(field, "account_profile")
    conflicts = list((account_profile.profile_conflicts if account_profile else []) or [])

    for profile in [existing_profile, extracted_profile]:
        if not profile:
            continue
        for field, incoming in profile.model_dump().items():
            if field in {"profile_sources", "profile_conflicts", "field_provenance"}:
                continue
            current = base.get(field)
            current_source = field_provenance.get(field, _field_source(account_profile, field))
            incoming_source = _field_source(profile, field)
            allow_correction = incoming_source == "current_user" and current_source in {
                "account_profile", "saved_profile", "conversation_user", "conversation_profile", "inferred", "current_user",
            } and field in CORRECTION_FIELDS
            conflict = None if allow_correction else _build_conflict(field, current, incoming)
            if conflict and conflict not in conflicts:
                conflicts.append(conflict)
            merged_value = _merge_scalar(current, incoming, current_source, incoming_source)
            base[field] = merged_value
            if merged_value == incoming and incoming not in (None, "", [], {}):
                field_provenance[field] = incoming_source

    merged = RiderProfile(**base)
    if merged.home_break_type and not merged.wave_type:
        merged.wave_type = merged.home_break_type
    if merged.wave_type and not merged.home_break_type:
        merged.home_break_type = merged.wave_type
    if merged.current_board_volume_litres is None and merged.current_volume_litres is not None:
        merged.current_board_volume_litres = merged.current_volume_litres
    if merged.current_volume_litres is None and merged.current_board_volume_litres is not None:
        merged.current_volume_litres = merged.current_board_volume_litres
    merged.profile_sources = _merge_sources(account_profile, existing_profile, extracted_profile)
    merged.profile_conflicts = conflicts
    merged.field_provenance = field_provenance
    merged.confidence = profile_completeness(merged)
    return merged


def merge_profiles(*profiles: RiderProfile) -> RiderProfile:
    merged = RiderProfile()
    for profile in profiles:
        merged = merge_rider_profile(merged, profile)
    return merged


def profile_completeness(profile: RiderProfile) -> float:
    present = sum(1 for field in PROFILE_COMPLETENESS_FIELDS if getattr(profile, field, None) not in (None, ""))
    return round(present / len(PROFILE_COMPLETENESS_FIELDS), 2)


def missing_profile_fields(profile: RiderProfile) -> list[str]:
    required = {
        "weight_kg": "weight",
        "ability": "ability",
        "surf_frequency_per_week": "surf frequency",
        "wave_size_min_ft": "usual waves",
        "region": "search region",
    }
    missing = []
    for field_name, label in required.items():
        if getattr(profile, field_name) in [None, ""]:
            missing.append(label)
    return missing


def build_recommendation(profile: RiderProfile) -> BoardRecommendation | None:
    if not profile.weight_kg or not profile.ability:
        return None
    fit = recommend_rider_fit(profile)
    if fit is None:
        return None

    ability = (profile.ability or "Intermediate").lower()
    wave_type = profile.wave_type or "Beach Break"
    if wave_type in ["Point Break", "Reef Break"] and ability != "beginner":
        construction_notes = "A slightly more refined rail and better hold will help if the waves have shape or push."
    else:
        construction_notes = "Keep some foam under the chest and avoid going too narrow if the waves are soft or broken up."

    return BoardRecommendation(
        board_category=fit.board_category,
        suggested_length_range=("7'0 to 8'0" if "beginner" in ability else "5'8 to 6'3"),
        suggested_volume_range_litres=fit.volume_range_label,
        construction_notes=construction_notes,
        why_it_fits=fit.explanation,
        quivrr_search_direction=(
            f"Search {(profile.region or 'your selected region')} for available boards in this category and volume range."
        ),
        adjustment_factors=fit.adjustment_factors,
    )


def build_profile_reply(profile: RiderProfile, missing: list[str], recommendation: BoardRecommendation | None) -> str:
    if not any([
        profile.height_cm,
        profile.weight_kg,
        profile.ability,
        profile.preferred_board_type,
        profile.current_board,
        profile.current_volume_litres,
        profile.target_volume_litres,
    ]):
        return (
            "Can’t find what you’re looking for, or not sure what you want yet? I’ve got access to live "
            "board availability across Quivrr. Tell me how you surf, where you’re searching, and what kind "
            "of board you’re chasing, and I’ll help narrow it down."
        )
    if recommendation is None:
        questions = ", ".join(missing[:1])
        return (
            "Good start. I need a bit more before I can point you at the right board. "
            f"Can you tell me your {questions}? "
            "If you know your current board size or litres, add that too."
        )

    return (
        "Alright, that is enough to get you moving.\n\n"
        f"Recommended board type: {recommendation.board_category}\n"
        f"Suggested length range: {recommendation.suggested_length_range}\n"
        f"Suggested volume range: {recommendation.suggested_volume_range_litres}\n\n"
        f"Adjustments: {'; '.join(recommendation.adjustment_factors) or 'Baseline only'}\n\n"
        f"Why: {recommendation.why_it_fits}\n\n"
        f"Search next: {recommendation.quivrr_search_direction}"
    )
