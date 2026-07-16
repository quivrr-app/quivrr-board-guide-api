from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
DNA_PATH = ROOT / "app" / "knowledge" / "board_dna_v1.json"
EXPERT_PATH = ROOT / "app" / "knowledge" / "generated" / "board_expert_matrix.json"
OVERRIDES_PATH = ROOT / "app" / "knowledge" / "curated" / "board_master_editorial_overrides_v2.json"
REVIEW_ROOT = ROOT / "manufacturer_reviews"
MASTER_PATH = ROOT / "app" / "knowledge" / "curated" / "quivrr_board_master_matrix_v2.json"
AUDIT_ROOT = ROOT / "app" / "knowledge" / "audits" / "board_master_matrix_v2"

SHOPIFY_HOSTS = {
    "albumsurf.com", "cisurfboards.com", "dhdsurf.com", "firewiresurfboards.com",
    "haydenshapes.com", "jsindustries.com", "lostsurfboards.com.au", "pyzelsurf.com.au",
    "rustysurfboards.com", "sharpeyesurfboards.com.au",
}

MANUFACTURER_FILES = {
    "Album": "album_v1.json",
    "Channel Islands": "channel_islands_v1.json",
    "Chemistry Surfboards": "chemistry_surfboards_v1.json",
    "Chilli": "chilli_v1.json",
    "Christenson": "christenson_v1.json",
    "DHD": "dhd_v1.json",
    "DMS Surfboards": "dms_surfboards_v1.json",
    "Firewire": "firewire_v1.json",
    "Haydenshapes": "haydenshapes_v1.json",
    "JS Industries": "js_industries_v1.json",
    "Lost": "lost_v1.json",
    "Misfit Shapes": "misfit_shapes_v1.json",
    "Pukas": "pukas_v1.json",
    "Pyzel": "pyzel_v1.json",
    "Rusty": "rusty_v1.json",
    "Sharp Eye": "sharp_eye_v1.json",
    "Simon Anderson": "simon_anderson_v1.json",
}

PUBLIC_LABELS = {
    "fish": "Fish",
    "groveller": "Groveller",
    "daily_driver": "Daily Driver",
    "performance_shortboard": "Performance Shortboard",
    "step_up": "Step Up",
    "mid_length": "Mid Length",
    "longboard": "Longboard",
}

DETAILED_LABELS = {
    "daily_driver": "Everyday Daily Driver",
    "groveller": "Groveller",
    "hybrid_shortboard": "Hybrid Shortboard",
    "longboard": "Longboard",
    "mid_length": "Mid Length",
    "performance_daily_driver": "Performance Daily Driver",
    "performance_fish": "Performance Fish",
    "performance_mid_length": "Performance Mid Length",
    "performance_shortboard": "High Performance Shortboard",
    "performance_twin": "Performance Twin",
    "small_wave_shortboard": "Small Wave Performance Shortboard",
    "softboard": "Softboard",
    "step_up": "Step Up",
    "traditional_fish": "Traditional Fish",
    "twin_pin": "Twin Pin",
}

FIN_LABELS = {
    "thruster": "Thruster",
    "twin": "Twin",
    "twin_plus_trailer": "Twin + Trailer",
    "quad": "Quad",
    "two_plus_one": "2+1",
    "single": "Single",
    "single_plus_sidebites": "Single + Sidebites",
    "five_fin": "5 Fin",
    "convertible": "Convertible",
}

HTML_TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def clean(value: object) -> str:
    return SPACE.sub(" ", html.unescape(HTML_TAG.sub(" ", str(value or "")))).strip()


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def short_excerpt(value: str, words: int = 24) -> str:
    tokens = clean(value).split()
    return " ".join(tokens[:words]) + ("..." if len(tokens) > words else "")


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.descriptions: list[str] = []
        self.json_ld: list[str] = []
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = {name.lower(): value for name, value in attrs}
        if tag.lower() == "meta" and attributes.get("content"):
            name = (attributes.get("name") or attributes.get("property") or "").lower()
            if name in {"description", "og:description", "twitter:description"}:
                self.descriptions.append(attributes["content"])
        if tag.lower() == "script" and "ld+json" in (attributes.get("type") or "").lower():
            self._json_buffer = []

    def handle_data(self, data):
        if self._json_buffer is not None:
            self._json_buffer.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._json_buffer is not None:
            self.json_ld.append("".join(self._json_buffer))
            self._json_buffer = None


