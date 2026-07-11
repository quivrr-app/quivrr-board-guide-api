from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from app.inventory_client import normalise_region
from app.models import RiderProfile


PROFILE_API_URL = os.getenv(
    "QUIVRR_PROFILE_API_URL",
    "https://quivrr-backend-api.azurewebsites.net/api/my-quivrr/profile",
).rstrip("/")

SURF_FREQUENCY_MAP = {
    "a few times a year": 0.1,
    "monthly": 0.25,
    "fortnightly": 0.5,
    "weekly": 1.0,
    "several times a week": 3.0,
    "daily if there are waves": 5.0,
}


@dataclass(frozen=True)
class AuthenticatedProfileContext:
    authenticated: bool = False
    profile_loaded: bool = False
    invalid_token: bool = False
    user_id: str | None = None
    profile: RiderProfile | None = None


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _normalise_frequency(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return SURF_FREQUENCY_MAP.get(str(value).strip().lower())


def _profile_from_backend(payload: dict) -> RiderProfile | None:
    if not isinstance(payload, dict):
        return None

    user = payload.get("user") or {}
    profile = payload.get("profile") or {}
    region = normalise_region(user.get("homeRegion") or profile.get("homeCountry"))

    rider = RiderProfile(
        display_name=user.get("displayName"),
        region=region,
        height_cm=profile.get("heightCm"),
        weight_kg=profile.get("weightKg"),
        ability=profile.get("ability"),
        current_volume_litres=profile.get("currentVolumeLitres"),
        preferred_brands=list(profile.get("preferredBrands") or []),
        current_board=profile.get("currentBoard"),
        goal=profile.get("surfingGoal"),
        wave_type=profile.get("waveType"),
        wave_size=profile.get("waveSize"),
        surf_frequency_per_week=_normalise_frequency(profile.get("surfFrequency")),
        home_break=profile.get("homeBreak"),
        home_country=profile.get("homeCountry"),
        profile_sources=["account_profile"] if user.get("displayName") or profile else [],
    )
    preferred_min = profile.get("preferredVolumeMinLitres")
    preferred_max = profile.get("preferredVolumeMaxLitres")
    if preferred_min is not None and preferred_max is not None:
        rider.target_volume_litres = round((float(preferred_min) + float(preferred_max)) / 2, 2)
    elif preferred_min is not None:
        rider.target_volume_litres = float(preferred_min)
    rider.field_provenance = {
        field: "account_profile"
        for field, value in rider.model_dump().items()
        if field not in {"profile_sources", "profile_conflicts", "field_provenance"} and value not in (None, "", [], {})
    }
    return rider


def load_authenticated_profile_context(
    authorization: str | None,
    correlation_id: str | None = None,
    timeout_seconds: float = 8.0,
) -> AuthenticatedProfileContext:
    token = _bearer_token(authorization)
    if not token:
        return AuthenticatedProfileContext()

    headers = {"Authorization": f"Bearer {token}"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    try:
        response = requests.get(PROFILE_API_URL, headers=headers, timeout=timeout_seconds)
    except requests.RequestException:
        return AuthenticatedProfileContext(authenticated=True, profile_loaded=False)

    if response.status_code in {401, 403}:
        return AuthenticatedProfileContext(authenticated=False, profile_loaded=False, invalid_token=True)
    if not response.ok:
        return AuthenticatedProfileContext(authenticated=True, profile_loaded=False)

    payload = response.json()
    return AuthenticatedProfileContext(
        authenticated=True,
        profile_loaded=True,
        invalid_token=False,
        user_id=((payload.get("user") or {}).get("userId")),
        profile=_profile_from_backend(payload),
    )
