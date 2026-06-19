from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re

import requests


SOURCE = Path("app/knowledge/generated/canonical_board_profiles.json")
API_BASE = "https://quivrr-backend-api.azurewebsites.net"
SUPPORTED_BRANDS = {
    "Album", "Channel Islands", "Chemistry Surfboards", "Chilli", "Christenson", "DHD",
    "DMS Surfboards", "Firewire", "Haydenshapes", "JS Industries", "Lost", "Misfit Shapes",
    "Pukas", "Pyzel", "Rusty", "Sharp Eye", "Simon Anderson",
}


def clean_text(value: str | None) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta_descriptions: list[str] = []
        self.json_ld: list[str] = []
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = {name.lower(): value for name, value in attrs}
        if tag.lower() == "meta" and attributes.get("content"):
            name = (attributes.get("name") or attributes.get("property") or "").lower()
            if name in {"description", "og:description", "twitter:description"}:
                self.meta_descriptions.append(attributes["content"])
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
        description = value.get("description")
        item_type = str(value.get("@type") or "").lower()
        if description and (not item_type or any(token in item_type for token in ["product", "webpage"])):
            output.append(str(description))
        for child in value.values():
            output.extend(json_descriptions(child))
    elif isinstance(value, list):
        for child in value:
            output.extend(json_descriptions(child))
    return output


def extract_description(page_html: str) -> str | None:
    parser = MetadataParser()
    parser.feed(page_html)
    candidates = []
    for raw in parser.json_ld:
        try:
            candidates.extend(json_descriptions(json.loads(raw)))
        except json.JSONDecodeError:
            continue
    candidates.extend(parser.meta_descriptions)
    cleaned = [clean_text(value) for value in candidates]
    cleaned = [value for value in cleaned if len(value) >= 80]
    return max(cleaned, key=len) if cleaned else None


def fetch_description(row: dict) -> dict:
    url = row.get("official_product_url") or row.get("source")
    if not str(url or "").startswith(("http://", "https://")):
        return {"status": "missing_source_url", "description": None}
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "QuivrrCatalogue/1.0 (+manufacturer catalogue description audit)"},
        )
        response.raise_for_status()
        description = extract_description(response.text)
        return {"status": "found" if description else "missing_description", "description": description}
    except requests.RequestException as exc:
        return {"status": "fetch_failed", "description": None, "error": str(exc)[:240]}


def load_canonical_ids() -> dict[tuple[str, str], int]:
    brands = requests.get(f"{API_BASE}/api/brands", timeout=30).json()
    output = {}
    for brand in brands:
        brand_name = brand["brandName"]
        models = requests.get(f"{API_BASE}/api/models/{brand['brandId']}", timeout=30).json()
        for model in models:
            output[(key(brand_name), key(model["modelName"]))] = int(model["modelId"])
    return output


def reject_generic_descriptions(rows: list[dict], results: dict[int, dict]) -> None:
    by_description: dict[str, set[tuple[str, str]]] = {}
    for index, result in results.items():
        description = clean_text(result.get("description"))
        if description:
            by_description.setdefault(description, set()).add((key(rows[index].get("brand")), key(rows[index].get("model"))))
    generic = {description for description, models in by_description.items() if len(models) >= 3}
    for result in results.values():
        if clean_text(result.get("description")) in generic:
            result["description"] = None
            result["status"] = "generic_description_rejected"


def build_report(rows: list[dict], results: dict[int, dict], canonical_ids: dict) -> dict:
    by_brand = {}
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault((row.get("brand"), key(row.get("model"))), []).append((index, row))
    for (brand, _), variants in groups.items():
        index, row = variants[0]
        brand = row.get("brand")
        if brand not in SUPPORTED_BRANDS:
            continue
        variant_results = [results.get(i, {}) for i, _ in variants]
        result = next((item for item in variant_results if item.get("description")), variant_results[0] if variant_results else {})
        existing = max((clean_text(item.get("description")) for _, item in variants), key=len, default="")
        scraped = max((clean_text(item.get("description")) for item in variant_results), key=len, default="")
        board_model_id = canonical_ids.get((key(brand), key(row.get("model"))))
        item = by_brand.setdefault(brand, {
            "modelsFound": 0, "modelsWithDescription": 0, "modelsMissingDescription": 0,
            "modelsLinkedToBoardModelId": 0, "modelsNotLinked": 0, "descriptionsAddedByDryRun": 0,
            "fetchFailures": 0, "sampleDescriptions": [],
        })
        item["modelsFound"] += 1
        if existing or scraped:
            item["modelsWithDescription"] += 1
        else:
            item["modelsMissingDescription"] += 1
        if board_model_id:
            item["modelsLinkedToBoardModelId"] += 1
        else:
            item["modelsNotLinked"] += 1
        if not existing and scraped:
            item["descriptionsAddedByDryRun"] += 1
        if variant_results and all(item.get("status") == "fetch_failed" for item in variant_results):
            item["fetchFailures"] += 1
        if (existing or scraped) and len(item["sampleDescriptions"]) < 2:
            item["sampleDescriptions"].append({
                "model": row.get("model"),
                "boardModelId": board_model_id,
                "sourceUrl": row.get("official_product_url") or row.get("source"),
                "description": (existing or scraped)[:360],
            })
    return {
        "mode": "dry_run",
        "sourceType": "manufacturer",
        "retailerFallbackUsed": False,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "brands": dict(sorted(by_brand.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run manufacturer description enrichment for Bodhi")
    parser.add_argument("--apply", action="store_true", help="Update the generated canonical profile JSON; never writes SQL")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    canonical_ids = load_canonical_ids()
    missing = [(index, row) for index, row in enumerate(rows)
               if row.get("brand") in SUPPORTED_BRANDS and not clean_text(row.get("description"))]
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_description, row): index for index, row in missing}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    reject_generic_descriptions(rows, results)

    report = build_report(rows, results, canonical_ids)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.apply:
        now = datetime.now(timezone.utc).isoformat()
        for index, row in enumerate(rows):
            row["board_model_id"] = canonical_ids.get((key(row.get("brand")), key(row.get("model"))))
            result = results.get(index, {})
            if not clean_text(row.get("description")) and result.get("description"):
                row["description"] = result["description"]
            if clean_text(row.get("description")):
                row["description_source_type"] = "manufacturer"
                row["description_source_url"] = row.get("official_product_url") or row.get("source")
                row["description_last_scraped_utc"] = now
        SOURCE.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        report["mode"] = "apply_json_only"

    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