def json_descriptions(value) -> list[str]:
    output = []
    if isinstance(value, dict):
        if value.get("description"):
            output.append(str(value["description"]))
        for child in value.values():
            output.extend(json_descriptions(child))
    elif isinstance(value, list):
        for child in value:
            output.extend(json_descriptions(child))
    return output


def extract_html_description(page_html: str) -> str:
    parser = MetadataParser()
    parser.feed(page_html)
    candidates = list(parser.descriptions)
    for raw in parser.json_ld:
        try:
            candidates.extend(json_descriptions(json.loads(raw)))
        except (json.JSONDecodeError, TypeError):
            continue
    cleaned = [clean(value) for value in candidates if len(clean(value)) >= 40]
    return max(cleaned, key=len, default="")


class OfficialEvidence:
    def __init__(self, refresh: bool):
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; QUIVRR-Editorial-Review/2.0)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        })
        self.bulk: dict[str, dict] = {}

    def request(self, url: str, attempts: int = 3) -> requests.Response | None:
        for attempt in range(attempts):
            try:
                response = self.session.get(url, timeout=35, allow_redirects=True)
                if response.status_code == 429:
                    time.sleep(2 + attempt * 4)
                    continue
                return response
            except requests.RequestException:
                time.sleep(1 + attempt * 2)
        return None

    def load_store(self, host: str) -> dict:
        host = host.removeprefix("www.")
        if host in self.bulk:
            return self.bulk[host]
        response = self.request(f"https://{host}/products.json?limit=250")
        products = []
        if response and response.ok:
            try:
                products = response.json().get("products", [])
            except ValueError:
                products = []
        by_handle = {key(item.get("handle")): item for item in products if item.get("handle")}
        self.bulk[host] = {"products": products, "by_handle": by_handle}
        return self.bulk[host]

    def best_product(self, model: str, url: str) -> tuple[dict | None, str | None]:
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        store = self.load_store(host)
        path_parts = [part for part in parsed.path.split("/") if part]
        handle = path_parts[path_parts.index("products") + 1] if "products" in path_parts else None
        product = store["by_handle"].get(key(handle)) if handle else None
        if product:
            return product, "shopify_bulk_product"

        model_key = key(model)
        candidates = []
        for item in store["products"]:
            title_key = key(item.get("title"))
            body_key = key(item.get("body_html") or item.get("description"))
            score = 0
            if title_key == model_key:
                score = 100
            elif model_key and model_key in title_key:
                score = 80
            elif re.search(rf"\bsurfboard model\s+{re.escape(model_key)}\b", body_key):
                score = 90
            elif model_key and model_key in body_key:
                score = 40
            if score:
                candidates.append((score, len(clean(item.get("body_html") or item.get("description"))), item))
        if candidates:
            return max(candidates, key=lambda item: (item[0], item[1]))[2], "shopify_bulk_identity_match"

        if handle:
            response = self.request(f"{parsed.scheme}://{parsed.netloc}/products/{handle}.js")
            if response and response.ok:
                try:
                    return response.json(), "shopify_product_json"
                except ValueError:
                    pass
        return None, None

    def fetch(self, board: dict) -> dict:
        url = board["evidence"]["official_source_url"]
        stored = clean(board["evidence"].get("manufacturer_description"))
        if not self.refresh:
            return self.payload(url, url, stored, "stored_official_snapshot", None, False, board["model"])

        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host in SHOPIFY_HOSTS:
            product, method = self.best_product(board["model"], url)
            if product:
                description = clean(product.get("body_html") or product.get("description"))
                title = clean(product.get("title"))
                resolved = f"{parsed.scheme}://{parsed.netloc}/products/{product.get('handle')}" if product.get("handle") else url
                if description:
                    return self.payload(url, resolved, description, method, 200, True, board["model"], title)

        response = self.request(url)
        if response and response.ok:
            extracted = extract_html_description(response.text)
            description = extracted or stored
            if description:
                method = "official_html_metadata" if extracted else "official_html_with_snapshot_extract"
                return self.payload(url, response.url, description, method, response.status_code, True, board["model"])

        status = response.status_code if response else None
        return self.payload(url, response.url if response else url, stored, "stored_snapshot_after_live_failure", status, False, board["model"])

    @staticmethod
    def payload(url: str, resolved: str, description: str, method: str, status: int | None,
                live: bool, model: str, title: str = "") -> dict:
        model_tokens = [token for token in key(model).split() if len(token) > 1 or token.isdigit()]
        identity_text = key(f"{title} {resolved} {description[:20000]}")
        identity_match = bool(model_tokens) and all(token in identity_text for token in model_tokens)
        return {
            "official_url": url,
            "resolved_url": resolved,
            "retrieved_at_utc": utc_now(),
            "retrieval_method": method,
            "http_status": status,
            "live_verified": live,
            "identity_match": identity_match,
            "content_sha256": hashlib.sha256(description.encode("utf-8")).hexdigest() if description else None,
            "description_word_count": len(description.split()),
            "official_intent_excerpt": short_excerpt(description),
            "_description": description,
        }


