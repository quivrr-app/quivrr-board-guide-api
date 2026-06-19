from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "app" / "knowledge" / "generated" / "canonical_board_profiles.json"
GENERATED_INTELLIGENCE_PATH = ROOT / "app" / "knowledge" / "generated" / "board_intelligence_generated.json"
OUTPUT_PATH = ROOT / "app" / "knowledge" / "generated" / "canonical_board_intelligence.json"
CATEGORY_INDEX_PATH = ROOT / "app" / "knowledge" / "generated" / "manufacturer_category_index.json"
PHASE2_GAP_PATH = ROOT / "app" / "knowledge" / "audits" / "board_intelligence_matrix_gap_report.csv"
COVERAGE_JSON = ROOT / "app" / "knowledge" / "audits" / "phase3_harvest_coverage.json"
COVERAGE_CSV = ROOT / "app" / "knowledge" / "audits" / "phase3_harvest_coverage.csv"

PRIORITY_BRANDS = {"Sharp Eye", "Pyzel", "Lost", "JS Industries", "DHD", "Rusty"}
CATEGORY_PAGES = {
    "Pyzel": [
        ("High Performance", "https://pyzelsurfboards.com/pages/model-category/high-performance"),
        ("Daily Drivers", "https://pyzelsurfboards.com/pages/model-category/daily-drivers"),
        ("Funformance", "https://pyzelsurfboards.com/pages/model-category/funformance"),
        ("Mid Length / Gun", "https://pyzelsurfboards.com/pages/model-category/guns"),
    ],
    "JS Industries": [
        ("Charger Series", "https://jsindustries.com/collections/charger-series-1"),
        ("Performer Series", "https://jsindustries.com/collections/performer-series"),
        ("Daily Series", "https://jsindustries.com/collections/daily-series"),
        ("Fun Series", "https://jsindustries.com/collections/fun-series"),
        ("Youth Series", "https://jsindustries.com/collections/youth-series-1"),
        ("Foil Boards", "https://jsindustries.com/collections/foil-boards-1"),
        ("Softboards", "https://jsindustries.com/collections/softboards-1"),
    ],
}
RETAILER_HOST_TOKENS = {
    "58surf", "surf58", "surfboss", "surf-boss", "surfcorner", "mundo-surf",
    "singlequiver", "bell-surf", "boardcave", "surfshop",
}

CATEGORY_MAP = {
    ("JS Industries", "Daily Series"): ("daily_driver", []),
    ("JS Industries", "Performer Series"): ("performance_shortboard", ["high_performance"]),
    ("JS Industries", "Charger Series"): ("step_up", ["high_performance"]),
    ("JS Industries", "Youth Series"): ("youth", []),
    ("JS Industries", "Foil Boards"): ("foil", []),
    ("JS Industries", "Softboards"): ("softboard", []),
    ("Pyzel", "Daily Drivers"): ("daily_driver", []),
    ("Pyzel", "High Performance"): ("high_performance", ["performance_shortboard"]),
    ("Lost", "Performance"): ("performance_shortboard", ["high_performance"]),
    ("Lost", "Something Fishy"): ("fish", []),
    ("Lost", "Grovellers"): ("groveller", []),
    ("Lost", "Recreational Vehicles"): ("hybrid", []),
    ("Lost", "Mid Lengths"): ("mid_length", []),
    ("Lost", "Step Ups"): ("step_up", []),
    ("Sharp Eye", "Performance Range"): ("performance_shortboard", ["high_performance"]),
    ("Sharp Eye", "Pro Range"): ("performance_shortboard", ["high_performance"]),
    ("Sharp Eye", "Pro Model"): ("performance_shortboard", ["high_performance"]),
    ("Sharp Eye", "Alternate Range"): ("hybrid", []),
    ("Sharp Eye", "XL Range"): ("step_up", ["high_performance"]),
    ("Sharp Eye", "Youth Range"): ("youth", ["performance_shortboard"]),
}

ABILITY_ORDER = ["beginner", "intermediate", "advanced", "expert"]


def clean(value: object) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def model_key(row: dict) -> tuple[str, str]:
    return key(row.get("brand")), key(row.get("model"))


