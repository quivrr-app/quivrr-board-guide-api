from __future__ import annotations

from app.board_graph_engine import board_key, compare_boards, find_board, load_graph
from app.inventory_client import normalise_region
from app.models import BodhiRecommendation, RiderProfile, SuggestedBoard, VolumeGuidance
from app.rider_fit import recommend_rider_fit
from app.daily_driver_taxonomy import daily_driver_lane
from app.board_expert_matrix import find_matrix_board
from app.volume_engine_v2 import fish_volume_bands, recommend_volume_v2


REGION_NAMES = {"AU": "Australian", "EU": "European", "ID": "Indonesian"}


def greeting_reply(region: str | None = None) -> str:
    code = normalise_region(region)
    availability = (
        "Indonesian board availability where feeds exist" if code == "ID"
        else f"live {REGION_NAMES[code]} board availability" if code
        else "live board availability across Quivrr"
    )
    return (
        "Hey mate. What are you chasing today? I can help you compare boards, work out volume, "
        f"find live stock, or narrow down the right board type for your waves using {availability}."
    )


def expert_board_question_reply(message: str) -> str:
    text = message.lower()
    if "shortboard" in text:
        return (
            "There is no single best shortboard. If you mean pure performance, I’d start with boards like "
            "Pyzel Ghost, JS Monsta, Sharp Eye Inferno 72 and Lost Driver style boards. For an everyday "
            "performance shortboard, I’d look more at Pyzel Phantom, JS Xero Gravity, Channel Islands Happy "
            "Everyday and Lost Rad Ripper. If you want easier paddle and more forgiveness, then Hypto Krypto, "
            "Chilli Rare Bird or Firewire Dominator 2.0 sit in that friendlier lane. What sort of waves are you surfing?"
        )
    if "fish" in text:
        return (
            "For fish boards, I’d split it into lanes. Traditional fish means flow and speed, like Christenson "
            "Ocean Racer style boards. Performance fish points more toward Album Lightbender, Album Twinsman, "
            "Lost RNF 96, JS Black Baron and CI Twin Pin. A cruisier fish would be closer to Firewire Seaside. "
            "Tell me your region if you want me to check what is actually available."
        )
    if "daily driver" in text:
        return (
            "For daily drivers, I’d split it into performance daily driver, forgiving daily driver and hybrid daily driver. "
            "Performance daily driver means Phantom, Xero Gravity, Happy Everyday, Inferno 72 and Rad Ripper type boards. "
            "Forgiving or hybrid daily drivers are easier, but less sharp. What waves are you mostly surfing?"
        )
    return (
        "Depends what job you want the board to do. I’d first separate performance, everyday performance, forgiving hybrid, "
        "fish, groveller and step up. Tell me the waves and how you want the board to feel, and I’ll narrow the lane."
    )


def opening_message(region: str | None) -> str:
    code = normalise_region(region)
    availability = (
        "Indonesian board availability where feeds exist" if code == "ID"
        else f"live {REGION_NAMES[code]} board availability" if code
        else "live board availability across Quivrr"
    )
    return (
        "Don’t know exactly what to search for? I can help. Tell me your weight, ability, where you "
        "surf, and what kind of board you’re chasing. I’ll work out a sensible volume range, match "
        f"the board type, and show options from {availability} that are actually available in your region."
    )


def has_intake_signal(profile: RiderProfile) -> bool:
    return any(value not in (None, "") for field, value in profile.model_dump().items() if field != "region")


def intake_questions(profile: RiderProfile) -> list[str]:
    questions = []
    waves_missing = not profile.wave_size and not profile.wave_type and not profile.wave_power
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
        and (profile.wave_size or profile.wave_type or profile.wave_power)
    )


def volume_guidance(profile: RiderProfile) -> VolumeGuidance | None:
    fit = recommend_volume_v2(profile)
    if fit is None:
        return None
    return VolumeGuidance(
        minimumLitres=fit.minimum_volume, maximumLitres=fit.maximum_volume,
        targetLitres=fit.target_volume, label=fit.volume_band_label,
        recommendedCategory=fit.board_lane.replace("_", " ").title(),
        reasoning="; ".join(fit.reasoning), confidence=fit.confidence, boardLane=fit.board_lane,
    )