def fin_setups(board: dict, evidence: str, expert: dict, override: dict) -> tuple[str, list[str], str]:
    if override.get("primary_fin_setup"):
        return override["primary_fin_setup"], override.get("alternative_fin_setup", []), "editorial_override"

    text = clean(evidence).lower()
    detected = []
    patterns = [
        ("Twin + Trailer", r"\b(?:twin\s*\+\s*1|twin plus trailer|twin trailer|twin fin with trailer)\b"),
        ("2+1", r"\b(?:2\s*\+\s*1|two plus one|2 plus 1)\b"),
        ("5 Fin", r"\b(?:5[- ]?fin|five[- ]?fin)\b"),
        ("Thruster", r"\bthruster\b|\b3[- ]?fin\b|\b3x (?:futures|fcs)\b"),
        ("Quad", r"\bquad\b|\b4[- ]?fin\b"),
        ("Twin", r"\btwin[- ]?fin\b"),
        ("Single + Sidebites", r"\bsingle (?:fin )?(?:with|plus) sidebites\b"),
        ("Single", r"\bsingle[- ]?fin\b"),
    ]
    for label, pattern in patterns:
        if re.search(pattern, text) and label not in detected:
            detected.append(label)
    category = board.get("primary_category")
    public_family = board.get("public_family")
    category_default = None
    if category in {"performance_twin", "traditional_fish", "twin_pin"}:
        category_default = "Twin"
    elif public_family in {"performance_shortboard", "daily_driver", "groveller", "step_up"}:
        category_default = "Thruster"
    elif public_family == "fish":
        category_default = "Twin"
    elif public_family == "longboard":
        category_default = "Single"

    if category_default and category_default in detected:
        detected.remove(category_default)
        detected.insert(0, category_default)
    if detected and (category_default is None or detected[0] == category_default):
        return detected[0], detected[1:], "official_manufacturer_text"

    if category_default:
        alternatives = [value for value in detected if value != category_default]
        return category_default, alternatives, "manufacturer_intent_category_default"

    configured = [FIN_LABELS.get(value, value.replace("_", " ").title()) for value in board["physical_design"].get("fin_configurations", [])]
    configured.extend(value for value in expert.get("finSetup", []) if value not in configured)
    configured = list(dict.fromkeys(configured)) or ["Thruster"]
    return configured[0], configured[1:], "governed_dna_fallback"


def detailed_category_for(board: dict, override: dict) -> str:
    if override.get("detailed_category"):
        return override["detailed_category"]
    family = board["public_family"]
    category = board["primary_category"]
    contextual = {
        ("performance_shortboard", "performance_twin"): "Alternative Performance Twin",
        ("performance_shortboard", "twin_pin"): "Performance Twin Pin",
        ("performance_shortboard", "performance_daily_driver"): "Forgiving HPSB",
        ("performance_shortboard", "hybrid_shortboard"): "Performance Shortboard",
        ("performance_shortboard", "performance_fish"): "Alternative Performance Shortboard",
        ("daily_driver", "performance_twin"): "Performance Twin Daily Driver",
        ("daily_driver", "performance_fish"): "Performance Daily Driver",
        ("daily_driver", "groveller"): "Small Wave Daily Driver",
        ("daily_driver", "small_wave_shortboard"): "Small Wave Daily Driver",
        ("groveller", "performance_twin"): "Small Wave Performance Twin",
        ("groveller", "performance_fish"): "Performance Groveller",
        ("groveller", "hybrid_shortboard"): "Small Wave Daily Driver",
        ("fish", "performance_twin"): "Performance Fish",
        ("step_up", "performance_twin"): "Alternative Reef Step Up",
        ("step_up", "performance_fish"): "Alternative Reef Step Up",
    }
    return contextual.get((family, category), DETAILED_LABELS.get(category, category.replace("_", " ").title()))


