from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.daily_driver_taxonomy import daily_driver_lane
from app.board_master import category_key, find_master_board, find_master_board_by_id
from app.manufacturer_intelligence import find_staged_model


KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
GENERATED_DIR = KNOWLEDGE_DIR / "generated"


@dataclass(frozen=True)
class BoardSize:
    length: str | None
    width: str | None
    thickness: str | None
    volume_litres: float | None


@dataclass(frozen=True)
class BoardIntelligenceRecord:
    brand: str
    model: str
    board_model_id: int | None
    category: str | None
    primary_category: str | None
    lane: str | None
    description: str | None
    short_description: str | None
    official_product_url: str | None
    source_type: str | None
    source_confidence: float
    curated: bool
    graph_eligible: bool
    classified: bool
    unclassified: bool
    release_year: int | None = None
    model_generation: str | None = None
    is_current_model: bool | None = None
    is_discontinued: bool | None = None
    ability_tags: tuple[str, ...] = ()
    wave_tags: tuple[str, ...] = ()
    wave_types: tuple[str, ...] = ()
    feel_tags: tuple[str, ...] = ()
    wave_height_min_ft: float | None = None
    wave_height_max_ft: float | None = None
    design_scores: dict[str, float] = field(default_factory=dict)
    quiver_roles: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()
    trade_offs: tuple[str, ...] = ()
    recommendation_lanes: tuple[str, ...] = ()
    excluded_recommendation_lanes: tuple[str, ...] = ()
    sizes: tuple[BoardSize, ...] = ()
    volume_min_litres: float | None = None
    volume_max_litres: float | None = None
    relationships: dict[str, tuple[dict, ...]] = field(default_factory=dict)
    metadata_missing_fields: tuple[str, ...] = ()


def _normalise_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def board_key(brand: str | None, model: str | None) -> str:
    return f"{_normalise_text(brand)}::{_normalise_text(model)}"