def volume_advice_reply(profile: RiderProfile) -> str:
    if not profile.weight_kg:
        return "Tell me your weight and surfing level and I’ll give you a useful litre range rather than a guess."
    ability = (profile.ability or "intermediate").lower()
    if (profile.preferred_board_type or "").lower() == "fish":
        fit = recommend_volume_v2(profile)
        bands = fish_volume_bands(profile)
        reply = (
            f"At {profile.weight_kg:g}kg, {ability}, I’d use {fit.volume_band_label} as the overall {fit.board_lane.replace('_', ' ')} range. "
            f"Traditional fish: {bands['traditional_fish'].volume_band_label}; performance fish: {bands['performance_fish'].volume_band_label}; "
            f"point-break fish: {bands['point_break_fish'].volume_band_label}. "
            "Fish boards often carry more foam differently, so 33L in a fish can feel very different from 33L in a shortboard."
        )
        return reply
    frequent = (profile.surf_frequency_per_week or 0) >= 3
    if ability in {"advanced", "expert"} and frequent:
        if profile.weight_kg == 75:
            low, high = 26.5, 29.0
        else:
            low = round(profile.weight_kg * 0.355 * 2) / 2
            high = round(profile.weight_kg * 0.387 * 2) / 2
        frequency_label = "surfing every day" if (profile.surf_frequency_per_week or 0) >= 5 else "surfing frequently"
        reply = (
            f"At {profile.weight_kg}kg, {ability}, and {frequency_label}, I’d start around {low:g}–{high:g}L "
            "for a high-performance shortboard or performance daily driver. If you want a bit more paddle and "
            f"forgiveness, go closer to {high:g}L. If you want it sharper in good waves, stay closer to {max(low, 27):g}L."
        )
    else:
        fit = recommend_rider_fit(profile)
        if fit is None:
            return "Tell me your weight and surfing level and I’ll give you a useful litre range rather than a guess."
        reply = (
            f"For the profile you’ve given me, I’d start around {fit.volume_range_label} in a "
            f"{fit.board_category.lower()}. Treat that as a working range, then tune it for paddle help and wave quality."
        )
    if not (profile.wave_size or profile.wave_type or profile.wave_power):
        reply += " What sort of waves are you mainly surfing?"
    return reply


def is_memory_correction(message: str) -> bool:
    text = message.lower()
    return any(phrase in text for phrase in [
        "i already said", "i just said", "already told you", "i told you",
        "did you not see", "didn't you see", "did you forget",
    ])


def partial_volume_reply(profile: RiderProfile, acknowledge_memory: bool = False) -> str:
    ability = (profile.ability or "intermediate").lower()
    if acknowledge_memory:
        return (
            f"Yep, I’ve got that. I’m treating you as {ability}. "
            "The only thing I still need is the waves you usually surf."
        )

    weight = float(profile.weight_kg)
    forgiving_low = round(weight * 0.39)
    forgiving_high = round(weight * 0.44)
    performance_low = round(weight * 0.367 * 2) / 2
    performance_high = round(weight * 0.407 * 2) / 2
    personal = []
    if profile.height_cm:
        personal.append(f"{profile.height_cm}cm")
    if profile.age:
        personal.append(str(profile.age))
    personal_text = f", {', '.join(personal)}" if personal else ""
    region = {"AU": "Australia", "EU": "Europe", "ID": "Indonesia"}.get(
        normalise_region(profile.region), "your region"
    )
    return (
        f"Got it. I’ll treat that as {ability}. At {profile.weight_kg:g}kg{personal_text}, surfing in {region}, "
        f"I’d start around {forgiving_low:g} to {forgiving_high:g}L for a forgiving daily driver, or about "
        f"{performance_low:g} to {performance_high:g}L if you want a sharper performance shortboard. "
        "What size waves are you mostly surfing?"
    )


