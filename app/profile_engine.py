
import re

from app.models import BoardRecommendation, RiderProfile


def _extract_height_cm(text: str) -> int | None:
    match = re.search(r"\b(1[4-9][0-9]|20[0-9]|21[0-9])\s*cm\b", text)
    if match:
        return int(match.group(1))
    return None


def _extract_weight_kg(text: str) -> int | None:
    match = re.search(r"\b([4-9][0-9]|1[0-4][0-9])\s*kg\b", text)
    if match:
        return int(match.group(1))
    return None


def _extract_current_volume(text: str) -> float | None:
    match = re.search(r"\b([1-9][0-9](?:\.[0-9])?)\s*(?:l|litre|litres)\b", text)
    if match:
        return float(match.group(1))
    return None


def _extract_ability(text: str) -> str | None:
    for ability in ["beginner", "intermediate", "advanced", "expert"]:
        if ability in text:
            return ability.title()
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
        "beach": "Beach Break",
        "reef": "Reef Break",
        "point": "Point Break",
        "slab": "Slab",
        "river": "River Mouth",
    }

    for token, label in options.items():
        if token in text:
            return label

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


def _extract_region(text: str, explicit_region: str | None = None) -> str | None:
    if explicit_region:
        return explicit_region

    regions = [
        "australia",
        "united states",
        "canada",
        "europe",
        "united kingdom",
        "indonesia",
        "japan",
        "brazil",
    ]

    for region in regions:
        if region in text:
            return region.title()

    return None


def extract_profile(message: str, region: str | None = None) -> RiderProfile:
    text = message.lower()

    return RiderProfile(
        height_cm=_extract_height_cm(text),
        weight_kg=_extract_weight_kg(text),
        ability=_extract_ability(text),
        current_volume_litres=_extract_current_volume(text),
        region=_extract_region(text, region),
        wave_size=_extract_wave_size(text),
        wave_type=_extract_wave_type(text),
        goal=_extract_goal(text),
    )


def missing_profile_fields(profile: RiderProfile) -> list[str]:
    required = {
        "height_cm": "height",
        "weight_kg": "weight",
        "ability": "ability",
        "region": "region",
        "wave_size": "normal wave size",
        "wave_type": "wave type",
        "goal": "what you want the board to do better",
    }

    missing = []
    for field_name, label in required.items():
        if getattr(profile, field_name) in [None, ""]:
            missing.append(label)

    return missing


def build_recommendation(profile: RiderProfile) -> BoardRecommendation | None:
    missing = missing_profile_fields(profile)

    if len(missing) > 2:
        return None

    weight = profile.weight_kg or 80
    ability = (profile.ability or "Intermediate").lower()
    wave_type = profile.wave_type or "Beach Break"
    goal = (profile.goal or "").lower()

    if ability == "beginner":
        volume_low = round(weight * 0.55)
        volume_high = round(weight * 0.70)
        category = "Funboard, mini mal or forgiving mid length"
        length_range = "7'0 to 8'0"
    elif "paddle" in goal or "catch more waves" in goal:
        volume_low = round(weight * 0.40)
        volume_high = round(weight * 0.44)
        category = "Hybrid shortboard, groveller or performance fish"
        length_range = "5'8 to 6'2"
    elif ability in ["advanced", "expert"]:
        volume_low = round(weight * 0.32)
        volume_high = round(weight * 0.38)
        category = "Performance shortboard or refined everyday shortboard"
        length_range = "5'10 to 6'2"
    else:
        volume_low = round(weight * 0.37)
        volume_high = round(weight * 0.45)
        category = "Everyday shortboard, hybrid or groveller"
        length_range = "5'9 to 6'3"

    if wave_type in ["Point Break", "Reef Break"] and ability.lower() != "beginner":
        construction_notes = "A slightly more refined rail and better hold will help if the waves have shape or push."
    else:
        construction_notes = "Keep some foam under the chest and avoid going too narrow if the waves are soft or broken up."

    return BoardRecommendation(
        board_category=category,
        suggested_length_range=length_range,
        suggested_volume_range_litres=f"{volume_low} to {volume_high}L",
        construction_notes=construction_notes,
        why_it_fits=(
            "This gives you enough paddle support to catch more waves while keeping the board responsive enough to turn. "
            "For everyday surf, the goal is usually to avoid going too high performance too early."
        ),
        quivrr_search_direction=(
            "Start with the Australia region, then search everyday shortboards, hybrids, grovellers and fish style boards in this volume range."
        ),
    )


def build_profile_reply(profile: RiderProfile, missing: list[str], recommendation: BoardRecommendation | None) -> str:
    if recommendation is None:
        questions = ", ".join(missing[:4])
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
        f"Why: {recommendation.why_it_fits}\n\n"
        f"Search next: {recommendation.quivrr_search_direction}"
    )
