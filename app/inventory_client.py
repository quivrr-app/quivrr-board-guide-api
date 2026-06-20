from __future__ import annotations

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import os
import re
from typing import Callable
from urllib.parse import quote, urlencode

import requests

from app.models import RiderProfile, SuggestedBoard
from app.rider_fit import recommend_rider_fit


API_BASE = os.getenv("QUIVRR_INVENTORY_API_URL", "https://quivrr-backend-api.azurewebsites.net").rstrip("/")
REGION_ALIASES = {"AUSTRALIA": "AU", "EUROPE": "EU", "INDONESIA": "ID"}
BRAND_ALIASES = {"CHEMISTRY": "CHEMISTRY SURFBOARDS", "DMS": "DMS SURFBOARDS"}


def normalise_region(value: str | None) -> str | None:
    region = (value or "").strip().upper()
    region = REGION_ALIASES.get(region, region)
    return region if region in {"AU", "EU", "ID"} else None


def _key(value: str | None) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return re.sub(r"\s+", " ", value)


@lru_cache(maxsize=1024)
def _get_json(path: str):
    response = requests.get(f"{API_BASE}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def _find_brand_id(brand: str, get_json: Callable[[str], object]) -> int | None:
    target = BRAND_ALIASES.get(brand.strip().upper(), brand.strip().upper())
    for row in get_json("/api/brands") or []:
        if row.get("brandName", "").strip().upper() == target:
            return int(row["brandId"])
    return None


def _find_model_id(brand_id: int, model: str, get_json: Callable[[str], object]) -> int | None:
    target = _key(model)
    matches = [row for row in get_json(f"/api/models/{brand_id}") or [] if _key(row.get("modelName")) == target]
    return int(matches[0]["modelId"]) if len(matches) == 1 else None


def _candidate_sizes(model_id: int, target_volume: float | None, get_json: Callable[[str], object]) -> list[dict]:
    output = []
    for row in get_json(f"/api/constructions/{model_id}") or []:
        construction = quote(str(row.get("construction") or ""), safe="")
        for size in get_json(f"/api/sizes/{model_id}/{construction}") or []:
            try:
                volume = float(size.get("volumeLitres"))
            except (TypeError, ValueError):
                continue
            output.append({**size, "_distance": abs(volume - target_volume) if target_volume is not None else 0})
    output.sort(key=lambda row: (row["_distance"], row.get("boardSizeId") or 0))
    seen = set()
    deduped = []
    for row in output:
        size_id = row.get("boardSizeId")
        if size_id in seen:
            continue
        seen.add(size_id)
        deduped.append(row)
    if target_volume is None:
        return deduped[:2]
    selected = []
    for tolerance in (1.0, 2.0, 3.0):
        for row in deduped:
            if row["_distance"] <= tolerance and row not in selected:
                selected.append(row)
        if len(selected) >= 2:
            break
    return selected[:2]


def _summarise_stock(payloads: list[dict], region: str) -> dict:
    rows = []
    direct_rows = {}
    retailer_rows = {}
    for payload in payloads:
        if normalise_region(payload.get("regionCode")) != region:
            continue
        direct = [row for row in payload.get("directManufacturerMatches", []) if row.get("isAvailable") is not False]
        retailers = [
            row for key in ("exactRetailerMatches", "closeRetailerMatches")
            for row in payload.get(key, []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"}
        ]
        for row in direct:
            key = row.get("manufacturerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            direct_rows[key] = row
        for row in retailers:
            key = row.get("retailerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            retailer_rows[key] = row
    rows.extend(direct_rows.values())
    rows.extend(retailer_rows.values())
    direct_count = len(direct_rows)
    retailer_count = len(retailer_rows)

    urls = [row.get("productUrl") for row in rows if row.get("productUrl")]
    prices = [float(row["priceAmount"]) for row in rows if row.get("priceAmount") is not None]
    currencies = {row.get("priceCurrency") for row in rows if row.get("priceCurrency")}
    price_range = None
    if prices and len(currencies) == 1:
        currency = next(iter(currencies))
        price_range = f"{min(prices):g}-{max(prices):g} {currency}" if min(prices) != max(prices) else f"{min(prices):g} {currency}"
    return {
        "available_count": direct_count + retailer_count,
        "manufacturer_direct_count": direct_count,
        "retailer_count": retailer_count,
        "example_live_source_url": urls[0] if urls else None,
        "price_range": price_range,
    }


def enrich_suggestions_with_inventory(
    suggestions: list[SuggestedBoard],
    profile: RiderProfile,
    get_json: Callable[[str], object] = _get_json,
) -> list[SuggestedBoard]:
    region = normalise_region(profile.region)
    fit = recommend_rider_fit(profile)
    target = profile.target_volume_litres
    if target is None and fit is not None:
        target = (fit.volume_low + fit.volume_high) / 2
    if not region:
        return suggestions

    enriched = []
    for suggestion in suggestions:
        stock = {"available_count": 0, "manufacturer_direct_count": 0, "retailer_count": 0,
                 "example_live_source_url": None, "price_range": None}
        selected_size = None
        try:
            model_id = suggestion.board_model_id
            if model_id is None:
                brand_id = _find_brand_id(suggestion.brand, get_json)
                model_id = _find_model_id(brand_id, suggestion.model, get_json) if brand_id else None
            sizes = _candidate_sizes(model_id, target, get_json) if model_id else []
            payloads = [
                get_json("/api/search?" + urlencode({"boardSizeId": size["boardSizeId"], "region": region}))
                for size in sizes
            ]
            stock = _summarise_stock(payloads, region)
            if sizes:
                selected_size = sizes[0].get("label")
        except (requests.RequestException, TypeError, ValueError, KeyError):
            # Availability is optional context. Failure must produce zero stock, never invented stock.
            pass

        enriched.append(suggestion.model_copy(update={**stock, "suggested_size": selected_size, "region": region}))

    # Exact fit first, then actual regional availability, manufacturer direct, retailer, confidence.
    enriched.sort(
        key=lambda board: (
            board.confidence,
            board.available_count > 0,
            board.manufacturer_direct_count > 0,
            board.retailer_count > 0,
        ),
        reverse=True,
    )
    return enriched


def enrich_suggestions_concurrently(
    suggestions: list[SuggestedBoard],
    profile: RiderProfile,
    get_json: Callable[[str], object] = _get_json,
    workers: int = 8,
) -> list[SuggestedBoard]:
    if len(suggestions) <= 1:
        return enrich_suggestions_with_inventory(suggestions, profile, get_json)

    def enrich_one(board: SuggestedBoard) -> SuggestedBoard:
        return enrich_suggestions_with_inventory([board], profile, get_json)[0]

    with ThreadPoolExecutor(max_workers=min(workers, len(suggestions))) as executor:
        enriched = list(executor.map(enrich_one, suggestions))
    enriched.sort(
        key=lambda board: (
            board.available_count > 0,
            board.confidence,
            board.manufacturer_direct_count > 0,
            board.retailer_count > 0,
        ),
        reverse=True,
    )
    return enriched