def _load_json(path: Path, *, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _coerce_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_list(*values: object) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        if isinstance(value, list):
            items = value
        elif value is None:
            items = []
        else:
            items = [value]
        for item in items:
            text = str(item or "").strip()
            if text and text not in output:
                output.append(text)
    return tuple(output)


def _confidence_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    mapping = {
        "high": 0.95,
        "medium": 0.75,
        "low": 0.55,
        "none": 0.0,
    }
    return mapping.get(str(value or "").strip().lower(), 0.0)


def _sizes_from_profile(profile: dict) -> tuple[BoardSize, ...]:
    sizes: list[BoardSize] = []
    for row in profile.get("sizes", []):
        if not isinstance(row, dict):
            continue
        sizes.append(
            BoardSize(
                length=row.get("length"),
                width=row.get("width"),
                thickness=row.get("thickness"),
                volume_litres=_coerce_float(row.get("volume_litres")),
            )
        )
    return tuple(sizes)


def _volume_range_from_generated(row: dict) -> tuple[float | None, float | None]:
    volume_range = row.get("volume_range")
    if not isinstance(volume_range, dict):
        return None, None
    return _coerce_float(volume_range.get("min")), _coerce_float(volume_range.get("max"))


def _sizes_volume_range(sizes: tuple[BoardSize, ...]) -> tuple[float | None, float | None]:
    volumes = [size.volume_litres for size in sizes if size.volume_litres is not None]
    if not volumes:
        return None, None
    return min(volumes), max(volumes)


def _metadata_release_year(model: str, description_text: str, metadata: dict, curated: dict) -> int | None:
    explicit = _coerce_int(curated.get("release_year") or metadata.get("releaseYear"))
    if explicit and 1990 <= explicit <= 2100:
        return explicit

    search_text = " ".join([model or "", description_text or ""])
    for pattern in [r"\bnew for (20[0-9]{2})\b", r"\breleased in (20[0-9]{2})\b", r"\bfor (20[0-9]{2})\b"]:
        match = re.search(pattern, search_text, flags=re.IGNORECASE)
        if match:
            year = _coerce_int(match.group(1))
            if year and 1990 <= year <= 2100:
                return year
    return None


def _metadata_model_generation(model: str, metadata: dict, curated: dict) -> str | None:
    explicit = curated.get("model_generation") or metadata.get("modelGeneration")
    if explicit:
        return str(explicit).strip() or None
    match = re.search(r"\b([2-9](?:\.[0-9])?)\b", model or "")
    return match.group(1) if match else None


def _metadata_current_flag(model: str, description_text: str, metadata: dict, curated: dict) -> bool | None:
    explicit = curated.get("is_current_model")
    if isinstance(explicit, bool):
        return explicit
    explicit = metadata.get("isCurrentModel")
    if isinstance(explicit, bool):
        return explicit

    search_text = " ".join([model or "", description_text or ""]).lower()
    if any(
        token in search_text
        for token in ["all-new", "all new", "new for 20", "updated version", "new improved", "next generation", "latest innovation"]
    ):
        return True
    return None


def _metadata_discontinued_flag(description_text: str, metadata: dict, curated: dict) -> bool | None:
    explicit = curated.get("is_discontinued")
    if isinstance(explicit, bool):
        return explicit
    explicit = metadata.get("isDiscontinued")
    if isinstance(explicit, bool):
        return explicit
    return True if "discontinued" in (description_text or "").lower() else None


def _build_records() -> dict[str, BoardIntelligenceRecord]:
    canonical_profiles = _load_json(GENERATED_DIR / "canonical_board_profiles.json", default=[])
    generated_intelligence = _load_json(GENERATED_DIR / "board_intelligence_generated.json", default={}).get("boards", [])
    canonical_intelligence = _load_json(GENERATED_DIR / "canonical_board_intelligence.json", default={}).get("profiles", [])
    recommendation_graph = _load_json(GENERATED_DIR / "board_recommendation_graph.json", default={}).get("boards", [])
    relationship_graph = _load_json(GENERATED_DIR / "board_relationship_graph.json", default={}).get("boards", [])
    curated_intelligence = _load_json(KNOWLEDGE_DIR / "board_intelligence.json", default={}).get("boards", [])
    curated_overrides = _load_json(KNOWLEDGE_DIR / "board_intelligence_overrides.json", default={}).get("boards", [])
    audit = _load_json(GENERATED_DIR / "board_intelligence_audit.json", default={})

    by_id_generated = {
        row.get("board_model_id"): row
        for row in generated_intelligence
        if isinstance(row, dict) and row.get("board_model_id") is not None
    }
    by_key_generated = {
        board_key(row.get("brand"), row.get("model")): row
        for row in generated_intelligence
        if isinstance(row, dict) and row.get("brand") and row.get("model")
    }

    by_id_canonical = {}
    by_key_canonical = {}
    for row in canonical_intelligence:
        if not isinstance(row, dict):
            continue
        identity = row.get("identity") or {}
        key = board_key(identity.get("brand"), identity.get("model"))
        if identity.get("boardModelId") is not None:
            by_id_canonical[identity.get("boardModelId")] = row
        if key != "::":
            by_key_canonical[key] = row

    by_key_graph = {
        board_key(row.get("brand"), row.get("model")): row
        for row in recommendation_graph
        if isinstance(row, dict) and row.get("brand") and row.get("model")
    }
    by_key_relationships = {
        board_key(row.get("brand"), row.get("model")): row
        for row in relationship_graph
        if isinstance(row, dict) and row.get("brand") and row.get("model")
    }

    by_key_curated: dict[str, dict] = {}
    for source_rows in (curated_intelligence, curated_overrides):
        for row in source_rows:
            if isinstance(row, dict) and row.get("brand") and row.get("model"):
                by_key_curated[board_key(row.get("brand"), row.get("model"))] = row

    unclassified_keys = {
        board_key(row.get("brand"), row.get("model"))
        for row in audit.get("unclassifiedBoards", [])
        if isinstance(row, dict)
    }

    records: dict[str, BoardIntelligenceRecord] = {}
    for profile in canonical_profiles:
        if not isinstance(profile, dict) or not profile.get("brand") or not profile.get("model"):
            continue

        key = board_key(profile.get("brand"), profile.get("model"))
        board_model_id = profile.get("board_model_id")
        generated = by_id_generated.get(board_model_id) or by_key_generated.get(key) or {}
        canonical = by_id_canonical.get(board_model_id) or by_key_canonical.get(key) or {}
        graph = by_key_graph.get(key) or {}
        relationships_row = by_key_relationships.get(key) or {}
        curated = by_key_curated.get(key) or {}
        master = find_master_board_by_id(board_model_id) or find_master_board(profile.get("brand"), profile.get("model"))

        identity = canonical.get("identity") or {}
        description = canonical.get("description") or {}
        category = canonical.get("category") or {}
        wave = canonical.get("wave") or {}
        surfer = canonical.get("surfer") or {}
        design = canonical.get("design") or {}
        metadata = canonical.get("metadata") or {}
        description_text = (
            curated.get("model_description")
            or generated.get("model_description")
            or description.get("manufacturerDescription")
            or profile.get("description")
            or ""
        )

        sizes = _sizes_from_profile(profile)
        size_volume_min, size_volume_max = _sizes_volume_range(sizes)
        generated_volume_min, generated_volume_max = _volume_range_from_generated(generated)

        category_value = (master.get("board_type") if master else None) or (
            curated.get("category")
            or generated.get("category")
            or category.get("manufacturerCategory")
            or category.get("primaryCategory")
            or profile.get("category")
        )
        primary_category = category_key(master["detailed_category"]) if master else (category.get("primaryCategory") or graph.get("primaryCategory"))
        source_confidence = max(
            _confidence_value(curated.get("confidence")),
            _confidence_value(description.get("descriptionConfidence")),
            _confidence_value(category.get("categoryConfidence")),
            _confidence_value(metadata.get("reviewedByQuivrr") and "high"),
            0.35 if generated else 0.0,
        )
        relationships = {
            name: tuple(value)
            for name, value in (relationships_row.get("relationships") or {}).items()
            if isinstance(value, list) and value
        }
        record = BoardIntelligenceRecord(
            brand=profile["brand"],
            model=profile["model"],
            board_model_id=board_model_id,
            category=category_value,
            primary_category=primary_category,
            lane=((master.get("recommendation_lanes") or [None])[0] if master else daily_driver_lane(profile.get("brand"), profile.get("model"))),
            description=(master.get("manufacturer_intent") if master else description_text) or None,
            short_description=(
                curated.get("short_description")
                or generated.get("short_description")
                or description.get("shortDescription")
            ),
            official_product_url=(
                (master.get("official_url") if master else None)
                or curated.get("official_product_url")
                or generated.get("official_product_url")
                or identity.get("sourceUrl")
                or profile.get("official_product_url")
            ),
            source_type=(
                curated.get("source_type")
                or generated.get("source_type")
                or identity.get("sourceType")
                or profile.get("description_source_type")
            ),
            source_confidence=1.0 if master and master.get("confidence") == "high" else round(source_confidence, 2),
            curated=bool(curated),
            graph_eligible=bool(graph),
            classified=bool(primary_category or category_value not in {None, "", "Surfboard"}),
            unclassified=key in unclassified_keys,
            release_year=_metadata_release_year(profile.get("model") or "", description_text, metadata, curated),
            model_generation=_metadata_model_generation(profile.get("model") or "", metadata, curated),
            is_current_model=_metadata_current_flag(profile.get("model") or "", description_text, metadata, curated),
            is_discontinued=_metadata_discontinued_flag(description_text, metadata, curated),
            ability_tags=(
                _text_list(master.get("ability_range"))
                if master else _text_list(
                    curated.get("ability_tags"),
                    generated.get("ability_tags"),
                    generated.get("skill_level"),
                    surfer.get("surferProfiles"),
                    surfer.get("abilityMin"),
                    surfer.get("abilityMax"),
                )
            ),
            wave_tags=_text_list(curated.get("wave_tags"), generated.get("wave_tags")),
            wave_types=(
                _text_list(master.get("wave_type"))
                if master else _text_list(generated.get("wave_type"), wave.get("waveTypes"))
            ),
            feel_tags=_text_list(curated.get("feel_tags"), generated.get("feel_tags")),
            wave_height_min_ft=_coerce_float(wave.get("waveHeightMinFt")),
            wave_height_max_ft=_coerce_float(wave.get("waveHeightMaxFt")),
            design_scores={
                key_name: float(value)
                for key_name, value in (graph.get("designScores") or {}).items()
                if isinstance(value, (int, float))
            },
            quiver_roles=_text_list(graph.get("quiverRole"), curated.get("goal_tags")),
            strengths=(
                _text_list(master.get("strengths"))
                if master else _text_list(graph.get("strengths"))
            ),
            trade_offs=(
                _text_list(master.get("weaknesses"))
                if master else _text_list(curated.get("trade_offs"), generated.get("trade_offs"), graph.get("tradeOffs"))
            ),
            recommendation_lanes=_text_list(master.get("recommendation_lanes") if master else None),
            excluded_recommendation_lanes=_text_list(master.get("excluded_recommendation_lanes") if master else None),
            sizes=sizes,
            volume_min_litres=generated_volume_min if generated_volume_min is not None else size_volume_min,
            volume_max_litres=generated_volume_max if generated_volume_max is not None else size_volume_max,
            relationships=relationships,
            metadata_missing_fields=tuple(metadata.get("missingFields") or ()),
        )
        records[key] = record

    return records


@lru_cache(maxsize=1)
def load_board_records() -> tuple[BoardIntelligenceRecord, ...]:
    return tuple(sorted(_build_records().values(), key=lambda row: (row.brand.lower(), row.model.lower())))


@lru_cache(maxsize=1)
def board_record_lookup() -> dict[str, BoardIntelligenceRecord]:
    return {board_key(row.brand, row.model): row for row in load_board_records()}


def find_board_record(brand: str | None, model: str | None) -> BoardIntelligenceRecord | None:
    record = board_record_lookup().get(board_key(brand, model))
    if record:
        return record
    staged = find_staged_model(brand, model)
    if not staged:
        return None
    master = find_master_board(staged["manufacturer"], staged["model"])
    sizes = _sizes_from_profile(staged)
    volume_min, volume_max = _sizes_volume_range(sizes)
    return BoardIntelligenceRecord(
        brand=staged["manufacturer"],
        model=staged["model"],
        board_model_id=None,
        category=master["board_type"] if master else "Surfboard",
        primary_category=category_key(master["detailed_category"]) if master else None,
        lane=((master.get("recommendation_lanes") or [None])[0] if master else None),
        description=staged.get("official_description"),
        short_description=None,
        official_product_url=staged.get("official_product_url"),
        source_type="governed_board_master_phase3",
        source_confidence=1.0 if master and master.get("confidence") == "high" else 0.8,
        curated=bool(master),
        graph_eligible=bool(master),
        classified=bool(master),
        unclassified=False,
        is_current_model=True,
        ability_tags=_text_list(master.get("ability_range") if master else None),
        wave_types=_text_list(master.get("wave_type") if master else None),
        strengths=_text_list(master.get("strengths") if master else None),
        trade_offs=_text_list(master.get("weaknesses") if master else None),
        recommendation_lanes=_text_list(master.get("recommendation_lanes") if master else None),
        excluded_recommendation_lanes=_text_list(master.get("excluded_recommendation_lanes") if master else None),
        sizes=sizes,
        volume_min_litres=volume_min,
        volume_max_litres=volume_max,
        metadata_missing_fields=(),
    )


def board_intelligence_baseline() -> dict[str, int]:
    canonical_profiles = _load_json(GENERATED_DIR / "canonical_board_profiles.json", default=[])
    recommendation_graph = _load_json(GENERATED_DIR / "board_recommendation_graph.json", default={}).get("boards", [])
    relationship_graph = _load_json(GENERATED_DIR / "board_relationship_graph.json", default={}).get("boards", [])
    audit = _load_json(GENERATED_DIR / "board_intelligence_audit.json", default={})

    invalid_relationship_references = 0
    valid_models = {
        board_key(row.get("brand"), row.get("model"))
        for row in relationship_graph
        if isinstance(row, dict) and row.get("brand") and row.get("model")
    }
    for row in relationship_graph:
        if not isinstance(row, dict):
            continue
        for related_rows in (row.get("relationships") or {}).values():
            if not isinstance(related_rows, list):
                continue
            for related in related_rows:
                if board_key(related.get("brand"), related.get("model")) not in valid_models:
                    invalid_relationship_references += 1

    return {
        "canonical_board_profiles": len(canonical_profiles),
        "graph_eligible_models": len(recommendation_graph),
        "unclassified_board_intelligence_records": int(audit.get("unclassifiedCount") or 0),
        "invalid_relationship_references": invalid_relationship_references,
    }
