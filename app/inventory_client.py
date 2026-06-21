from __future__ import annotations

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import os
import re
import time
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
    for attempt in range(3):
        try:
            response = requests.get(f"{API_BASE}{path}", timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(0.35 * (attempt + 1))


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


CARBON_EPOXY_TERMS = (
    "carbon", "carbotune", "spinetek", "spine tek", "eps", "epoxy", "hyfi", "helium",
    "ibolic", "i bolic", "futureflex", "dark arts", "black sheep", "lightspeed", "lib tech",
    "varial", "thunderbolt", "xtr",
)


def construction_matches_preference(construction: str | None, preference: str | None) -> bool:
    if not preference:
        return True
    return any(term in _key(construction) for term in CARBON_EPOXY_TERMS)


def _candidate_sizes(model_id: int, target_volume: float | None, get_json: Callable[[str], object],
                     construction_preference: str | None = None) -> list[dict]:
    output = []
    for row in get_json(f"/api/constructions/{model_id}") or []:
        if not construction_matches_preference(row.get("construction"), construction_preference):
            continue
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


def _summarise_stock(payloads: list[dict], region: str, construction_preference: str | None = None) -> dict:
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
        if construction_preference:
            direct = [row for row in direct if construction_matches_preference(
                " ".join(filter(None, [row.get("construction"), row.get("title")])), construction_preference
            )]
            retailers = [row for row in retailers if construction_matches_preference(
                " ".join(filter(None, [row.get("construction"), row.get("title")])), construction_preference
            )]
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
            sizes = _candidate_sizes(model_id, target, get_json, profile.construction_preference) if model_id else []
            payloads = [
                get_json("/api/search?" + urlencode({"boardSizeId": size["boardSizeId"], "region": region}))
                for size in sizes
            ]
            stock = _summarise_stock(payloads, region, profile.construction_preference)
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


def locate_exact_board(
    board: SuggestedBoard,
    profile: RiderProfile,
    get_json: Callable[[str], object] = _get_json,
) -> tuple[list[SuggestedBoard], bool]:
    region = normalise_region(profile.region)
    if not region:
        return [], False
    model_id = board.board_model_id
    if model_id is None:
        brand_id = _find_brand_id(board.brand, get_json)
        model_id = _find_model_id(brand_id, board.model, get_json) if brand_id else None
    if model_id is None:
        return [], False

    requested_construction = _key(profile.requested_construction)
    requested_length = _key(profile.requested_length)
    target_volume = profile.target_volume_litres
    sizes = []
    for construction_row in get_json(f"/api/constructions/{model_id}") or []:
        construction = str(construction_row.get("construction") or "")
        if requested_construction and requested_construction not in _key(construction):
            continue
        for size in get_json(f"/api/sizes/{model_id}/{quote(construction, safe='')}") or []:
            if requested_length and _key(size.get("length")) != requested_length:
                continue
            try:
                volume_delta = abs(float(size.get("volumeLitres")) - target_volume) if target_volume is not None else 0
            except (TypeError, ValueError):
                volume_delta = 99
            if target_volume is not None and volume_delta > 1.0:
                continue
            sizes.append((volume_delta, size))
    sizes.sort(key=lambda item: (item[0], item[1].get("boardSizeId") or 0))

    exact_rows, close_rows = [], []
    for _, size in sizes[:4]:
        payload = get_json("/api/search?" + urlencode({"boardSizeId": size["boardSizeId"], "region": region}))
        if normalise_region(payload.get("regionCode")) != region:
            continue
        exact_rows.extend(("Manufacturer Direct", row) for row in payload.get("directManufacturerMatches", []) if row.get("isAvailable") is not False)
        exact_rows.extend((row.get("retailerName") or "Retailer", row) for row in payload.get("exactRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"})
        close_rows.extend((row.get("retailerName") or "Retailer", row) for row in payload.get("closeRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"})

    selected_rows, exact = (exact_rows, True) if exact_rows else (close_rows, False)
    output, seen = [], set()
    for source_name, row in selected_rows:
        url = row.get("productUrl")
        if not url or url in seen:
            continue
        seen.add(url)
        price = None
        if row.get("priceAmount") is not None and row.get("priceCurrency"):
            price = f"{float(row['priceAmount']):g} {row['priceCurrency']}"
        output.append(board.model_copy(update={
            "category": "Exact stock" if exact else "Close stock",
            "why_it_fits": f"{'Exact' if exact else 'Close'} verified {region} match from {source_name}",
            "available_count": 1,
            "manufacturer_direct_count": 1 if source_name == "Manufacturer Direct" else 0,
            "retailer_count": 0 if source_name == "Manufacturer Direct" else 1,
            "example_live_source_url": url, "price_range": price, "region": region,
            "suggested_size": " | ".join(filter(None, [row.get("length"), f"{row.get('volumeLitres'):g}L" if row.get("volumeLitres") is not None else None, row.get("construction")])),
        }))
        if len(output) >= 8:
            break
    return output, exact