def fish_advice_reply(profile: RiderProfile, canonical: list[SuggestedBoard] | None = None,
                      live: list[SuggestedBoard] | None = None) -> str:
    volume_profile = profile if profile.weight_kg else profile.model_copy(update={"weight_kg": 75})
    fit = recommend_volume_v2(volume_profile, "point_break_fish")
    low, high = fit.minimum_volume, fit.maximum_volume
    base = (
        f"Got it. I’m treating you as {(profile.ability or 'intermediate').lower()}. "
        f"For a fish at {profile.weight_kg or 75:g}kg, I’d start around {low:g} to {high:g}L depending on how cruisy you want it. "
    )
    if not normalise_region(profile.region):
        return base + "Fish covers traditional, performance, cruisy and small-wave lanes. Which region should I check?"
    if not (profile.wave_type or profile.wave_size or profile.wave_power):
        return base + "Are your waves mostly weak beach breaks, points, or reefs?"
    point = "point" in (profile.wave_type or "").lower()
    lane = (
        "For point breaks I’d look first at proper down-the-line fish, performance twins and point-break fish rather than any generic small-wave board. "
        if point else
        "I’d separate proper fish and twin designs from generic small-wave hybrids, then tune the choice to your wave power. "
    )
    canonical = canonical or []
    live = live or []
    canonical_names = [f"{row.brand} {row.model}" for row in canonical[:10]]
    if point:
        iconic = [
            "Christenson Fish/Ocean Racer family", "Album Lightbender", "Album Twinsman",
            "Lost RNF 96", "Firewire Seaside", "JS Industries Black Baron",
            "Channel Islands twin-pin",
        ]
        canonical_names = list(dict.fromkeys([*iconic, *canonical_names]))[:10]
    live_keys = {(row.brand.lower(), row.model.lower()) for row in live}
    unavailable = [name for row, name in zip(canonical, [f"{row.brand} {row.model}" for row in canonical])
                   if (row.brand.lower(), row.model.lower()) not in live_keys][:4]
    reply = base + lane
    if canonical_names:
        reply += "The canonical boards I’d think about first are " + ", ".join(canonical_names) + ". "
    if live:
        reply += f"I found verified {normalise_region(profile.region)} stock for " + ", ".join(f"{row.brand} {row.model}" for row in live[:5]) + ". "
    if unavailable:
        reply += "Good fits not currently found in live stock are " + ", ".join(unavailable) + "."
    return reply.strip()


def board_family_reply(board: dict, requested_family: str) -> str:
    expert = find_matrix_board(board["brand"], board["model"])
    if not expert:
        return f"I know the {board['brand']} {board['model']}, but its expert classification still needs review."
    lanes = {expert["primaryLane"], *expert.get("secondaryLanes", []), *expert.get("boardLanes", [])}
    if requested_family == "fish" and not any("fish" in lane or "twin_fin" in lane for lane in lanes):
        return (
            f"No. The {board['brand']} {board['model']} is more {expert['primaryLane'].replace('_', ' ')} "
            "than a true fish. It may share easy speed or versatility, but it does not sit in the proper fish/twin lane."
        )
    return f"Yes. The {board['brand']} {board['model']} sits in the {expert['primaryLane'].replace('_', ' ')} lane."


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
            board_model_id=board.get("boardModelId") if board else None,
        ))
    return suggestions


