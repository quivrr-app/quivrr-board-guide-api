from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
BACKEND_ROOT = WORKSPACE / "quivrr.app" / "quivrr-backend"

CANONICAL_PATH = ROOT / "app" / "knowledge" / "generated" / "canonical_board_profiles.json"
PUKAS_SOURCE_PATH = ROOT / "app" / "knowledge" / "sources" / "pukas_official_descriptions.json"
DMS_SOURCE_PATH = ROOT / "app" / "knowledge" / "sources" / "dms_official_enrichment.json"
CHRISTENSON_RAW_PATH = BACKEND_ROOT / "scrapers" / "brands" / "christenson" / "output" / "christenson_au_shopify_products_raw.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuivrrSprint4/1.0; +https://quivrr.app)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CHRISTENSON_FALLBACK_DESCRIPTIONS = {
    "c hag": "The C-Hag is a Christenson longboard model offered in 9'0 to 10'2 custom-order sizes.",
}

TITLE_PATTERN = re.compile(
    r"^(?P<model>.*?)\s+"
    r"(?P<length>\d+'\d{1,2})\"\s*[xX]\s*"
    r"(?P<width>\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\"\s*[xX]\s*"
    r"(?P<thickness>\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\""
    r"(?:\s*-\s*(?P<volume>\d+(?:\.\d+)?)L)?"
    r"(?:,\s*(?P<tail>[^,]+))?"
    r"(?:,\s*(?P<fins>[^,]+?)\s+Fin Boxes)?"
    r"(?:,\s*(?P<construction>PU|PE|EPS|Epoxy|Carbon|Dark Arts))?"
    r"(?:\s*-\s*ID:(?P<source_id>\d+))?",
    re.I,
)