def refresh_category_index() -> dict:
    import requests

    categories = []
    headers = {"User-Agent": "QuivrrCanonicalIntelligence/1.0 (+read-only manufacturer category audit)"}
    for brand, pages in CATEGORY_PAGES.items():
        for category, source_url in pages:
            if brand == "JS Industries":
                endpoint = source_url.rstrip("/") + "/products.json?limit=250"
                response = requests.get(endpoint, headers=headers, timeout=30)
                response.raise_for_status()
                models = sorted({key(product.get("title")) for product in response.json().get("products", []) if product.get("title")})
            else:
                response = requests.get(source_url, headers=headers, timeout=30)
                response.raise_for_status()
                handles = re.findall(
                    r'class="image-overlay__image-link"\s+href="/pages/board-model/([^"?#/]+)',
                    response.text, flags=re.IGNORECASE,
                )
                models = sorted({key(handle) for handle in handles})
            categories.append({"brand": brand, "manufacturerCategory": category, "sourceUrl": source_url, "modelKeys": models})
    payload = {"schemaVersion": "manufacturer_category_index_v1", "sourceType": "manufacturer_category_page", "categories": categories}
    CATEGORY_INDEX_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def load_category_index() -> dict[tuple[str, str], list[dict]]:
    if not CATEGORY_INDEX_PATH.exists():
        return {}
    payload = json.loads(CATEGORY_INDEX_PATH.read_text(encoding="utf-8"))
    output: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for category in payload.get("categories", []):
        for model in category.get("modelKeys", []):
            output[(key(category.get("brand")), key(model))].append(category)
    return output


def indexed_category(brand: str, model: str, index: dict[tuple[str, str], list[dict]]) -> tuple[str | None, str | None, list[str]]:
    rows = index.get((key(brand), key(model)), [])
    if not rows:
        return None, None, []
    return rows[0]["manufacturerCategory"], rows[0]["sourceUrl"], [row["manufacturerCategory"] for row in rows]


def first_sentences(value: str, limit: int = 360) -> str | None:
    if not value:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", value)
    output = ""
    for sentence in sentences:
        candidate = f"{output} {sentence}".strip()
        if len(candidate) > limit and output:
            break
        output = candidate[:limit]
        if len(output) >= 120:
            break
    return output or None


def is_retailer_url(url: object) -> bool:
    host = urlparse(str(url or "")).netloc.lower()
    return any(token in host for token in RETAILER_HOST_TOKENS)


