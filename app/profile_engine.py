
import re

from app.board_graph_engine import load_graph
from app.models import BoardRecommendation, RiderProfile
from app.rider_fit import recommend_rider_fit


def _extract_height_cm(text: str) -> int | None:
    match = re.search(r"\b(1[4-9][0-9]|20[0-9]|21[0-9])\s*(?:cm|(?:in\s+)?height)\b", text)
    if match:
        return int(match.group(1))
    return None


def _extract_weight_kg(text: str) -> int | None:
    match = re.search(r"\b([4-9][0-9]|1[0-4][0-9])\s*(?:kgs?|kilograms?|kilos?)\b", text)
    if match:
        return int(match.group(1))
    return None


def _extract_current_volume(text: str) -> float | None:
    if any(token in text for token in ["around", "looking for", "want", "target"]):
        return None
    match = re.search(r"\b([1-9][0-9](?:\.[0-9])?)\s*(?:l|litre|litres)\b", text)
    if match:
        return float(match.group(1))
    return None


def _extract_target_volume(text: str) -> float | None:
    match = re.search(
        r"(?:around|about|roughly|target(?:ing)?|looking for|want(?:ing)?)\D{0,24}"
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
        match = re.search(r"\b(?:i(?:'m|m| am))\s+([1-8][0-9])\b", text)
    return int(match.group(1)) if match else None


def _extract_fitness(text: str) -> str | None:
    if re.search(r"\bfit\b", text):
        return "High"
    if re.search(r"\bsurf(?:ing)?\s+(?:every\s*day|everyday|daily)\b", text):
        return "High"
    for token, label in [
        ("low fitness", "Low"), ("not very fit", "Low"), ("poor fitness", "Low"),
        ("high fitness", "High"), ("very fit", "High"), ("strong paddler", "High"),
        ("average fitness", "Average"), ("moderate fitness", "Average"),
    ]:
        if token in text:
            return label
    return None


def _extract_frequency(text: str) -> float | None:
    match = re.search(r"\b([0-7](?:\.5)?)\s*(?:times?|sessions?)\s*(?:a|per)\s*week\b", text)
    if match:
        return float(match.group(1))
    if ((re.search(r"\b(?:daily|every\s*day|everyday)\b", text) and "daily driver" not in text)
            or "most days" in text):
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
        "performance shortboard", "daily driver", "everyday shortboard", "shortboard",
        "groveller", "groveler", "hybrid", "fish", "mid-length", "mid length", "longboard",
        "step up", "step-up",
    ]
    return next((value.title() for value in options if value in text), None)


def _extract_desired_feel(text: str) -> str | None:
    options = [
        "easier paddle", "more performance", "more forgiving", "faster in weak waves",
        "hold in bigger waves",
    ]
    found = [value for value in options if value in text]
    return ", ".join(found) or None


def _extract_ability(text: str) -> str | None:
    ability_phrases = [
        ("Expert", [r"\bexpert\b"]),
        ("Advanced", [r"\badvanced\b", r"\bexperienced(?: surfer)?\b"]),
        ("Intermediate", [
            r"\bintermediate\b", r"\bgood\s*(?:or|/)\s*average(?:\s+surfer)?\b",
            r"\bgood(?:\s+surfer)?\b", r"\baverage(?:\s+surfer)?\b", r"\bdecent(?:\s+surfer)?\b",
        ]),
        ("Beginner", [r"\bbeginner\b", r"\bnovice\b", r"\blearning\b"]),
    ]
    for ability, patterns in ability_phrases:
        if any(re.search(pattern, text) for pattern in patterns):
            return ability
    return None


def _extract_wave_size(text: str) -> str | None:
    match = re.search(r"\b([1-9])\s*(?:to|-)\s*([1-9])\s*(?:ft|foot|feet)\b", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}ft"

    match = re.search(r"\b([1-9])\s*(?:ft|foot|feet)\b", text)
    if match:
        return f"{match.group(1)}ft"

    return None


def _extract_wave_type(text: str) -> str | None:
    options = {
        "beachie": "Beach Break",
        "beach": "Beach Break",
        "reef": "Reef Break",
        "point": "Point Break",
        "slab": "Slab",
        "river": "River Mouth",
    }

    for token, label in options.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return label

    return None


def _extract_wave_power(text: str) -> str | None:
    if any(token in text for token in ["small waves", "weak waves", "soft waves", "gutless", "mushy"]):
        return "Weak"
    if any(token in text for token in ["powerful waves", "heavy waves", "punchy"]):
        return "Powerful"
    if re.search(r"\bgood (?:waves?|reef|beach|point)", text):
        return "Average to Powerful"
    return None