def manufacturer_intent_signals(description: str) -> list[str]:
    text = clean(description).lower()
    patterns = {
        "groveller": [r"\bhigh[- ]performance grovell?er\b", r"\bperformance grovell?er\b"],
        "performance_shortboard": [
            r"\bhigh[- ]performance shortboard\b", r"\bpro[- ]formance series shortboard\b",
            r"\bcompetition shortboard\b", r"\bhpsb\b",
        ],
        "mid_length": [r"\bmid[- ]length\b"],
        "longboard": [r"\blongboard\b", r"\bnose[- ]?riding longboard\b"],
        "step_up": [r"\bstep[- ]up\b", r"\bsemi[- ]gun\b", r"\bbig[- ]wave gun\b"],
        "daily_driver": [r"\bdaily driver\b", r"\beveryday shortboard\b", r"\ball[- ]round shortboard\b"],
        "fish": [r"\bperformance fish\b", r"\btraditional fish\b", r"\bretro fish\b", r"\bfish surfboard\b"],
    }
    return [family for family, expressions in patterns.items() if any(re.search(expression, text) for expression in expressions)]


def top_labels(values: dict, high: bool, count: int = 3) -> list[str]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=high)
    return [name.replace("_", " ") for name, _ in ordered[:count]]


def ability_range(board: dict) -> list[str]:
    levels = ["beginner", "progressing", "intermediate", "advanced", "expert"]
    fit = board.get("rider_fit", {})
    accepted = [level for level in levels if fit.get(level, 0) >= 5]
    return accepted or [max(levels, key=lambda level: fit.get(level, 0))]


def wave_context(board: dict, expert: dict) -> tuple[dict, list[str], list[str]]:
    size = {"minimum_ft": expert.get("waveRangeMinFt"), "maximum_ft": expert.get("waveRangeMaxFt")}
    power = expert.get("wavePower") or top_labels({
        "weak": board["conditions"].get("weak_waves", 0),
        "average": board["conditions"].get("average_waves", 0),
        "powerful": board["conditions"].get("powerful_waves", 0),
    }, True, 2)
    wave_types = expert.get("waveTypes") or top_labels({
        "beach break": board["conditions"].get("beach_break", 0),
        "point break": board["conditions"].get("point_break", 0),
        "reef break": board["conditions"].get("reef_break", 0),
        "hollow waves": board["conditions"].get("hollow_waves", 0),
        "open face": board["conditions"].get("open_face", 0),
    }, True, 3)
    return size, list(power), list(wave_types)


