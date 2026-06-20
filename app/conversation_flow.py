from __future__ import annotations

from app.board_graph_engine import board_key, find_board, load_graph
from app.inventory_client import normalise_region
from app.models import BodhiRecommendation, RiderProfile, SuggestedBoard, VolumeGuidance
from app.rider_fit import recommend_rider_fit


REGION_NAMES = {"AU": "Australian", "EU": "European", "ID": "Indonesian"}


def opening_message(region: str | None) -> str:
    code = normalise_region(region)
    availability = (
        "Indonesian board availability where feeds exist" if code == "ID"
        else f"live {REGION_NAMES[code]} board availability" if code
        else "live board availability across Quivrr"
    )
    return (
        "Can’t find what you’re looking for, or not sure what you want yet? I’ve got access to "
        f"{availability}. Tell me how you surf, where you’re searching, and what kind of board "
        "you’re chasing, and I’ll help narrow it down."
    )


def has_intake_signal(profile: RiderProfile) -> bool:
    return any(value not in (None, "") for field, value in profile.model_dump().items() if field != "region")


def intake_questions(profile: RiderProfile) -> list[str]:
    questions = []
    waves_missing = not profile.wave_size and not profile.wave_type
    if not profile.weight_kg and waves_missing:
        questions.append("What’s your rough weight, and what sort of waves are you mainly surfing?")
    elif not profile.weight_kg:
        questions.append("Roughly how much do you weigh?")
    elif waves_missing:
        questions.append("What size and type of waves are you mainly surfing?")

    if not profile.ability and len(questions) < 2:
        questions.append("How would you describe your surfing level—beginner, intermediate, advanced, or expert?")
    if profile.surf_frequency_per_week is None and len(questions) < 2:
        questions.append("About how often are you surfing each week?")
    if not normalise_region(profile.region) and len(questions) < 2:
        questions.append("Which region should I search: Australia, Europe, or Indonesia?")
    return questions[:2]


def enough_for_recommendations(profile: RiderProfile) -> bool:
    return bool(
        profile.weight_kg
        and profile.ability
        and normalise_region(profile.region)
        and (profile.wave_size or profile.wave_type)
    )


def volume_guidance(profile: RiderProfile) -> VolumeGuidance | None:
    fit = recommend_rider_fit(profile)
    if fit is None:
        return None
    return VolumeGuidance(
        minimumLitres=fit.volume_low,
        maximumLitres=fit.volume_high,
        label=fit.volume_range_label,
        recommendedCategory=fit.board_category,
        reasoning=fit.explanation,
    )


def graph_suggestions(profile: RiderProfile, relation: str) -> list[SuggestedBoard]:
    if not profile.current_board:
        return []
    graph = load_graph()
    current_key = board_key("", profile.current_board)[1]
    current = next(
        (row for row in graph.get("boards", []) if current_key.endswith(board_key(row.get("brand"), row.get("model"))[1])),
        None,
    )
    if not current:
        return []
    suggestions = []
    for edge in current.get("recommendations", {}).get(relation, [])[:4]:
        board = find_board(graph, edge["brand"], edge["model"])
        wave = board.get("dna", {}).get("waveRange", {}) if board else {}
        wave_label = None
        if wave.get("minFt") is not None and wave.get("maxFt") is not None:
            wave_label = f"{wave['minFt']:g}-{wave['maxFt']:g}ft"
        suggestions.append(SuggestedBoard(
            brand=edge["brand"], model=edge["model"], category=edge.get("primaryCategory") or "Surfboard",
            confidence=min(float(edge.get("score", 0)) / 100, 0.96),
            why_it_fits=f"{edge.get('reason') or 'Close canonical board profile'}; {relation.replace('Boards', '').lower()} from your {current['brand']} {current['model']}",
            volume_range=(f"{board['volumeRange']['min']:g}-{board['volumeRange']['max']:g}L" if board and board.get("volumeRange", {}).get("min") is not None else None),
            wave_range=wave_label,
            skill_fit=(f"{board['surferFit'].get('abilityMin') or 'unspecified'} to {board['surferFit'].get('abilityMax') or 'unspecified'}" if board else None),
            source="quivrr_board_graph",
        ))
    return suggestions


