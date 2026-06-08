
def build_basic_guidance(message: str, region: str | None = None) -> str:
    text = message.lower()

    if not message.strip():
        return (
            "Hey, I am Bodhi, the Core Lord. Tell me your height, weight, ability level, "
            "where you surf, your usual wave size and what you want your next board to do better."
        )

    has_weight = any(token in text for token in ["kg", "kilo", "pound", "lbs"])
    has_height = any(token in text for token in ["cm", "foot", "feet", "ft", "'"])
    has_ability = any(token in text for token in ["beginner", "intermediate", "advanced", "expert"])
    has_waves = any(token in text for token in ["ft", "foot", "beach", "reef", "point", "wave", "waves"])

    missing = []
    if not has_height:
        missing.append("your height")
    if not has_weight:
        missing.append("your weight")
    if not has_ability:
        missing.append("your ability level")
    if not has_waves:
        missing.append("the waves you normally surf")

    if missing:
        return (
            "Good start. Before I point you at a board, I need "
            + ", ".join(missing[:4])
            + ". Also tell me whether you want more paddle power, more speed, tighter turns or more hold."
        )

    region_text = f" in {region}" if region else ""

    return (
        f"Based on that{region_text}, I would start you around a user friendly hybrid, groveller or small wave shortboard rather than a narrow high performance board. "
        "You are probably looking for something with a bit of foam under the chest, a forgiving outline and enough width to carry speed through softer sections.\n\n"
        "Starting point:\n"
        "1. Board category: hybrid shortboard, groveller or performance fish\n"
        "2. Length range: roughly around your normal shortboard length, or slightly shorter if the board has more width and foam\n"
        "3. Volume: aim for paddle support first, then refine down once we know your current board volume\n"
        "4. Search next: choose Australia in Quivrr, then look at models built for everyday 2 to 4 foot surf\n\n"
        "Tell me your current board size and volume if you know it, and I can tighten that recommendation."
    )