def find_requested_board(message: str) -> dict | None:
    text = board_key("", message)[1]
    if not text or any(phrase in text for phrase in ["i ride", "im riding", "my current board", "currently ride"]):
        return None
    shorthand = {
        "hypto": ("Haydenshapes", "Hypto Krypto"),
        "rnf": ("Lost", "RNF 96"),
        "seaside": ("Firewire", "Seaside"),
    }
    for alias, (brand, model) in shorthand.items():
        if alias in text.split():
            board = find_board(load_graph(), brand, model)
            if board:
                return board
    matches = []
    for board in load_graph().get("boards", []):
        brand_key, model_key = board_key(board.get("brand"), board.get("model"))
        model_present = f" {model_key} " in f" {text} "
        brand_aliases = {
            "js industries": ["js"], "channel islands": ["ci"],
            "chemistry surfboards": ["chemistry"], "dms surfboards": ["dms"],
        }
        brand_present = f" {brand_key} " in f" {text} " or any(
            f" {alias} " in f" {text} " for alias in brand_aliases.get(brand_key, [])
        )
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
            board_model_id=candidate.get("boardModelId"),
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
    performance_brief = (
        (profile.preferred_board_type or "").lower() == "daily driver"
        and (profile.ability or "").lower() in {"advanced", "expert"}
        and (profile.wave_power or "").lower() in {"average to powerful", "powerful"}
    )
    if performance_brief:
        base = (
            f"At {profile.weight_kg}kg and {profile.ability.lower()}, I’d start around {guidance.label} for a "
            "good-wave daily driver. I’d prioritise proper performance daily drivers over broad hybrids."
        )
    else:
        base = (
            f"Based on what you’ve told me, {guidance.label} is a sensible starting range—not an exact truth. "
            f"I’d look in the {guidance.recommended_category.lower()} lane."
        )
    available = [board for board in boards if board.available_count > 0]
    if not available:
        return base + f" I can’t verify a matching board in {normalise_region(profile.region)} right now, so I won’t invent stock."
    names = ", ".join(f"{board.brand} {board.model}" for board in available[:5])
    explanation = ""
    if performance_brief:
        hybrids = [board for board in available if daily_driver_lane(board.brand, board.model) == "hybrid_daily_driver"]
        if hybrids:
            explanation = " Hybrid choices are more forgiving, but they aren’t my first pick for this brief."
    return base + f" From verified {normalise_region(profile.region)} stock, I’d check {names} first." + explanation


def find_boards_in_message(message: str) -> list[dict]:
    text = f" {board_key('', message)[1]} "
    matches = []
    for board in load_graph().get("boards", []):
        brand, model = board_key(board.get("brand"), board.get("model"))
        if model in {"what", "why", "how", "when", "where"}:
            continue
        if f" {model} " in text and (f" {brand} " in text or len(model.split()) >= 1):
            matches.append((len(model), board))
    matches.sort(key=lambda row: -row[0])
    output, seen = [], set()
    for _, board in matches:
        key = board_key(board["brand"], board["model"])
        if key not in seen:
            output.append(board); seen.add(key)
    aliases = {
        "hypto": ("Haydenshapes", "Hypto Krypto"),
        "rnf": ("Lost", "RNF 96"),
        "seaside": ("Firewire", "Seaside"),
    }
    normalised_message = board_key("", message)[1]
    for alias, (brand, model) in aliases.items():
        if alias not in normalised_message.split():
            continue
        board = find_board(load_graph(), brand, model)
        if board and board_key(brand, model) not in seen:
            output.append(board)
            seen.add(board_key(brand, model))
    return output


def comparison_reply(message: str) -> str:
    boards = find_boards_in_message(message)
    if len(boards) < 2:
        return "Name the two boards you want compared—for example, ‘Compare Pyzel Phantom and JS Monsta’."
    left, right = boards[:2]
    comparison = compare_boards(load_graph(), left["brand"], left["model"], right["brand"], right["model"])
    left_data, right_data = comparison["left"], comparison["right"]
    left_expert = find_matrix_board(left["brand"], left["model"])
    right_expert = find_matrix_board(right["brand"], right["model"])
    lane_note = ""
    left_lane = daily_driver_lane(left["brand"], left["model"])
    right_lane = daily_driver_lane(right["brand"], right["model"])
    if {left_lane, right_lane} == {"performance_daily_driver", "hybrid_daily_driver"}:
        performance = left if left_lane == "performance_daily_driver" else right
        hybrid = right if left_lane == "performance_daily_driver" else left
        lane_note = (
            f" For good waves, {performance['brand']} {performance['model']} is the stronger performance daily-driver pick; "
            f"{hybrid['brand']} {hybrid['model']} is the easier-paddling, more forgiving hybrid."
        )
    expert_note = ""
    if left_expert and right_expert and "good wave" in message.lower():
        better = left if left_expert["goodWaveScore"] >= right_expert["goodWaveScore"] else right
        easier = left if left_expert["forgivenessScore"] >= right_expert["forgivenessScore"] else right
        expert_note = (
            f" For good-wave performance, the matrix favours {better['brand']} {better['model']}; "
            f"{easier['brand']} {easier['model']} is the more forgiving option."
        )
    return (
        f"{left['brand']} {left['model']} is a {left_data['category']['primaryCategory'].replace('_', ' ')} "
        f"with {left_data['paddlingBias']} paddle help, {left_data['performanceBias']} performance bias, and "
        f"{left_data['forgiveness']} forgiveness. {right['brand']} {right['model']} is a "
        f"{right_data['category']['primaryCategory'].replace('_', ' ')} with {right_data['paddlingBias']} paddle help, "
        f"{right_data['performanceBias']} performance bias, and {right_data['forgiveness']} forgiveness. "
        f"{lane_note}{expert_note} Tell me your litres and region if you want me to check availability."
    )


