"""Deterministic canonical-board resolution for every Bodhi entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re

from app.board_master import load_board_master, normalise


BRAND_ALIASES = {
    "js": "JS Industries",
    "js industries": "JS Industries",
    "ci": "Channel Islands",
    "channel islands": "Channel Islands",
    "lost": "Lost",
    "lost surfboards": "Lost",
    "sharp eye": "Sharp Eye",
    "sharpeye": "Sharp Eye",
    "firewire": "Firewire",
    "pyzel": "Pyzel",
    "dhd": "DHD",
}

# Only include reviewed aliases that identify a single canonical model.
MODEL_ALIASES = {
    ("Haydenshapes", "Hypto Krypto"): ("hypto",),
    ("Lost", "RNF 96"): ("rnf", "rnf96"),
    ("DHD", "MF DNA"): ("dna",),
}

_FILLER = {
    "tell", "me", "about", "what", "is", "the", "a", "an", "like", "thoughts", "on",
    "would", "it", "suit", "for", "who", "does", "how", "surf", "board", "surfboard",
    "any", "good", "work", "with", "my", "please",
}
_GENERIC_MODEL_TERMS = {"fish", "twin", "shortboard", "longboard", "step up", "mid length"}


@dataclass(frozen=True)
class BoardResolution:
    status: str
    brand: str | None = None
    model: str | None = None
    canonical_key: str | None = None
    canonical_model_id: int | None = None
    match_type: str | None = None
    confidence: float = 0.0
    matched_input: str | None = None
    alternatives: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _text(value: object) -> str:
    return normalise(value)


def _brand_from_text(text: str) -> str | None:
    for alias, brand in sorted(BRAND_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return brand
    known = {row["manufacturer"] for row in load_board_master()["models"]}
    for brand in sorted(known, key=lambda item: len(_text(item)), reverse=True):
        if re.search(rf"\b{re.escape(_text(brand))}\b", text):
            return brand
    return None


def _result(row: dict, match_type: str, confidence: float, matched_input: str) -> BoardResolution:
    return BoardResolution(
        status="resolved",
        brand=row["manufacturer"],
        model=row["model"],
        canonical_key=row["canonical_key"],
        canonical_model_id=int(row["canonical_model_id"]),
        match_type=match_type,
        confidence=confidence,
        matched_input=matched_input,
    )


def _ambiguous(rows: list[dict], matched_input: str) -> BoardResolution:
    return BoardResolution(
        status="ambiguous",
        match_type="ambiguous_match",
        matched_input=matched_input,
        alternatives=tuple((row["manufacturer"], row["model"]) for row in rows[:3]),
    )


def resolve_board(message: str, *, context_board: tuple[str, str] | None = None) -> BoardResolution:
    """Resolve a board without allowing fuzzy matching to select a close sibling silently."""
    text = _text(message)
    if not text:
        return BoardResolution(status="not_found")
    rows = list(load_board_master()["models"])
    requested_brand = _brand_from_text(text)
    candidates = [row for row in rows if not requested_brand or row["manufacturer"] == requested_brand]

    # Generic or question-word model names cannot be selected from a prose
    # question without a brand. Keep the candidate visible for clarification.
    clarification_candidates = [
        row for row in candidates
        if not requested_brand
        and (
            _text(row["model"]) in _GENERIC_MODEL_TERMS
            and " ".join(word for word in text.split() if word not in _FILLER) == _text(row["model"])
            or _text(row["model"]) in _FILLER and text.split().count(_text(row["model"])) >= 2
        )
        and re.search(rf"\b{re.escape(_text(row['model']))}\b", text)
    ]
    if clarification_candidates:
        return _ambiguous(clarification_candidates, text)

    words_without_filler = [word for word in text.split() if word not in _FILLER and word not in _text(requested_brand).split()]
    requested_phrase = " ".join(words_without_filler)
    prefix = [row for row in candidates if requested_phrase and _text(row["model"]).startswith(requested_phrase + " ")]
    has_exact_phrase = any(_text(row["model"]) == requested_phrase for row in candidates)
    if prefix and not has_exact_phrase:
        return _result(prefix[0], "model_prefix", .9, requested_phrase) if len(prefix) == 1 else _ambiguous(prefix, requested_phrase)

    exact = [
        row for row in candidates
        if _text(row["model"]) not in _GENERIC_MODEL_TERMS or requested_brand
        # Names that are ordinary question words need a manufacturer or an
        # otherwise standalone mention. Never let "What is X like" resolve to
        # a board called "What".
        if requested_brand or _text(row["model"]) not in _FILLER
        if re.search(rf"\b{re.escape(_text(row['model']))}\b", text)
    ]
    if exact:
        # A full model phrase outranks an overlapping family member (Monsta Box vs Monsta).
        exact.sort(key=lambda row: len(_text(row["model"])), reverse=True)
        best_length = len(_text(exact[0]["model"]))
        best = [row for row in exact if len(_text(row["model"])) == best_length]
        if len(best) == 1:
            return _result(best[0], "exact_brand_and_model" if requested_brand else "exact_model", 1.0 if requested_brand else .98, text)
        return _ambiguous(best, text)

    for row in candidates:
        aliases = MODEL_ALIASES.get((row["manufacturer"], row["model"]), ())
        aliases = (*aliases, *row.get("aliases", []))
        for alias in aliases:
            alias_key = _text(alias)
            if alias_key and re.search(rf"\b{re.escape(alias_key)}\b", text):
                return _result(row, "alias_match", .97, alias_key)

    words = words_without_filler
    phrase = " ".join(words)
    if phrase:
        scored = []
        for row in candidates:
            model = _text(row["model"])
            if not requested_brand and model in _GENERIC_MODEL_TERMS:
                continue
            # A short model needs a very clear typo correction.
            ratio = SequenceMatcher(None, phrase, model).ratio()
            for width in range(max(1, len(model.split()) - 1), min(len(words), len(model.split()) + 1) + 1):
                for index in range(len(words) - width + 1):
                    ratio = max(ratio, SequenceMatcher(None, " ".join(words[index:index + width]), model).ratio())
            threshold = .9 if len(model) <= 5 else .84
            if ratio >= threshold:
                scored.append((ratio, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            best_score, best = scored[0]
            if len(scored) == 1 or best_score - scored[1][0] >= .08:
                return _result(best, "fuzzy_model", round(best_score, 2), phrase)
            return _ambiguous([row for _, row in scored], phrase)

    if context_board:
        brand, model = context_board
        for row in rows:
            if row["manufacturer"] == brand and row["model"] == model:
                return _result(row, "conversation_context", .9, text)
    return BoardResolution(status="not_found", matched_input=text)