def find_requested_board(message: str) -> dict | None:
    text = board_key("", message)[1]
    if not text or any(phrase in text for phrase in ["i ride", "im riding", "my current board", "currently ride"]):
        return None
    matches = []
    for board in load_graph().get("boards", []):
        brand_key, model_key = board_key(board.get("brand"), board.get("model"))
        model_present = f" {model_key} " in f" {text} "
        brand_present = f" {brand_key} " in f" {text} "
        if model_key and model_present and (brand_present or len(model_key.split()) >= 2):
            matches.append((len(model_key), board))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def suggestions_for_board(board: dict, relations: list[str] | None = None) -> list[SuggestedBoard]:
    graph = load_graph()
    candidates = [board] if relations is None else [
        find_board(graph, edge["brand"], edge["model"])
        for relation in relations
        for edge in board.get("recommendations", {}).get(relation, [])
    ]
    output = []
    seen = set()
    for candidate in candidates:
        if not candidate or board_key(candidate["brand"], candidate["model"]) in seen:
            continue
        seen.add(board_key(candidate["brand"], candidate["model"]))
        taxonomy = candidate["taxonomy"]
        dna = candidate["dna"]
        volume = candidate.get("volumeRange", {})
        wave = dna.get("waveRange", {})
        output.append(SuggestedBoard(
            brand=candidate["brand"], model=candidate["model"], category=taxonomy["primaryCategory"],
            confidence={"high": .9, "medium": .75, "low": .55}.get(taxonomy.get("confidence"), .55),
            why_it_fits=("The board you asked for" if relations is None else
                         f"Canonical {taxonomy['primaryCategory'].replace('_', ' ')} alternative with {dna['boardPersonality'].replace('_', ' ')} design intent"),
            volume_range=(f"{volume['min']:g}-{volume['max']:g}L" if volume.get("min") is not None else None),
            wave_range=(f"{wave['minFt']:g}-{wave['maxFt']:g}ft" if wave.get("minFt") is not None and wave.get("maxFt") is not None else None),
            skill_fit=(f"{candidate['surferFit'].get('abilityMin') or 'unspecified'} to {candidate['surferFit'].get('abilityMax') or 'unspecified'}"),
            source="quivrr_board_graph",
        ))
    return output[:4]


def public_recommendations(boards: list[SuggestedBoard]) -> list[BodhiRecommendation]:
    output = []
    for board in boards:
        if board.manufacturer_direct_count and board.retailer_count:
            source_type = "manufacturer_direct_and_retailer"
        elif board.manufacturer_direct_count:
            source_type = "manufacturer_direct"
        elif board.retailer_count:
            source_type = "retailer"
        else:
            source_type = "no_verified_live_source"
        output.append(BodhiRecommendation(
            brand=board.brand, model=board.model, category=board.category,
            whyItFits=board.why_it_fits,
            suggestedVolumeOrSizeRange=board.suggested_size or board.volume_range,
            waveRange=board.wave_range, skillFit=board.skill_fit,
            availableCount=board.available_count, region=board.region,
            exampleProductUrl=board.example_live_source_url, sourceType=source_type,
            priceRange=board.price_range, confidence=board.confidence,
        ))
    return output


def recommendation_reply(profile: RiderProfile, guidance: VolumeGuidance, boards: list[SuggestedBoard]) -> str:
    base = (
        f"Based on what you’ve told me, {guidance.label} is a sensible starting range—not an exact truth. "
        f"I’d look in the {guidance.recommended_category.lower()} lane."
    )
    available = [board for board in boards if board.available_count > 0]
    if not available:
        return base + f" I can’t verify a matching board in {normalise_region(profile.region)} right now, so I won’t invent stock."
    names = ", ".join(f"{board.brand} {board.model}" for board in available[:3])
    return base + f" The live options I’d check first are {names}."