def choose_model_rows(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        row_key = model_key(row)
        if all(row_key):
            groups[row_key].append(row)
    return groups


def description_candidates(groups: dict[tuple[str, str], list[dict]]) -> dict[tuple[str, str], str]:
    candidates = {}
    owners: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row_key, rows in groups.items():
        values = [str(row.get("description") or "") for row in rows]
        value = max(values, key=lambda item: len(clean(item)), default="")
        if value:
            candidates[row_key] = value
            owners[key(value)].add(row_key)
    generic = {value_key for value_key, model_keys in owners.items() if len(model_keys) >= 3}
    return {
        row_key: value for row_key, value in candidates.items()
        if len(clean(value)) >= 80 and key(value) not in generic and key(value) not in {"surfboard", "surf board"}
    }


def trusted_source(rows: list[dict]) -> tuple[str | None, str | None]:
    for row in rows:
        source_type = clean(row.get("description_source_type")).lower()
        url = row.get("description_source_url") or row.get("official_product_url") or row.get("source")
        if source_type == "manufacturer" and str(url or "").startswith("http") and not is_retailer_url(url):
            return str(url), "manufacturer"
    for row in rows:
        url = row.get("official_product_url")
        if str(url or "").startswith("http") and not is_retailer_url(url):
            return str(url), "manufacturer_product_page"
    return None, None


def extract_manufacturer_category(brand: str, model: str, description: str) -> tuple[str | None, str | None]:
    if brand == "Sharp Eye":
        patterns = [
            r"(?:Overview\s+)?(?:[A-Z0-9#.+ -]+ Model\s+)?(?:Performance\s+)?(XL Range|Performance Range|Pro Range|Alternate Range|Youth Range)",
            r"Model Outline\s+(XL Range|Performance Range|Pro Range|Pro model|Alternate Range|Youth Range)",
        ]
        for pattern in patterns:
            match = re.search(pattern, description, flags=re.IGNORECASE)
            if match:
                label = next(label for label in ["XL Range", "Performance Range", "Pro Range", "Pro Model", "Alternate Range", "Youth Range"] if key(label) == key(match.group(1)))
                return label, "manufacturer_product_description"
    if brand == "JS Industries":
        for label in ["Charger Series", "Performer Series", "Daily Series", "Fun Series", "Youth Series", "Foil Boards", "Softboards"]:
            if re.search(rf"\b{re.escape(label)}\b", description, flags=re.IGNORECASE):
                return label, "manufacturer_product_description"
        if re.search(r"\byouth\b", model, flags=re.IGNORECASE):
            return "Youth Series", "manufacturer_model_name"
        if re.search(r"\bsoftboard\b", model, flags=re.IGNORECASE):
            return "Softboards", "manufacturer_model_name"
    if brand == "Pyzel":
        for label in ["Daily Drivers", "Funformance", "Mid Length / Gun"]:
            if re.search(rf"\b{re.escape(label)}\b", description, flags=re.IGNORECASE):
                return label, "manufacturer_product_description"
        if re.search(r"\b(?:High Performance (?:category|collection|range)|(?:category|collection|range)\s*:?\s*High Performance)\b", description, re.I):
            return "High Performance", "manufacturer_product_description"
    if brand == "Lost":
        variants = {
            "Something Fishy": ["Something Fishy"],
            "Grovellers": ["Grovellers", "Grovelers"],
            "Recreational Vehicles": ["Recreational Vehicles"],
            "Mid Lengths": ["Mid Lengths", "Mid-Lengths"], "Step Ups": ["Step Ups", "Step-Ups"],
        }
        for label, tokens in variants.items():
            if any(re.search(rf"\b{re.escape(token)}\b", description, flags=re.IGNORECASE) for token in tokens):
                return label, "manufacturer_product_description"
        if re.search(r"\b(?:Performance (?:category|collection|range)|(?:category|collection|range)\s*:?\s*Performance)\b", description, re.I):
            return "Performance", "manufacturer_product_description"
    return None, None


def map_manufacturer_category(brand: str, manufacturer_category: str | None, description: str) -> tuple[str | None, list[str], str | None, str | None]:
    if not manufacturer_category:
        return derive_category(description)
    direct = CATEGORY_MAP.get((brand, manufacturer_category))
    if direct:
        return direct[0], direct[1], "deterministic_category_mapping", "medium"
    lowered = description.lower()
    if (brand, manufacturer_category) == ("JS Industries", "Fun Series"):
        primary = "groveller" if re.search(r"small|weak|grovel", lowered) else "hybrid"
        return primary, ["hybrid"] if primary == "groveller" else [], "deterministic_category_mapping", "medium"
    if (brand, manufacturer_category) == ("Pyzel", "Funformance"):
        primary = "groveller" if re.search(r"small|weak|grovel", lowered) else "hybrid"
        return primary, ["hybrid"] if primary == "groveller" else [], "deterministic_category_mapping", "medium"
    if (brand, manufacturer_category) == ("Pyzel", "Mid Length / Gun"):
        if re.search(r"\bgun|big wave|serious|heavy\b", lowered):
            return "gun", ["step_up"], "deterministic_category_mapping", "medium"
        return "mid_length", [], "deterministic_category_mapping", "medium"
    return None, [], None, None


def derive_category(description: str) -> tuple[str | None, list[str], str | None, str | None]:
    rules = [
        ("softboard", r"\bsoftboard\b"), ("foil", r"\bfoil board\b"),
        ("longboard", r"\blongboard\b"), ("mid_length", r"\bmid[- ]?length\b"),
        ("step_up", r"\bstep[- ]?up|semi[- ]?gun\b"), ("groveller", r"\bgrovell?er\b"),
        ("fish", r"\b(?:keel |retro )?fish(?: surfboard| shape)?\b"),
        ("performance_shortboard", r"\b(?:high[- ]?)?performance shortboard\b"),
        ("daily_driver", r"\bdaily driver|everyday shortboard|one[- ]board quiver|true all[- ]rounder\b"),
        ("hybrid", r"\bhybrid (?:shortboard|surfboard)\b"),
    ]
    for category, pattern in rules:
        if re.search(pattern, description, flags=re.IGNORECASE):
            secondary = ["high_performance"] if category == "performance_shortboard" and re.search(r"high[- ]performance", description, re.I) else []
            return category, secondary, "deterministic_manufacturer_description", "medium"
    return None, [], None, None


def extract_wave_range(description: str) -> tuple[float | None, float | None, str | None, str | None]:
    patterns = [
        r"(?:Ideal Wave Size|Wave Height|Wave Size|waves? from|waves? of)?\s*(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:ft|foot|feet)",
        r"(?:Ideal Wave Size|Wave Height|Wave Size)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:ft|foot|feet)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:ft|foot|feet)",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            low, high = float(match.group(1)), float(match.group(2))
            if 0.5 <= low <= high <= 30:
                source = "manufacturer_product_scale" if re.search(r"Ideal Wave Size|Wave Height|Wave Size", match.group(0), re.I) else "manufacturer_product_description"
                return low, high, source, "high" if source.endswith("scale") else "medium"
    return None, None, None, None


def extract_wave_types(description: str) -> tuple[list[str], str | None, str | None]:
    mappings = [("beach_break", r"\bbeach ?break\b"), ("point_break", r"\bpoint ?break\b"), ("reef_break", r"\breef ?break\b"), ("wave_pool", r"\bwave pool\b")]
    values = [value for value, pattern in mappings if re.search(pattern, description, re.I)]
    if values:
        source = "manufacturer_product_scale" if re.search(r"Wave Type\s*:", description, re.I) else "manufacturer_product_description"
        return values, source, "high" if source.endswith("scale") else "medium"
    return [], None, None


def extract_wave_power(description: str) -> tuple[list[str], str | None, str | None]:
    values = []
    if re.search(r"\bweak|soft|gutless|mushy\b", description, re.I): values.append("weak")
    if re.search(r"\beveryday|average conditions|all[- ]round\b", description, re.I): values.append("average")
    if re.search(r"\bpowerful|hollow|heavy|serious conditions|conditions of consequence\b", description, re.I): values.append("powerful")
    return (values, "manufacturer_product_description", "medium") if values else ([], None, None)


def extract_abilities(description: str) -> tuple[str | None, str | None, list[str], str | None, str | None]:
    labelled = re.search(
        r"Ability\s*:\s*(beginner|intermediate|advanced|expert)\s*(?:to|-|–|—)\s*"
        r"(beginner|intermediate|advanced|expert)", description, re.I
    )
    if labelled:
        low, high = labelled.group(1).lower(), labelled.group(2).lower()
        profiles = [value for value in [sentence_with(description, ["surfer", "ability", "recommended for"])] if value]
        return low, high, profiles, "manufacturer_product_scale", "high"
    found = []
    for ability in ABILITY_ORDER:
        if re.search(rf"\b{ability}\b", description, re.I):
            found.append(ability)
    if re.search(r"\bnovice\b", description, re.I): found.append("beginner")
    if re.search(r"\bexperienced surfer\b", description, re.I): found.append("advanced")
    if re.search(r"\bprofessional(?: surfer)?|pro[- ]level\b", description, re.I): found.append("expert")
    found = sorted(set(found), key=ABILITY_ORDER.index)
    if not found:
        return None, None, [], None, None
    indices = [ABILITY_ORDER.index(value) for value in found]
    source = "manufacturer_product_scale" if re.search(r"Ability\s*:", description, re.I) else "manufacturer_product_description"
    profiles = []
    practical = sentence_with(description, ["surfer", "ability", "recommended for"])
    if practical:
        profiles.append(practical)
    return ABILITY_ORDER[min(indices)], ABILITY_ORDER[max(indices)], profiles, source, "high" if source.endswith("scale") else "medium"


def sentence_with(description: str, tokens: list[str], limit: int = 420) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", description):
        if any(token in sentence.lower() for token in tokens):
            return clean(sentence)[:limit]
    return None


def compact_notes(values: list[str], limit: int = 700) -> str | None:
    sentences = []
    for value in values:
        for sentence in re.split(r"(?<=[.!?])\s+", clean(value)):
            sentence = clean(sentence)
            if sentence and sentence not in sentences:
                sentences.append(sentence)
    output = " ".join(sentences)
    return output[:limit].rstrip() or None


def design_value(description: str, field: str) -> str | None:
    patterns = {
        "outline": [r"Model Outline\s+([^.]{3,180})", r"((?:fuller|performance|traditional|modern|wide|narrow|pulled[- ]in)[^.]*?outline[^.]*)"],
        "entryRocker": [r"((?:flat|low|medium|full|relaxed|continuous|moderate|high|smooth)[^.,;]{0,45}entry rocker)"],
        "exitRocker": [r"((?:flat|flattened|low|medium|full|relaxed|continuous|moderate|high)[^.,;]{0,45}exit rocker)"],
        "railType": [r"((?:sensitive |forgiving |soft |hard |low |medium |boxy |full |refined ){1,4}rails?)"],
    }
    for pattern in patterns[field]:
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            return clean(match.group(1)).rstrip(" .")
    if field == "outline":
        return sentence_with(description, ["outline"], limit=300)
    return None


def fin_setup(rows: list[dict], description: str) -> tuple[str | None, str | None, str | None]:
    values = [clean(row.get("fin_system")) for row in rows if clean(row.get("fin_system"))]
    if values:
        return Counter(values).most_common(1)[0][0], "manufacturer_profile_field", "high"
    match = re.search(r"Fin (?:Setup|Set[- ]?up)\s*:?\s*([A-Za-z0-9+ /-]{3,50})", description, re.I)
    return (clean(match.group(1)), "manufacturer_product_scale", "high") if match else (None, None, None)


def tail_shape(rows: list[dict], description: str) -> tuple[str | None, str | None, str | None]:
    values = [clean(row.get("tail_shape")) for row in rows if clean(row.get("tail_shape"))]
    if values:
        return Counter(values).most_common(1)[0][0], "manufacturer_profile_field", "high"
    match = re.search(r"\b(squash|swallow|round pin|rounded pin|pin|round|diamond|moon|thumb) tail\b", description, re.I)
    return (clean(match.group(0)), "manufacturer_product_description", "medium") if match else (None, None, None)


def construction_notes(description: str) -> tuple[str | None, str | None, str | None]:
    value = sentence_with(description, ["construction", "carbon", "fiberglass", "fibreglass", "eps", "epoxy", "polyurethane"])
    return (value, "manufacturer_product_description", "medium") if value else (None, None, None)


def practical_surfer_notes(brand: str, description: str) -> list[str]:
    if brand != "Rusty":
        return []
    notes = []
    for tokens in (["extra litre", "extra liter", "more volume"], ["paddle", "wave entry", "catch waves"]):
        value = sentence_with(description, list(tokens))
        if value and value not in notes:
            notes.append(value)
    return notes


def merge_generated_group(rows: list[dict]) -> dict:
    ordered = sorted(rows, key=lambda row: float(row.get("classificationConfidence") or 0), reverse=True)
    merged = dict(ordered[0]) if ordered else {}
    for field in ["waveType", "wavePower", "surferLevel"]:
        merged[field] = sorted({value for row in rows for value in (row.get(field) or [])})
    for field in ["rocker_notes", "tail_notes", "fin_setup_notes", "construction_notes"]:
        merged[field] = max((clean(row.get(field)) for row in rows), key=len, default="") or None
    for row in ordered:
        if row.get("boardCategory") not in {None, "", "unclassified"}:
            merged["boardCategory"] = row["boardCategory"]
            break
    for row in ordered:
        if row.get("waveRangeMinFt") is not None and row.get("waveRangeMaxFt") is not None:
            merged["waveRangeMinFt"], merged["waveRangeMaxFt"] = row["waveRangeMinFt"], row["waveRangeMaxFt"]
            break
    return merged


def harvest_profile(rows: list[dict], description: str | None, fallback: dict | None = None, category_index: dict | None = None) -> dict:
    fallback = fallback or {}
    representative = max(rows, key=lambda row: len(clean(row.get("description"))))
    brand, model = representative.get("brand"), representative.get("model")
    source_url, source_type = trusted_source(rows)
    trusted_description = description if source_url and source_type else None
    indexed, indexed_source, indexed_categories = indexed_category(brand, model, category_index or {})
    manufacturer_category, manufacturer_category_source = extract_manufacturer_category(brand, model, trusted_description or "")
    if indexed:
        manufacturer_category, manufacturer_category_source = indexed, "manufacturer_category_page"
    primary, secondary, category_source, category_confidence = map_manufacturer_category(brand, manufacturer_category, trusted_description or "")
    if len(indexed_categories) > 1:
        for extra_category in indexed_categories[1:]:
            extra_primary, extra_secondary, _, _ = map_manufacturer_category(brand, extra_category, trusted_description or "")
            if extra_primary and extra_primary != primary:
                secondary.append(extra_primary)
            secondary.extend(extra_secondary)
    wave_min, wave_max, wave_source, wave_confidence = extract_wave_range(trusted_description or "")
    wave_types, wave_type_source, wave_type_confidence = extract_wave_types(trusted_description or "")
    wave_power, wave_power_source, wave_power_confidence = extract_wave_power(trusted_description or "")
    ability_min, ability_max, profiles, surfer_source, surfer_confidence = extract_abilities(trusted_description or "")
    profiles.extend(value for value in practical_surfer_notes(brand, trusted_description or "") if value not in profiles)
    outline = design_value(trusted_description or "", "outline")
    rail = design_value(trusted_description or "", "railType")
    entry = design_value(trusted_description or "", "entryRocker")
    exit_value = design_value(trusted_description or "", "exitRocker")
    tail, tail_source, tail_confidence = tail_shape(rows, trusted_description or "")
    fins, fin_source, fin_confidence = fin_setup(rows, trusted_description or "")
    construction, construction_source, construction_confidence = construction_notes(trusted_description or "")
    fallback_category = fallback.get("boardCategory")
    if not primary and fallback_category and fallback_category != "unclassified":
        primary, category_source, category_confidence = fallback_category, "generated_fallback", "low"
    if wave_min is None and fallback.get("waveRangeMinFt") is not None and fallback.get("waveRangeMaxFt") is not None:
        wave_min, wave_max, wave_source, wave_confidence = fallback.get("waveRangeMinFt"), fallback.get("waveRangeMaxFt"), "generated_fallback", "low"
    if not wave_types and fallback.get("waveType"):
        wave_types, wave_type_source, wave_type_confidence = list(fallback["waveType"]), "generated_fallback", "low"
    if not wave_power and fallback.get("wavePower"):
        wave_power, wave_power_source, wave_power_confidence = list(fallback["wavePower"]), "generated_fallback", "low"
    if not ability_min and fallback.get("surferLevel"):
        levels = [value for value in fallback["surferLevel"] if value in ABILITY_ORDER]
        if levels:
            indices = [ABILITY_ORDER.index(value) for value in levels]
            ability_min, ability_max = ABILITY_ORDER[min(indices)], ABILITY_ORDER[max(indices)]
            surfer_source, surfer_confidence = "generated_fallback", "low"
    legacy_design_notes = compact_notes([
        clean(fallback.get(field)) for field in ["rocker_notes", "tail_notes", "fin_setup_notes", "construction_notes"]
        if clean(fallback.get(field))
    ])
    design_present = any([outline, rail, entry, exit_value, tail, fins, construction])
    design_present = design_present or bool(legacy_design_notes)
    design_confidence = "high" if any(value == "high" for value in [tail_confidence, fin_confidence]) else "medium" if any([outline, rail, entry, exit_value, tail, fins, construction]) else "low" if legacy_design_notes else None
    missing = []
    for field, present in [
        ("manufacturerDescription", trusted_description), ("manufacturerCategory", manufacturer_category),
        ("primaryCategory", primary), ("waveHeight", wave_min is not None and wave_max is not None),
        ("waveTypes", wave_types), ("wavePower", wave_power),
        ("surferAbility", ability_min and ability_max), ("designMetadata", design_present),
    ]:
        if not present: missing.append(field)
    notes = []
    if brand not in PRIORITY_BRANDS:
        notes.append("Phase 3 structured harvesting deferred for this brand; trusted description retained.")
    if trusted_description and not manufacturer_category:
        notes.append("No explicit manufacturer category label found; category is derived only when description evidence is deterministic.")
    if len(indexed_categories) > 1:
        notes.append("Manufacturer category page lists this model in: " + ", ".join(indexed_categories) + ".")
    return {
        "identity": {"brand": brand, "model": model, "boardModelId": representative.get("board_model_id"), "sourceUrl": source_url, "sourceType": source_type, "lastUpdatedUtc": representative.get("description_last_scraped_utc")},
        "description": {"manufacturerDescription": trusted_description, "shortDescription": first_sentences(trusted_description or ""), "descriptionSource": source_url if trusted_description else None, "descriptionConfidence": "high" if trusted_description and source_type == "manufacturer" else "medium" if trusted_description else None},
        "category": {"manufacturerCategory": manufacturer_category, "manufacturerCategories": indexed_categories or ([manufacturer_category] if manufacturer_category else []), "manufacturerSeries": manufacturer_category if brand == "JS Industries" else None, "manufacturerCategorySource": "manufacturer_category_page" if indexed_source else manufacturer_category_source, "manufacturerCategorySourceUrl": indexed_source, "manufacturerCategoryConfidence": "high" if manufacturer_category else None, "primaryCategory": primary, "secondaryCategories": sorted(set(secondary)), "categorySource": category_source, "categoryConfidence": category_confidence},
        "wave": {"waveHeightMinFt": wave_min, "waveHeightMaxFt": wave_max, "waveTypes": wave_types, "wavePower": wave_power, "waveSource": wave_source or wave_type_source or wave_power_source, "waveConfidence": "high" if "high" in [wave_confidence, wave_type_confidence, wave_power_confidence] else "medium" if "medium" in [wave_confidence, wave_type_confidence, wave_power_confidence] else "low" if any([wave_min is not None, wave_types, wave_power]) else None, "fieldSources": {"waveHeight": wave_source, "waveTypes": wave_type_source, "wavePower": wave_power_source}, "fieldConfidence": {"waveHeight": wave_confidence, "waveTypes": wave_type_confidence, "wavePower": wave_power_confidence}},
        "surfer": {"abilityMin": ability_min, "abilityMax": ability_max, "surferProfiles": profiles, "surferSource": surfer_source or ("manufacturer_product_description" if profiles else None), "surferConfidence": surfer_confidence or ("medium" if profiles else None)},
        "design": {"outline": outline, "railType": rail, "entryRocker": entry, "exitRocker": exit_value, "tailShape": tail, "finSetup": fins, "constructionNotes": construction, "designNotes": legacy_design_notes, "designSource": "mixed_manufacturer_and_generated" if legacy_design_notes and any([outline, rail, entry, exit_value, tail, fins, construction]) else "generated_fallback" if legacy_design_notes else "manufacturer_profile_and_description" if design_present else None, "designConfidence": design_confidence, "fieldSources": {"outline": "manufacturer_product_description" if outline else None, "railType": "manufacturer_product_description" if rail else None, "entryRocker": "manufacturer_product_description" if entry else None, "exitRocker": "manufacturer_product_description" if exit_value else None, "tailShape": tail_source, "finSetup": fin_source, "constructionNotes": construction_source, "designNotes": "generated_fallback" if legacy_design_notes else None}},
        "metadata": {"missingFields": missing, "extractionNotes": notes, "reviewedByQuivrr": None, "reviewedAtUtc": None},
    }


def has_design(profile: dict) -> bool:
    return any(profile["design"].get(field) for field in ["outline", "railType", "entryRocker", "exitRocker", "tailShape", "finSetup", "constructionNotes", "designNotes"])


def phase2_coverage() -> tuple[dict, dict[str, dict]]:
    with PHASE2_GAP_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    def yes(row: dict, field: str) -> bool: return row.get(field) == "True"
    overall = {
        "totalModels": len(rows), "descriptions": sum(yes(row, "descriptionPresent") for row in rows),
        "categories": sum(yes(row, "categoryPresent") for row in rows),
        "waveMetadata": sum(any(yes(row, field) for field in ["waveRangePresent", "waveTypePresent", "wavePowerPresent"]) for row in rows),
        "surferMetadata": sum(yes(row, "abilityPresent") for row in rows),
        "designMetadata": sum(yes(row, "designMetadataPresent") for row in rows),
    }
    by_brand = {}
    for brand in sorted({row["brand"] for row in rows}):
        selected = [row for row in rows if row["brand"] == brand]
        by_brand[brand] = {
            "models": len(selected), "descriptions": sum(yes(row, "descriptionPresent") for row in selected),
            "categories": sum(yes(row, "categoryPresent") for row in selected),
            "waveMetadata": sum(any(yes(row, field) for field in ["waveRangePresent", "waveTypePresent", "wavePowerPresent"]) for row in selected),
            "surferMetadata": sum(yes(row, "abilityPresent") for row in selected),
            "designMetadata": sum(yes(row, "designMetadataPresent") for row in selected),
        }
    return overall, by_brand


def after_coverage(profiles: list[dict]) -> tuple[dict, dict[str, dict]]:
    overall = {
        "totalModels": len(profiles), "descriptions": sum(bool(row["description"]["manufacturerDescription"]) for row in profiles),
        "categories": sum(bool(row["category"]["primaryCategory"]) for row in profiles),
        "waveMetadata": sum(bool(row["wave"]["waveHeightMinFt"] is not None or row["wave"]["waveTypes"] or row["wave"]["wavePower"]) for row in profiles),
        "surferMetadata": sum(bool(row["surfer"]["abilityMin"] or row["surfer"]["surferProfiles"]) for row in profiles),
        "designMetadata": sum(has_design(row) for row in profiles),
    }
    by_brand = {}
    for brand in sorted({row["identity"]["brand"] for row in profiles}):
        selected = [row for row in profiles if row["identity"]["brand"] == brand]
        top_missing = Counter(field for row in selected for field in row["metadata"]["missingFields"]).most_common(3)
        by_brand[brand] = {
            "models": len(selected), "descriptions": sum(bool(row["description"]["manufacturerDescription"]) for row in selected),
            "categories": sum(bool(row["category"]["primaryCategory"]) for row in selected),
            "waveMetadata": sum(bool(row["wave"]["waveHeightMinFt"] is not None or row["wave"]["waveTypes"] or row["wave"]["wavePower"]) for row in selected),
            "surferMetadata": sum(bool(row["surfer"]["abilityMin"] or row["surfer"]["surferProfiles"]) for row in selected),
            "designMetadata": sum(has_design(row) for row in selected),
            "sourceQuality": "manufacturer_primary" if any(row["description"]["descriptionConfidence"] == "high" for row in selected) else "incomplete",
            "topMissingFields": "; ".join(f"{field}: {count}" for field, count in top_missing),
        }
    return overall, by_brand


def write_coverage(before: dict, after: dict, before_brand: dict, after_brand: dict, mode: str) -> None:
    brand_rows = []
    for brand in sorted(after_brand):
        row = {"brand": brand, **after_brand[brand]}
        for field in ["descriptions", "categories", "waveMetadata", "surferMetadata", "designMetadata"]:
            row[f"{field}Before"] = before_brand.get(brand, {}).get(field, 0)
            row[f"{field}Gain"] = row[field] - row[f"{field}Before"]
        brand_rows.append(row)
    brands_enriched = sum(
        any(row[f"{field}Gain"] > 0 for field in ["categories", "waveMetadata", "surferMetadata", "designMetadata"])
        for row in brand_rows
    )
    report = {
        "auditVersion": "bodhi_phase_3_v1", "mode": mode,
        "architecture": "global canonical intelligence; regional inventory excluded",
        "outputDecision": "A separate model-level canonical_board_intelligence.json avoids repeating global intelligence across 573 construction rows and does not change runtime recommendations.",
        "totalModels": after["totalModels"], "brandsWithCoverageGain": brands_enriched,
        "before": before, "after": after,
        "gains": {field: after[field] - before[field] for field in ["descriptions", "categories", "waveMetadata", "surferMetadata", "designMetadata"]},
        "brands": brand_rows,
    }
    COVERAGE_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with COVERAGE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(brand_rows[0].keys()))
        writer.writeheader(); writer.writerows(brand_rows)


def write_profiles(profiles: list[dict]) -> None:
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write('{\n  "schemaVersion": "canonical_board_intelligence_v1",\n  "profiles": [\n')
        for index, profile in enumerate(profiles):
            suffix = "," if index < len(profiles) - 1 else ""
            handle.write("    " + json.dumps(profile, ensure_ascii=False, separators=(",", ":")) + suffix + "\n")
        handle.write("  ]\n}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Harvest deterministic global manufacturer board intelligence")
    parser.add_argument("--apply", action="store_true", help="Write the reviewed model-level generated intelligence output")
    parser.add_argument("--refresh-category-index", action="store_true", help="Refresh the small read-only manufacturer category-page snapshot")
    args = parser.parse_args(argv)
    if args.refresh_category_index:
        refresh_category_index()
    category_index = load_category_index()
    rows = json.loads(CANONICAL_PATH.read_text(encoding="utf-8-sig"))
    generated_rows = json.loads(GENERATED_INTELLIGENCE_PATH.read_text(encoding="utf-8-sig")).get("boards", [])
    generated_groups = choose_model_rows(generated_rows)
    generated = {row_key: merge_generated_group(group) for row_key, group in generated_groups.items()}
    groups = choose_model_rows(rows)
    descriptions = description_candidates(groups)
    profiles = [harvest_profile(group, descriptions.get(row_key), generated.get(row_key), category_index) for row_key, group in sorted(groups.items())]
    before, before_brand = phase2_coverage()
    after, after_brand = after_coverage(profiles)
    write_coverage(before, after, before_brand, after_brand, "apply" if args.apply else "dry_run")
    report = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    report["modelsEnriched"] = sum(
        any([
            profile["category"]["categorySource"] not in {None, "generated_fallback"},
            profile["wave"]["waveSource"] not in {None, "generated_fallback"},
            profile["surfer"]["surferSource"] not in {None, "generated_fallback"},
            profile["design"]["designSource"] not in {None, "generated_fallback"},
        ]) for profile in profiles
    )
    report["priorityBrandModelsEnriched"] = sum(
        profile["identity"]["brand"] in PRIORITY_BRANDS and any([
            profile["category"]["categorySource"] not in {None, "generated_fallback"},
            profile["wave"]["waveSource"] not in {None, "generated_fallback"},
            profile["surfer"]["surferSource"] not in {None, "generated_fallback"},
            profile["design"]["designSource"] not in {None, "generated_fallback"},
        ]) for profile in profiles
    )
    COVERAGE_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.apply:
        write_profiles(profiles)
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", "before": before, "after": after, "gains": {field: after[field] - before[field] for field in after if field != "totalModels"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