def _extract_goal(text: str) -> str | None:
    goal_tokens = [
        "paddle power",
        "paddle",
        "speed",
        "turn",
        "turns",
        "loose",
        "hold",
        "performance",
        "stability",
        "catch more waves",
    ]

    found = [token for token in goal_tokens if token in text]
    if not found:
        return None

    readable = []
    for token in found:
        if token == "paddle":
            readable.append("More paddle power")
        elif token in ["turn", "turns"]:
            readable.append("Tighter turns")
        elif token == "loose":
            readable.append("More looseness")
        elif token == "catch more waves":
            readable.append("Catch more waves")
        else:
            readable.append(token.title())

    return ", ".join(dict.fromkeys(readable))


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
    aliases = {"js": "JS Industries", "ci": "Channel Islands", "lost": "Lost"}
    for token, brand in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return brand
    brands = sorted({str(row.get("brand") or "") for row in load_graph().get("boards", [])}, key=len, reverse=True)
    return next((brand for brand in brands if brand and re.search(rf"\b{re.escape(brand.lower())}\b", text)), None)


def _extract_region(text: str, explicit_region: str | None = None) -> str | None:
    aliases = [
        (r"\b(?:europe|eu)\b", "EU"),
        (r"\b(?:australia|australian|aus|au)\b", "AU"),
        (r"\b(?:indonesia|indonesian|indo|bali|id)\b", "ID"),
    ]
    for pattern, code in aliases:
        if re.search(pattern, text):
            return code
    return explicit_region


def _extract_current_board(text: str) -> str | None:
    if not re.search(r"\b(?:i ride|i'm riding|im riding|my current board|currently ride)\b", text):
        return None
    matches = []
    for board in load_graph().get("boards", []):
        brand = str(board.get("brand") or "")
        model = str(board.get("model") or "")
        if model.lower() in {"what", "why", "how", "when", "where"}:
            continue
        if model and re.search(rf"\b{re.escape(model.lower())}\b", text):
            matches.append((len(model), f"{brand} {model}"))
    return max(matches, default=(0, None))[1]


def extract_profile(message: str, region: str | None = None) -> RiderProfile:
    text = message.lower()

    return RiderProfile(
        height_cm=_extract_height_cm(text),
        weight_kg=_extract_weight_kg(text),
        ability=_extract_ability(text),
        current_board=_extract_current_board(text),
        current_volume_litres=_extract_current_volume(text),
        target_volume_litres=_extract_target_volume(text),
        age=_extract_age(text),
        fitness_level=_extract_fitness(text),
        surf_frequency_per_week=_extract_frequency(text),
        preferred_board_type=_extract_board_type(text),
        desired_feel=_extract_desired_feel(text),
        region=_extract_region(text, region),
        wave_size=_extract_wave_size(text),
        wave_type=_extract_wave_type(text),
        wave_power=_extract_wave_power(text),
        goal=_extract_goal(text),
        construction_preference=_extract_construction_preference(text),
        requested_construction=_extract_requested_construction(text),
        requested_length=_extract_requested_length(text),
        requested_brand=_extract_requested_brand(text),
    )


def merge_profiles(*profiles: RiderProfile) -> RiderProfile:
    merged = {}
    for profile in profiles:
        for field, value in profile.model_dump().items():
            if value not in (None, ""):
                merged[field] = value
    return RiderProfile(**merged)


def missing_profile_fields(profile: RiderProfile) -> list[str]:
    required = {
        "weight_kg": "weight",
        "ability": "ability",
        "surf_frequency_per_week": "surf frequency",
        "wave_size": "usual waves",
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
        suggested_length_range=("7'0 to 8'0" if ability == "beginner" else "5'8 to 6'3"),
        suggested_volume_range_litres=fit.volume_range_label,
        construction_notes=construction_notes,
        why_it_fits=(
            fit.explanation
        ),
        quivrr_search_direction=(
            f"Search {(profile.region or 'your selected region')} for available boards in this category and volume range."
        ),
        adjustment_factors=fit.adjustment_factors,
    )


def build_profile_reply(profile: RiderProfile, missing: list[str], recommendation: BoardRecommendation | None) -> str:
    if not any([
        profile.height_cm, profile.weight_kg, profile.ability, profile.preferred_board_type,
        profile.current_board, profile.current_volume_litres, profile.target_volume_litres,
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