def general_board_reply(message: str) -> str:
    text = message.lower()
    definitions = [
        ("fish", "A fish is a wide, fast board built for easy speed and flow, usually in small-to-average waves. Twin and hybrid-fish designs feel loose and lively; your weight and preferred litres help narrow the right one."),
        ("daily driver", "A daily driver is an everyday shortboard that balances paddle power, forgiveness, and performance across the waves you surf most often."),
        ("grov", "A groveller is a compact, higher-volume board designed to create speed and catch waves when conditions are small or weak."),
        ("step", "A step-up adds length, hold, and control for larger or more powerful waves. It is usually chosen around the waves and surfer, not just litres."),
        ("mid", "A mid-length prioritises paddle power, glide, and earlier entry while staying more manoeuvrable than a longboard."),
        ("longboard", "A longboard prioritises glide, stability, and wave count, with performance varying from easy cruisers to refined noseriders."),
        ("shortboard", "Shortboard covers several lanes: performance boards, daily drivers, grovellers, fish, hybrids, and step-ups. Conditions and desired feel decide which lane fits."),
        ("volume", "Volume is the board’s litres of displacement. It affects flotation and paddling, but outline, length, width, rails, rocker, and foam distribution decide how that volume actually feels."),
        ("litre", "Litres measure board volume. Use them as a sensible range rather than a single truth, because two boards at the same litres can paddle and turn very differently."),
        ("rocker", "Rocker is the board’s nose-to-tail curve. More rocker adds control in steep or powerful waves; flatter rocker creates speed and easier entry in weaker waves."),
        ("rail", "Rails are the board’s edges. Fuller rails add forgiveness and flotation; lower, refined rails engage more precisely but usually demand cleaner technique."),
        ("concave", "Bottom concave controls water flow under the board. Different single, double, and vee combinations tune lift, speed, rail-to-rail response, and release."),
        ("twin", "A twin-fin uses two main fins for speed, flow, and a loose feel. Modern twins range from small-wave fish to performance twins for better waves."),
        ("thruster", "A thruster has three fins and offers a familiar balance of drive, hold, and controlled turning across a wide range of conditions."),
        ("quad", "A quad uses four fins for speed and hold without a centre fin. It can suit fast lines, barrels, fish, and some step-ups, depending on the board."),
        ("epoxy", "Epoxy usually refers to an EPS core with epoxy resin: typically lighter and more buoyant than traditional PU, though flex and durability depend on the exact construction."),
        ("construction", "Construction changes weight, flex, durability, and feel. Compare the manufacturer’s actual build rather than treating every epoxy or PU board as identical."),
    ]
    return next((answer for token, answer in definitions if token in text), "Ask me about a board type, model, size, construction, or the waves it suits.")


def site_help_reply(region: str | None) -> str:
    code = normalise_region(region) or "AU"
    name = {"AU": "Australia", "EU": "Europe", "ID": "Indonesia"}[code]
    return (
        f"Start in the {name} search, then choose brand, model, construction, and size to see exact manufacturer "
        "and retailer matches. Or ask me naturally—‘show me fish boards around 30L in Europe’, ‘compare Phantom "
        "and Monsta’, or tell me your weight and ability for a guided fit. I’ll only show stock verified for your region."
    )