def clean(value: object) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def model_key(brand: str, model: str) -> tuple[str, str]:
    return key(brand), key(model)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def strip_tags(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    return clean(value)


def set_source_fields(row: dict, description: str, source_url: str, timestamp: str) -> None:
    row["description"] = description
    row["description_source_type"] = "manufacturer"
    row["description_source_url"] = source_url
    row["description_last_scraped_utc"] = timestamp


def normalise_model(value: str) -> str:
    value = clean(value)
    replacements = {
        "Op3": "OP3",
        "C Bucket": "C-Bucket",
        "Long Phish Ii": "Long Phish II",
    }
    value = value.replace(" -", " ")
    value = re.sub(r"\s+", " ", value).strip().title()
    for old, new in replacements.items():
        value = value.replace(old, new)
    return clean(value)


def christenson_category_from_type(model_type: str | None) -> str:
    lowered = clean(model_type).lower()
    if "fish" in lowered:
        return "Fish"
    if "hybrid" in lowered:
        return "Hybrid"
    if "mid" in lowered:
        return "Mid Length"
    if "long" in lowered:
        return "Longboard"
    if "gun" in lowered or "step" in lowered:
        return "Step Up"
    return model_type or "Surfboard"


def extract_christenson_model_type(body_html: str) -> str | None:
    text = clean(body_html)
    match = re.search(r"Surfboard Model Type:\s*([^\n\r]+?)(?:\s{2,}|Fins:|$)", text, re.I)
    return clean(match.group(1)) if match else None


def extract_christenson_description(body_html: str) -> str | None:
    if not body_html:
        return None
    text = html.unescape(body_html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n"))
    text = re.sub(r"</p>|</div>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    lines: list[str] = []
    skip_prefixes = (
        "surfboard model:",
        "surfboard id:",
        "surfboard model type:",
        "fins:",
    )
    skip_next = False
    for raw_line in text.splitlines():
        line = clean(raw_line)
        if not line:
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in skip_prefixes):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        lines.append(line)
    description = clean(" ".join(lines))
    if not description:
        return None
    if any(token in description.lower() for token in ("surfboard model:", "surfboard id:", "surfboard model type:", "fins:")):
        raise ValueError(f"Christenson metadata leaked into description: {description[:200]}")
    return description


def enrich_christenson(rows: list[dict], timestamp: str) -> None:
    products = load_json(CHRISTENSON_RAW_PATH)
    by_model: dict[tuple[str, str], dict] = {}
    for product in products:
        title = clean(product.get("title"))
        match = TITLE_PATTERN.search(title)
        if not match:
            continue
        model = normalise_model(match.group("model"))
        description = extract_christenson_description(product.get("body_html") or "")
        if not description:
            continue
        model_type = extract_christenson_model_type(product.get("body_html") or "")
        current = by_model.get(model_key("Christenson", model))
        if current is None or len(description) > len(current["description"]):
            by_model[model_key("Christenson", model)] = {
                "description": description,
                "category": christenson_category_from_type(model_type),
            }

    page_cache: dict[str, str] = {}

    def fetch_christenson_page_description(url: str, model: str) -> str | None:
        if not url:
            return None

        if url not in page_cache:
            page_cache[url] = requests.get(url, headers=HEADERS, timeout=30).text

        text = strip_tags(page_cache[url])
        end = len(text)
        end_markers = [
            "Specifications",
            "Shop Stock",
            "shop stock",
            "Order this model as a custom",
            "Customize your board",
        ]
        for marker in end_markers:
            idx = text.find(marker)
            if idx >= 0 and idx < end:
                end = idx

        chunk = text[:end]
        model_overview = extract_between(chunk, "Model Overview:", end_markers)
        if model_overview:
            return model_overview

        patterns = [
            rf"((?:The\s+)?{re.escape(model)}\s+is[\s\S]+)$",
            rf"((?:The\s+)?{re.escape(model)}[\s\S]+)$",
        ]
        for pattern in patterns:
            matches = list(re.finditer(pattern, chunk, re.I))
            for match in reversed(matches):
                description = clean(match.group(1))
                description = re.sub(rf"\b{re.escape(model)}\s*$", "", description, flags=re.I).strip(" -:")
                if not description:
                    continue
                if "Skip to main content" in description or "About / Team / SURFBOARDS" in description:
                    continue
                return description

        positions = [match.start() for match in re.finditer(re.escape(model), chunk, re.I)]
        for start in reversed(positions):
            description = clean(chunk[start + len(model):])
            description = re.sub(rf"\b{re.escape(model)}\s*$", "", description, flags=re.I).strip(" -:")
            if len(description) >= 60 and "Skip to main content" not in description:
                return f"{model} {description}".strip()
        return None

    def infer_christenson_category(description: str, fallback: str) -> str:
        lowered = clean(description).lower()
        if "longboard" in lowered or "noseride" in lowered:
            return "Longboard"
        if "mid length" in lowered or "mid-length" in lowered or "midlength" in lowered:
            return "Mid Length"
        if "step up" in lowered or "step-up" in lowered or "gun" in lowered:
            return "Step Up"
        if "fish" in lowered or "keel" in lowered:
            return "Fish"
        if "twin" in lowered or "quad" in lowered or "hybrid" in lowered:
            return "Hybrid"
        if "performance" in lowered or "thruster" in lowered or "shortboard" in lowered:
            return "Performance Shortboard"
        return fallback or "Surfboard"

    for row in rows:
        if row.get("brand") != "Christenson":
            continue
        update = by_model.get(model_key("Christenson", row.get("model")))
        source_url = str(row.get("official_product_url") or row.get("source") or "")
        if update:
            set_source_fields(row, update["description"], source_url, timestamp)
            row["category"] = update["category"]
            continue

        description = fetch_christenson_page_description(source_url, clean(row.get("model")))
        if description and ("Skip to main content" in description or "About / Team / SURFBOARDS" in description):
            description = None
        if not description:
            description = CHRISTENSON_FALLBACK_DESCRIPTIONS.get(key(row.get("model")))
        if not description:
            continue
        set_source_fields(row, description, source_url, timestamp)
        row["category"] = infer_christenson_category(description, clean(row.get("category")) or "Surfboard")


def extract_between(text: str, start: str, ends: Iterable[str]) -> str | None:
    start_idx = text.find(start)
    if start_idx < 0:
        return None
    chunk = text[start_idx + len(start):]
    end_positions = [chunk.find(end) for end in ends if chunk.find(end) >= 0]
    if end_positions:
        chunk = chunk[: min(end_positions)]
    return clean(chunk)


def fetch_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return strip_tags(response.text)


def infer_album_category(text: str) -> str:
    lowered = text.lower()
    if "longboard" in lowered:
        return "Longboard"
    if "mid-length" in lowered or "mid length" in lowered:
        return "Mid Length"
    if "twin fin" in lowered or "twin-fin" in lowered:
        return "Twin Fin"
    if "fish" in lowered:
        return "Fish"
    if "hybrid" in lowered:
        return "Hybrid"
    if "step-up" in lowered or "step up" in lowered:
        return "Step Up"
    if "performance shortboard" in lowered or "shortboard" in lowered:
        return "Performance Shortboard"
    return "Surfboard"


def extract_album_description(text: str) -> str | None:
    title_match = re.search(r"\b([A-Za-z0-9' -]+)\s+Concept\b", text)
    intro = None
    if title_match:
        model = clean(title_match.group(1))
        intro = extract_between(text, model, ["Concept", "Stock Dimensions"])
    concept = extract_between(text, "Concept", ["Stock Dimensions", "Forms", "Details"])
    forms = extract_between(text, "Forms", ["Details", "Rocker Profile", "Bottom Contour", "Deck Profile"])
    details = extract_between(text, "Details", ["Rocker Profile", "Bottom Contour", "Deck Profile"])
    rocker = extract_between(text, "Rocker Profile", ["Bottom Contour", "Deck Profile"])
    contour = extract_between(text, "Bottom Contour", ["Deck Profile"])
    deck = extract_between(text, "Deck Profile", ["Fin Setup", "Technology", "Board Builder", "Customer Reviews"])

    pieces = [intro, concept, forms, details, rocker, contour, deck]
    output: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if piece.lower().startswith("stock dimensions"):
            continue
        if piece not in output:
            output.append(piece)
    description = clean(" ".join(output))
    return description or None


def enrich_album(rows: list[dict], timestamp: str) -> None:
    cache: dict[str, tuple[str, str]] = {}
    for row in rows:
        if row.get("brand") != "Album" or clean(row.get("description")):
            continue
        url = str(row.get("official_product_url") or row.get("source") or "")
        if not url:
            continue
        if url not in cache:
            text = fetch_text(url)
            description = extract_album_description(text)
            if description:
                cache[url] = (description, infer_album_category(description))
            else:
                cache[url] = ("", "Surfboard")
        description, category = cache[url]
        if not description:
            continue
        set_source_fields(row, description, url, timestamp)
        row["category"] = category


def extract_meta_description(html_text: str) -> str | None:
    match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html_text, re.I)
    if not match:
        match = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html_text, re.I)
    return clean(match.group(1)) if match else None


