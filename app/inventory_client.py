from __future__ import annotations

from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import os
import re
import time
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.parse import urlparse

import requests

from app.models import RetailerOffer, RiderProfile, SuggestedBoard
from app.rider_fit import recommend_rider_fit
from app.volume_engine_v2 import build_target_volume_context


API_BASE = os.getenv("QUIVRR_INVENTORY_API_URL", "https://quivrr-backend-api.azurewebsites.net").rstrip("/")
REGION_ALIASES = {
    "AUSTRALIA": "AU",
    "EUROPE": "EU",
    "UNITED STATES": "US",
    "USA": "US",
    "INDONESIA": "ID",
}
BRAND_ALIASES = {"CHEMISTRY": "CHEMISTRY SURFBOARDS", "DMS": "DMS SURFBOARDS"}
QUIVRR_REGION_PATHS = {"AU": "australia", "EU": "europe", "US": "united-states", "ID": "indonesia"}


def fit_score_label(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    score = confidence * 100 if confidence <= 1 else confidence
    if score >= 85:
        return "high"
    if score >= 75:
        return "medium"
    return "limited"


def inventory_source_label(manufacturer_count: int, retailer_count: int) -> str | None:
    if manufacturer_count and retailer_count:
        return "manufacturer_direct_and_retailer"
    if manufacturer_count:
        return "manufacturer_direct"
    if retailer_count:
        return "retailer"
    return None


def quivrr_search_url(board: SuggestedBoard, region: str, size: dict | None = None) -> str:
    size = size or {}
    params = {
        "region": region,
        "brand": board.brand,
        "model": board.model,
        "construction": size.get("construction"),
        "volume": size.get("volumeLitres"),
        "boardSizeId": size.get("boardSizeId"),
    }
    if size.get("boardSizeId"):
        params["autoSearch"] = "1"
    return f"https://quivrr.app/{QUIVRR_REGION_PATHS[region]}?{urlencode({key: value for key, value in params.items() if value not in (None, '')})}"


def quivrr_model_search_url(board: SuggestedBoard, region: str) -> str:
    params = {
        "brand": board.brand,
        "model": board.model,
    }
    return f"https://quivrr.app/{QUIVRR_REGION_PATHS[region]}/?{urlencode(params)}"


def normalise_region(value: str | None) -> str | None:
    region = (value or "").strip().upper()
    region = REGION_ALIASES.get(region, region)
    return region if region in {"AU", "EU", "US", "ID"} else None


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
        return deduped[:8]
    selected = []
    for tolerance in (1.0, 2.0, 3.0):
        for row in deduped:
            if row["_distance"] <= tolerance and row not in selected:
                selected.append(row)
        if len(selected) >= 2:
            break
    return selected[:2]


def _volume_compatibility_label(volume: float | None, target_context) -> tuple[str, float | None]:
    if volume is None or target_context is None or target_context.target_litres is None:
        return "acceptable_with_tradeoff", None
    delta = abs(float(volume) - float(target_context.target_litres))
    if target_context.minimum_litres is not None and target_context.maximum_litres is not None:
        if volume < target_context.minimum_litres or volume > target_context.maximum_litres:
            return "incompatible", delta
    if delta <= 0.5:
        return "excellent", delta
    if delta <= 1.5:
        return "good", delta
    if delta <= 2.0:
        return "acceptable_with_tradeoff", delta
    return "incompatible", delta


def _select_best_size(sizes: list[dict], target_context) -> dict | None:
    if target_context is None or target_context.target_litres is None:
        return sizes[0] if sizes else None
    ranked = []
    for size in sizes:
        compatibility, delta = _volume_compatibility_label(size.get("volumeLitres"), target_context)
        rank = {"excellent": 0, "good": 1, "acceptable_with_tradeoff": 2, "incompatible": 3}[compatibility]
        ranked.append((rank, delta if delta is not None else 99, size))
    ranked.sort(key=lambda item: (item[0], item[1], item[2].get("boardSizeId") or 0))
    for rank, _, size in ranked:
        if rank <= 1:
            return size
    return None


def _summarise_stock(payloads: list[dict], region: str, construction_preference: str | None = None) -> dict:
    rows = []
    direct_rows = {}
    retailer_rows = {}
    exact_retailer_rows = {}
    close_retailer_rows = {}
    checked = False
    offers = {}
    for payload in payloads:
        if normalise_region(payload.get("regionCode")) != region:
            continue
        checked = True
        for offer in (payload.get("offerIntelligence") or {}).get("offers") or payload.get("offers") or []:
            if normalise_region(offer.get("region")) != region or not offer.get("inStock"):
                continue
            if construction_preference and not construction_matches_preference(
                offer.get("construction"), construction_preference
            ):
                continue
            offer_key = offer.get("offerId") or offer.get("productUrl")
            if offer_key:
                offers[offer_key] = RetailerOffer.model_validate(offer)
        direct = [row for row in payload.get("directManufacturerMatches", []) if row.get("isAvailable") is not False]
        exact_retailers = [row for row in payload.get("exactRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"}]
        close_retailers = [row for row in payload.get("closeRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"}]
        retailers = [*exact_retailers, *close_retailers]
        if construction_preference:
            direct = [row for row in direct if construction_matches_preference(
                " ".join(filter(None, [row.get("construction"), row.get("title")])), construction_preference
            )]
            retailers = [row for row in retailers if construction_matches_preference(
                " ".join(filter(None, [row.get("construction"), row.get("title")])), construction_preference
            )]
            exact_retailers = [row for row in exact_retailers if row in retailers]
            close_retailers = [row for row in close_retailers if row in retailers]
        for row in direct:
            key = row.get("manufacturerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            direct_rows[key] = row
        for row in retailers:
            key = row.get("retailerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            retailer_rows[key] = row
        for row in exact_retailers:
            key = row.get("retailerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            exact_retailer_rows[key] = row
        for row in close_retailers:
            key = row.get("retailerInventoryId") or row.get("productUrl") or repr(sorted(row.items()))
            close_retailer_rows[key] = row
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
    if direct_count and retailer_count:
        availability_status = "manufacturer_and_retailer_stock"
    elif direct_count:
        availability_status = "manufacturer_stock"
    elif retailer_count:
        availability_status = "retailer_stock"
    else:
        availability_status = "not_found" if checked else "not_checked"
    exact_size_count = direct_count + len(exact_retailer_rows)
    return {
        "availability_checked": checked,
        "availability_status": availability_status,
        "available_count": direct_count + retailer_count,
        "manufacturer_direct_count": direct_count,
        "retailer_count": retailer_count,
        "inventory_match_count": direct_count + retailer_count,
        "exact_size_inventory_count": exact_size_count,
        "close_size_inventory_count": len(close_retailer_rows),
        "exact_size_stock": exact_size_count > 0,
        "model_level_stock": (direct_count + retailer_count) > 0,
        "inventory_source": inventory_source_label(direct_count, retailer_count),
        "example_live_source_url": urls[0] if urls else None,
        "price_range": price_range,
        "offers": list(offers.values()),
    }


def enrich_suggestions_with_inventory(
    suggestions: list[SuggestedBoard],
    profile: RiderProfile,
    get_json: Callable[[str], object] = _get_json,
) -> list[SuggestedBoard]:
    region = normalise_region(profile.region)
    fit = recommend_rider_fit(profile)
    target_context = build_target_volume_context(profile)
    target = target_context.target_litres if target_context and target_context.target_litres is not None else profile.target_volume_litres
    if target is None and fit is not None:
        target = (fit.volume_low + fit.volume_high) / 2
    if not region:
        return [
            suggestion.model_copy(update={
                "fit_score": round((suggestion.confidence * 100) if suggestion.confidence <= 1 else suggestion.confidence),
                "fit_confidence": fit_score_label(suggestion.confidence),
                "availability_checked": False,
                "availability_status": "not_checked",
                "inventory_source": None,
                "inventory_match_count": 0,
                "region_code": None,
            })
            for suggestion in suggestions
        ]

    enriched = []
    for suggestion in suggestions:
        stock = {
            "available_count": 0,
            "manufacturer_direct_count": 0,
            "retailer_count": 0,
            "availability_checked": False,
            "availability_status": "unknown",
            "inventory_source": None,
            "inventory_match_count": 0,
            "exact_size_inventory_count": 0,
            "close_size_inventory_count": 0,
            "exact_size_stock": False,
            "model_level_stock": False,
            "example_live_source_url": None,
            "price_range": None,
            "offers": [],
        }
        selected_size = None
        selected_size_data = None
        try:
            model_id = suggestion.board_model_id
            if model_id is None:
                brand_id = _find_brand_id(suggestion.brand, get_json)
                model_id = _find_model_id(brand_id, suggestion.model, get_json) if brand_id else None
            sizes = _candidate_sizes(model_id, target, get_json, profile.construction_preference) if model_id else []
            selected_size_data = _select_best_size(sizes, target_context) if sizes else None
            if selected_size_data is not None:
                sizes = [selected_size_data]
            else:
                sizes = []
            payloads = [
                get_json("/api/search?" + urlencode({"boardSizeId": size["boardSizeId"], "region": region}))
                for size in sizes
            ]
            stock = _summarise_stock(payloads, region, profile.construction_preference)
            if sizes:
                selected_size_data = sizes[0]
                selected_size = sizes[0].get("label")
        except (requests.RequestException, TypeError, ValueError, KeyError):
            # Availability is optional context. Failure must produce zero stock, never invented stock.
            pass

        source_url = stock.get("example_live_source_url")
        fit_score = round((suggestion.confidence * 100) if suggestion.confidence <= 1 else suggestion.confidence)
        volume_compatibility, volume_delta = _volume_compatibility_label(
            selected_size_data.get("volumeLitres") if selected_size_data else None,
            target_context,
        )
        if selected_size_data is None:
            volume_compatibility = "incompatible"
        size_reason = None
        if selected_size_data is not None:
            litres = selected_size_data.get("volumeLitres")
            if volume_delta is not None and target_context and target_context.target_litres is not None:
                size_reason = (
                    f"I selected the {selected_size} because it stays {volume_delta:g}L from your {target_context.target_litres:g}L target."
                    if volume_delta > 0
                    else f"I selected the {selected_size} because it lands right on your {target_context.target_litres:g}L target."
                )
        enriched.append(suggestion.model_copy(update={
            **stock,
            "fit_score": fit_score,
            "fit_confidence": fit_score_label(suggestion.confidence),
            "suggested_size": selected_size,
            "region": region,
            "region_code": region,
            "quivrr_search_url": quivrr_search_url(suggestion, region, selected_size_data),
            "source_product_url": source_url,
            "board_size_id": selected_size_data.get("boardSizeId") if selected_size_data else None,
            "selected_construction": selected_size_data.get("construction") if selected_size_data else None,
            "selected_volume_litres": selected_size_data.get("volumeLitres") if selected_size_data else None,
            "volume_delta_litres": volume_delta,
            "selected_size_reason": size_reason,
            "volume_compatibility": volume_compatibility,
            "offers": stock.get("offers", []),
        }))

    # Exact fit first, then actual regional availability, manufacturer direct, retailer, confidence.
    enriched.sort(
        key=lambda board: (
            board.volume_compatibility in {"excellent", "good"},
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
        exact_rows.extend(("Manufacturer Direct", row, size) for row in payload.get("directManufacturerMatches", []) if row.get("isAvailable") is not False)
        exact_rows.extend((row.get("retailerName") or "Retailer", row, size) for row in payload.get("exactRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"})
        close_rows.extend((row.get("retailerName") or "Retailer", row, size) for row in payload.get("closeRetailerMatches", []) if row.get("stockStatus") not in {"out_of_stock", "unavailable"})

    selected_rows, exact = (exact_rows, True) if exact_rows else (close_rows, False)
    output, seen = [], set()
    for source_name, row, size in selected_rows:
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
            "fit_score": round((board.confidence * 100) if board.confidence <= 1 else board.confidence),
            "fit_confidence": fit_score_label(board.confidence),
            "available_count": 1,
            "manufacturer_direct_count": 1 if source_name == "Manufacturer Direct" else 0,
            "retailer_count": 0 if source_name == "Manufacturer Direct" else 1,
            "availability_checked": True,
            "availability_status": "available",
            "inventory_source": "manufacturer_direct" if source_name == "Manufacturer Direct" else "retailer",
            "inventory_match_count": 1,
            "example_live_source_url": url, "source_product_url": url,
            "quivrr_search_url": quivrr_search_url(board, region, size),
            "board_size_id": size.get("boardSizeId"), "selected_construction": size.get("construction"),
            "selected_volume_litres": size.get("volumeLitres"),
            "price_range": price, "region": region, "region_code": region,
            "offers": [RetailerOffer.model_validate(row["offer"])] if row.get("offer") else [],
            "suggested_size": " | ".join(filter(None, [row.get("length"), f"{row.get('volumeLitres'):g}L" if row.get("volumeLitres") is not None else None, row.get("construction")])),
        }))
        if len(output) >= 8:
            break
    return output, exact