def record_for(board: dict, expert: dict, override: dict, official: dict) -> dict:
    previous_family = board["public_family"]
    previous_category = board["primary_category"]
    public_family = override.get("public_family", previous_family)
    detailed_category = detailed_category_for(board, override)
    board_type = override.get("board_type", PUBLIC_LABELS[public_family])
    description = official.pop("_description")
    intent_signals = manufacturer_intent_signals(description)
    unresolved_intent_conflict = len(intent_signals) == 1 and public_family not in intent_signals and not override
    primary_fin, alternative_fin, fin_source = fin_setups(board, description, expert, override)
    wave_size, wave_power, wave_type = wave_context(board, expert)
    abilities = ability_range(board)
    behaviour = board["behaviour"]
    strengths = expert.get("strengths") or top_labels(behaviour, True)
    weaknesses = expert.get("weaknesses") or top_labels(behaviour, False, 2)
    intent = official.get("official_intent_excerpt") or f"Official manufacturer evidence was unavailable for {board['model']}."
    source_confidence = board["evidence"].get("physical_design_confidence", "medium")
    review_required = (bool(board["evidence"].get("review_required")) or not official["live_verified"]
                       or not official["identity_match"] or unresolved_intent_conflict)
    confidence = "low" if review_required else ("high" if source_confidence == "high" or override else "medium")
    notes = list(board["evidence"].get("notes", []))
    if override:
        notes.append(override["reason"])
    if fin_source == "governed_dna_fallback":
        notes.append("Fin configuration was not explicit in the retrieved manufacturer text and remains a governed fallback requiring future confirmation.")

    return {
        "canonical_model_id": board["canonical_model_id"],
        "canonical_key": board["canonical_key"],
        "manufacturer": board["brand"],
        "model": board["model"],
        "official_url": official["official_url"],
        "official_evidence": official,
        "manufacturer_intent": intent,
        "manufacturer_intent_signals": intent_signals,
        "unresolved_intent_conflict": unresolved_intent_conflict,
        "public_family": public_family,
        "public_family_label": PUBLIC_LABELS[public_family],
        "detailed_category": detailed_category,
        "secondary_categories": board.get("secondary_categories", []),
        "board_type": board_type,
        "primary_fin_setup": primary_fin,
        "alternative_fin_setup": alternative_fin,
        "fin_configuration_source": fin_source,
        "tail_shape": board["physical_design"].get("tail", []),
        "outline": board["physical_design"].get("outline"),
        "bottom_contours": board["physical_design"].get("bottom_contours", []),
        "entry_rocker": board["physical_design"].get("rocker_entry"),
        "exit_rocker": board["physical_design"].get("rocker_tail"),
        "rail_type": board["physical_design"].get("rails"),
        "volume_philosophy": board["physical_design"].get("volume_distribution"),
        "wave_size": wave_size,
        "wave_power": wave_power,
        "wave_type": wave_type,
        "ability_range": abilities,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "typical_customer": f"{abilities[0].replace('_', ' ').title()} to {abilities[-1].replace('_', ' ').title()} surfer seeking a {detailed_category.lower()}.",
        "board_dna": {
            "physical_design": board["physical_design"],
            "behaviour": board["behaviour"],
            "conditions": board["conditions"],
            "rider_fit": board["rider_fit"],
            "style_tags": board.get("style_tags", []),
            "quiver_roles": board.get("quiver_roles", []),
        },
        "recommendation_lanes": expert.get("recommendationLanes") or expert.get("boardLanes") or [],
        "excluded_recommendation_lanes": expert.get("excludedLanes") or [],
        "editorial_notes": notes,
        "confidence": confidence,
        "review_required": review_required,
        "previous_public_family": previous_family,
        "previous_detailed_category": previous_category,
        "classification_changed": public_family != previous_family or bool(override.get("detailed_category")),
        "reviewed_date": "2026-07-17",
        "reviewed_by": "QUIVRR",
    }


