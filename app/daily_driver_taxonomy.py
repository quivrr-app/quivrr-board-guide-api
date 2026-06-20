from __future__ import annotations


PERFORMANCE_DAILY_DRIVERS = {
    ("pyzel", "phantom"),
    ("js industries", "xero gravity"),
    ("js industries", "monsta"),
    ("sharp eye", "inferno 72"),
    ("channel islands", "better everyday"),
    ("channel islands", "happy-everyday"),
    ("js industries", "golden child"),
    ("lost", "driver 2.0"),
    ("lost", "driver 3.0 round"),
    ("lost", "driver 3.0 squash"),
    ("lost", "rad ripper"),
}

FORGIVING_DAILY_DRIVERS = {
    ("firewire", "dominator 2.0"),
}

HYBRID_DAILY_DRIVERS = {
    ("haydenshapes", "hypto krypto"),
    ("chilli", "rare bird evo"),
    ("chilli", "rare bird evo tt"),
}

SMALL_WAVE_DAILY_DRIVERS = {
    ("lost", "rnf 96"),
}


def daily_driver_lane(brand: str | None, model: str | None) -> str | None:
    key = ((brand or "").strip().lower(), (model or "").strip().lower())
    for lane, boards in (
        ("performance_daily_driver", PERFORMANCE_DAILY_DRIVERS),
        ("forgiving_daily_driver", FORGIVING_DAILY_DRIVERS),
        ("hybrid_daily_driver", HYBRID_DAILY_DRIVERS),
        ("small_wave_daily_driver", SMALL_WAVE_DAILY_DRIVERS),
    ):
        if key in boards:
            return lane
    return None


def lane_label(lane: str | None) -> str | None:
    return lane.replace("_", " ").title() if lane else None