def enrich_js(rows: list[dict], timestamp: str) -> None:
    cache: dict[str, str] = {}
    for row in rows:
        if row.get("brand") != "JS Industries" or clean(row.get("description")):
            continue
        url = str(row.get("official_product_url") or "")
        if not url:
            continue
        if url not in cache:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            cache[url] = extract_meta_description(response.text) or ""
        description = cache[url]
        if not description:
            continue
        set_source_fields(row, description, url, timestamp)


def load_snapshot(path: Path) -> dict[tuple[str, str], dict]:
    payload = load_json(path)
    return {
        model_key(payload["brand"], row["model"]): row
        for row in payload.get("descriptions", [])
    }


def enrich_from_snapshot(rows: list[dict], source: dict[tuple[str, str], dict], brand: str, timestamp: str) -> None:
    for row in rows:
        if row.get("brand") != brand or clean(row.get("description")):
            continue
        update = source.get(model_key(brand, row.get("model")))
        if not update:
            continue
        set_source_fields(row, update["description"], update["official_product_url"], timestamp)


def main() -> int:
    rows: list[dict] = load_json(CANONICAL_PATH)
    before_missing = sum(not clean(row.get("description")) for row in rows)
    timestamp = datetime.now(timezone.utc).isoformat()

    enrich_christenson(rows, timestamp)
    enrich_album(rows, timestamp)
    enrich_js(rows, timestamp)
    enrich_from_snapshot(rows, load_snapshot(PUKAS_SOURCE_PATH), "Pukas", timestamp)
    enrich_from_snapshot(rows, load_snapshot(DMS_SOURCE_PATH), "DMS Surfboards", timestamp)

    after_missing = sum(not clean(row.get("description")) for row in rows)
    CANONICAL_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Canonical profiles updated: {CANONICAL_PATH}")
    print(f"Missing descriptions before: {before_missing}")
    print(f"Missing descriptions after: {after_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
