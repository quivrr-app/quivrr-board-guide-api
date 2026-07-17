from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


PUBLIC_FAMILY_LABELS = {
    "fish": "Fish",
    "groveller": "Groveller",
    "daily_driver": "Daily Driver",
    "performance_shortboard": "Performance Shortboard",
    "step_up": "Step Up",
    "mid_length": "Mid Length",
    "longboard": "Longboard",
}

FAMILY_PATTERNS: tuple[tuple[str, str | None, tuple[str, ...]], ...] = (
    ("fish", "Performance Fish", (
        r"\b(?:high\s+)?perform\w*\s+fish\b", r"\bmodern\s+fish\b",
    )),
    ("fish", "Traditional Fish", (r"\btraditional\s+fish\b", r"\bretro\s+fish\b")),
    ("performance_shortboard", "Competition HPSB", (
        r"\bh\s*p\s*s\s*b\b", r"\bcompetition\s+shortboard\b", r"\bpro\s+board\b",
        r"\bproper\s+short(?:board|y)\b", r"\bhigh\s+perf\w*\s+(?:short)?boards?\b",
        r"\btrue\s+(?:high\s+)?performance\s+(?:short)?boards?\b",
        r"\bperformance\s+thruster\b", r"\bhigh\s+performance\s+stick\b",
        r"\bperforamce\s+shortboard\b", r"\bhigh\s+perfance\s+board\b",
    )),
    ("daily_driver", "Performance Daily Driver", (
        r"\bperformance\s+daily\s+driver\b", r"\beveryday\s+performance\s+board\b",
        r"\beveryday\s+shortboard\b", r"\bone[ -]board\s+quiver\b",
    )),
    ("daily_driver", None, (r"\bdaily\s+driv+er\b", r"\bdaily\s+drivver\b", r"\beveryday\s+board\b")),
    ("performance_shortboard", None, (
        r"\bperformance\s+short(?:board|y)s?\b", r"\bperformn?ce\s+shortboard\b",
        r"\bsomething\s+(?:spicy|less\s+cruisy|for\s+good\s+waves)\b",
    )),
    ("groveller", None, (
        r"\bgrovel+er\b", r"\bgroveller\b", r"\btiny[ -]wave\s+board\b",
        r"\bsummer\s+slop\s+board\b", r"\bsmall[ -]wave\s+twin\b",
    )),
    ("step_up", None, (r"\bstep[ -]?up\b", r"\breef\s+step[ -]?up\b", r"\btravel\s+step[ -]?up\b")),
    ("mid_length", None, (r"\bmid[ -]?(?:length|lenght)\b",)),
    ("longboard", None, (r"\blong\s*boards?\b", r"\blong\s+bord\b")),
    ("fish", None, (r"\bfish\b",)),
)

EXCLUSION_PATTERNS = {
    "fish": (r"\b(?:no|not|isn['’]?t|aren['’]?t)\s+(?:a\s+)?fish\b",),
    "groveller": (r"\b(?:no|not)\s+(?:a\s+)?grovel+er\b", r"\bnot\s+a\s+groveller\b"),
    "daily_driver": (
        r"\b(?:no|not)\s+(?:a\s+)?daily\s+driv+er\b", r"\bnot\s+an?\s+everyday\s+board\b",
        r"\bthese\s+are\s+daily\s+drivers\b", r"\bnothing\s+too\s+forgiving\b",
    ),
    "performance_shortboard": (r"\b(?:no|not)\s+(?:a\s+)?(?:performance\s+shortboard|hpsb)\b",),
    "step_up": (r"\b(?:no|not)\s+(?:a\s+)?step[ -]?up\b",),
    "mid_length": (r"\b(?:no|not)\s+(?:a\s+)?mid[ -]?(?:length|lenght)\b",),
    "longboard": (r"\b(?:no|not)\s+(?:a\s+)?long\s*boards?\b",),
}

FIN_PATTERNS = {
    "twin": r"\btwin(?:\s+fin)?s?\b",
    "quad": r"\bquad\b",
    "thruster": r"\bthruster\b",
    "five_fin": r"\b(?:five|5)[ -]?fin\b",
    "two_plus_one": r"\b(?:two|2)\s*\+\s*1\b",
    "single": r"\bsingle(?:\s+fin)?\b",
}