def apply_review_override(record: dict, override: dict) -> dict:
    """Apply final editorial authority to a previously reviewed record."""
    if not override:
        return record

    model_id = int(record["canonical_model_id"])
    if model_id != int(override["canonical_model_id"]):
        raise ValueError(f"Editorial override ID mismatch for {model_id}")
    if key(override["brand"]) != key(record["manufacturer"]) or key(override["model"]) != key(record["model"]):
        raise ValueError(f"Editorial override identity mismatch for {model_id}")

    updated = dict(record)
    previous_family = updated["public_family"]
    previous_category = updated["detailed_category"]
    for field in (
        "public_family",
        "detailed_category",
        "board_type",
        "primary_fin_setup",
        "alternative_fin_setup",
        "recommendation_lanes",
        "excluded_recommendation_lanes",
    ):
        if field in override:
            updated[field] = override[field]

    updated["public_family_label"] = PUBLIC_LABELS[updated["public_family"]]
    updated["fin_configuration_source"] = "editorial_override"
    updated["unresolved_intent_conflict"] = False
    updated["confidence"] = "high"
    updated["classification_changed"] = (
        updated["public_family"] != updated.get("previous_public_family")
        or updated["detailed_category"] != updated.get("previous_detailed_category")
    )

    lanes = list(dict.fromkeys(updated.get("recommendation_lanes", [])))
    excluded = list(dict.fromkeys(updated.get("excluded_recommendation_lanes", [])))
    category_lane = re.sub(r"[^a-z0-9]+", "_", updated["detailed_category"].lower()).strip("_")
    for lane in (updated["public_family"], category_lane):
        if lane and lane not in lanes:
            lanes.append(lane)
        excluded = [candidate for candidate in excluded if candidate != lane]
    updated["recommendation_lanes"] = lanes
    updated["excluded_recommendation_lanes"] = excluded

    if "editorial_notes" in override:
        updated["editorial_notes"] = override["editorial_notes"]
    elif override.get("reason"):
        notes = list(updated.get("editorial_notes", []))
        if override["reason"] not in notes:
            notes.append(override["reason"])
        updated["editorial_notes"] = notes

    abilities = updated.get("ability_range") or ["intermediate"]
    updated["typical_customer"] = (
        f"{abilities[0].replace('_', ' ').title()} to "
        f"{abilities[-1].replace('_', ' ').title()} surfer seeking a "
        f"{updated['detailed_category'].lower()}."
    )
    if updated["public_family"] != previous_family or updated["detailed_category"] != previous_category:
        updated["reviewed_date"] = "2026-07-17"
        updated["reviewed_by"] = "QUIVRR"
    return updated


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def validate(records: list[dict]) -> dict:
    required = ["public_family", "detailed_category", "primary_fin_setup", "official_url", "board_dna"]
    errors = []
    ids = [record["canonical_model_id"] for record in records]
    keys = [record["canonical_key"] for record in records]
    if len(records) != 431:
        errors.append(f"Expected 431 models, found {len(records)}")
    if len(set(ids)) != len(ids):
        errors.append("Duplicate canonical model IDs")
    if len(set(keys)) != len(keys):
        errors.append("Duplicate canonical keys")
    for record in records:
        for field in required:
            if not record.get(field):
                errors.append(f"{record['canonical_key']}: missing {field}")
        if record.get("public_family") not in PUBLIC_LABELS:
            errors.append(f"{record['canonical_key']}: invalid public family")
        if not str(record.get("official_url", "")).startswith("https://"):
            errors.append(f"{record['canonical_key']}: invalid official URL")
    manufacturers = Counter(record["manufacturer"] for record in records)
    families = Counter(record["public_family"] for record in records)
    return {
        "schema_version": 1,
        "validated_at_utc": utc_now(),
        "valid": not errors,
        "errors": errors,
        "model_count": len(records),
        "manufacturer_count": len(manufacturers),
        "public_family_count": len(families),
        "explicit_public_families": sum(bool(record.get("public_family")) for record in records),
        "detailed_categories": sum(bool(record.get("detailed_category")) for record in records),
        "fin_configurations": sum(bool(record.get("primary_fin_setup")) for record in records),
        "manufacturer_urls": sum(bool(record.get("official_url")) for record in records),
        "board_dna_records": sum(bool(record.get("board_dna")) for record in records),
        "live_verified_models": sum(record["official_evidence"]["live_verified"] for record in records),
        "identity_matched_models": sum(record["official_evidence"]["identity_match"] for record in records),
        "review_required_models": sum(record["review_required"] for record in records),
        "classification_changes": sum(record["classification_changed"] for record in records),
        "unresolved_intent_conflicts": sum(record["unresolved_intent_conflict"] for record in records),
        "by_manufacturer": dict(sorted(manufacturers.items())),
        "by_public_family": dict(sorted(families.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 1 Quivrr Board Intelligence master matrix")
    parser.add_argument("--refresh-official", action="store_true", help="Refresh evidence from current official manufacturer websites")
    args = parser.parse_args()

    override_payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    overrides = {int(row["canonical_model_id"]): row for row in override_payload["overrides"]}
    review_paths = [REVIEW_ROOT / filename for filename in MANUFACTURER_FILES.values()]
    if not args.refresh_official and all(path.exists() for path in review_paths):
        records = []
        for path in review_paths:
            for record in json.loads(path.read_text(encoding="utf-8"))["models"]:
                records.append(apply_review_override(record, overrides.get(int(record["canonical_model_id"]), {})))
    else:
        dna = json.loads(DNA_PATH.read_text(encoding="utf-8"))["models"]
        expert_rows = json.loads(EXPERT_PATH.read_text(encoding="utf-8"))["boards"]
        experts = {int(row["boardModelId"]): row for row in expert_rows if row.get("boardModelId") is not None}
        evidence = OfficialEvidence(args.refresh_official)
        records = []
        for board in dna:
            model_id = int(board["canonical_model_id"])
            override = overrides.get(model_id, {})
            if override and (key(override["brand"]) != key(board["brand"]) or key(override["model"]) != key(board["model"])):
                raise ValueError(f"Editorial override identity mismatch for {model_id}")
            records.append(record_for(board, experts.get(model_id, {}), override, evidence.fetch(board)))


    records.sort(key=lambda row: (row["manufacturer"].lower(), row["model"].lower(), row["canonical_model_id"]))
    by_manufacturer = defaultdict(list)
    for record in records:
        by_manufacturer[record["manufacturer"]].append(record)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    for manufacturer, filename in MANUFACTURER_FILES.items():
        payload = {
            "schema_version": 1,
            "manufacturer": manufacturer,
            "authority": "Current official manufacturer website",
            "reviewed_date": "2026-07-17",
            "reviewed_by": "QUIVRR",
            "model_count": len(by_manufacturer[manufacturer]),
            "models": by_manufacturer[manufacturer],
        }
        (REVIEW_ROOT / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    validation = validate(records)
    existing_generated_at = None
    if not args.refresh_official and MASTER_PATH.exists():
        existing_generated_at = json.loads(MASTER_PATH.read_text(encoding="utf-8")).get("generated_at_utc")
    master = {
        "schema_version": 2,
        "authority": "QUIVRR editorial review of current official manufacturer websites",
        "generated_at_utc": existing_generated_at or utc_now(),
        "phase": "Phase 1 editorial knowledge only; not yet consumed by runtime applications",
        "model_count": len(records),
        "manufacturer_count": len(by_manufacturer),
        "public_families": list(PUBLIC_LABELS),
        "models": records,
    }
    MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MASTER_PATH.write_text(json.dumps(master, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    (AUDIT_ROOT / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")

    write_csv(AUDIT_ROOT / "manufacturer_summary.csv", ["manufacturer", "model_count", "live_verified", "review_required"], [
        {
            "manufacturer": manufacturer,
            "model_count": len(rows),
            "live_verified": sum(row["official_evidence"]["live_verified"] for row in rows),
            "review_required": sum(row["review_required"] for row in rows),
        }
        for manufacturer, rows in sorted(by_manufacturer.items())
    ])
    write_csv(AUDIT_ROOT / "family_summary.csv", ["public_family", "model_count"], [
        {"public_family": family, "model_count": count}
        for family, count in sorted(Counter(row["public_family"] for row in records).items())
    ])
    write_csv(AUDIT_ROOT / "detailed_category_summary.csv", ["detailed_category", "model_count"], [
        {"detailed_category": category, "model_count": count}
        for category, count in sorted(Counter(row["detailed_category"] for row in records).items())
    ])
    write_csv(AUDIT_ROOT / "fin_configuration_summary.csv", ["primary_fin_setup", "model_count"], [
        {"primary_fin_setup": setup, "model_count": count}
        for setup, count in sorted(Counter(row["primary_fin_setup"] for row in records).items())
    ])
    write_csv(AUDIT_ROOT / "classification_changes.csv", [
        "canonical_model_id", "manufacturer", "model", "previous_public_family", "public_family",
        "previous_detailed_category", "detailed_category", "confidence", "review_required",
    ], [{field: row[field] for field in [
        "canonical_model_id", "manufacturer", "model", "previous_public_family", "public_family",
        "previous_detailed_category", "detailed_category", "confidence", "review_required",
    ]} for row in records if row["classification_changed"]])
    write_csv(AUDIT_ROOT / "low_confidence_models.csv", [
        "canonical_model_id", "manufacturer", "model", "official_url", "retrieval_method", "http_status", "identity_match", "confidence",
    ], [{
        "canonical_model_id": row["canonical_model_id"],
        "manufacturer": row["manufacturer"],
        "model": row["model"],
        "official_url": row["official_url"],
        "retrieval_method": row["official_evidence"]["retrieval_method"],
        "http_status": row["official_evidence"]["http_status"],
        "identity_match": row["official_evidence"]["identity_match"],
        "confidence": row["confidence"],
    } for row in records if row["review_required"]])
    write_csv(AUDIT_ROOT / "manufacturer_intent_conflicts.csv", [
        "canonical_model_id", "manufacturer", "model", "public_family", "manufacturer_intent_signals",
        "unresolved_intent_conflict", "official_url",
    ], [{
        "canonical_model_id": row["canonical_model_id"],
        "manufacturer": row["manufacturer"],
        "model": row["model"],
        "public_family": row["public_family"],
        "manufacturer_intent_signals": "|".join(row["manufacturer_intent_signals"]),
        "unresolved_intent_conflict": row["unresolved_intent_conflict"],
        "official_url": row["official_url"],
    } for row in records if row["manufacturer_intent_signals"] and row["public_family"] not in row["manufacturer_intent_signals"]])

    print(json.dumps(validation, indent=2))
    return 0 if validation["valid"] and validation["manufacturer_count"] == 17 and validation["public_family_count"] == 7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