@dataclass(frozen=True)
class FamilyIntent:
    requested_public_family: str | None = None
    requested_detailed_category: str | None = None
    requested_fin_setup: str | None = None
    excluded_public_families: tuple[str, ...] = field(default_factory=tuple)
    excluded_detailed_categories: tuple[str, ...] = field(default_factory=tuple)
    excluded_fin_setups: tuple[str, ...] = field(default_factory=tuple)
    allow_adjacent_alternatives: bool = False
    correction: bool = False
    correction_reason: str | None = None
    confidence: float = 0.0
    explicit: bool = False


def _state_value(state: Any, snake: str, camel: str, default: Any = None) -> Any:
    if state is None:
        return default
    if isinstance(state, dict):
        return state.get(snake, state.get(camel, default))
    return getattr(state, snake, default)


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def resolve_family_intent(message: str, previous_state: Any = None, *, reset: bool = False) -> FamilyIntent:
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    if reset:
        previous_state = None

    previous_family = _state_value(previous_state, "requested_public_family", "requestedPublicFamily")
    previous_detail = _state_value(previous_state, "requested_detailed_category", "requestedDetailedCategory")
    previous_fin = _state_value(previous_state, "requested_fin_setup", "requestedFinSetup")
    excluded = set(_state_value(previous_state, "excluded_public_families", "excludedPublicFamilies", []) or [])
    excluded_details = set(_state_value(previous_state, "excluded_detailed_categories", "excludedDetailedCategories", []) or [])
    excluded_fins = set(_state_value(previous_state, "excluded_fin_setups", "excludedFinSetups", []) or [])

    new_exclusions: set[str] = set()
    for family, patterns in EXCLUSION_PATTERNS.items():
        if _matches(patterns, text):
            excluded.add(family)
            new_exclusions.add(family)

    requested_family = None
    requested_detail = None
    explicit = False
    for family, detail, patterns in FAMILY_PATTERNS:
        if _matches(patterns, text):
            # Negated family mentions describe exclusions, not the requested family.
            if family in new_exclusions:
                continue
            requested_family = family
            requested_detail = detail
            explicit = True
            break

    requested_fin = None
    for fin, pattern in FIN_PATTERNS.items():
        if not re.search(pattern, text):
            continue
        if re.search(rf"\b(?:no|not|without)\b[^.?!]{{0,18}}{pattern}", text):
            excluded_fins.add(fin)
        else:
            requested_fin = fin
        break

    correction = bool(re.search(
        r"\b(?:no[, ]|i\s+said|you(?:'re| are)\s+showing|these\s+are|not\s+an?|actually|instead|proper|true)\b",
        text,
    )) and bool(requested_family or excluded)

    if not explicit:
        requested_family = previous_family
        requested_detail = previous_detail
        if requested_family in new_exclusions:
            requested_family = None
            requested_detail = None
    if requested_fin is None:
        requested_fin = previous_fin

    if requested_family and requested_family not in new_exclusions:
        excluded.discard(requested_family)
    if correction and previous_family and requested_family and previous_family != requested_family:
        excluded.add(previous_family)

    allow_adjacent = bool(re.search(r"\b(?:alternative|nearby|similar|close option)\b", text))
    reason = None
    if correction:
        rejected = sorted(excluded)
        reason = f"User corrected the family to {requested_family}"
        if rejected:
            reason += f" and excluded {', '.join(rejected)}"

    return FamilyIntent(
        requested_public_family=requested_family,
        requested_detailed_category=requested_detail,
        requested_fin_setup=requested_fin,
        excluded_public_families=tuple(sorted(excluded)),
        excluded_detailed_categories=tuple(sorted(excluded_details)),
        excluded_fin_setups=tuple(sorted(excluded_fins)),
        allow_adjacent_alternatives=allow_adjacent,
        correction=correction,
        correction_reason=reason,
        confidence=0.98 if explicit else (0.8 if requested_family else 0.0),
        explicit=explicit,
    )


def correction_acknowledgement(intent: FamilyIntent) -> str | None:
    if not intent.correction or not intent.requested_public_family:
        return None
    family = PUBLIC_FAMILY_LABELS[intent.requested_public_family]
    rejected = [PUBLIC_FAMILY_LABELS.get(item, item.replace("_", " ").title()) for item in intent.excluded_public_families]
    if rejected:
        return f"You’re right — those were {', '.join(rejected)}. You’re after true {family} boards, so I’ll keep this shortlist inside that family."
    return f"You’re right — I’ll keep this shortlist inside the {family} family."
