from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from app.board_dna import (
    dna_similarity,
    explain_dna_fit,
    find_board_dna,
    find_board_dna_by_id,
    load_board_dna,
    resolve_dna_brief,
    score_dna_fit,
)
from app.models import RiderProfile


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {"fish", "groveller", "daily_driver", "performance_shortboard", "step_up", "mid_length", "longboard"}


def _models():
    return load_board_dna()["models"]


def _average(rows, section, metric):
    return sum(row[section][metric] for row in rows) / len(rows)


def test_board_dna_is_complete_unique_and_governed():
    rows = _models()
    assert len(rows) == 431
    assert len({row["canonical_model_id"] for row in rows}) == 431
    assert len({row["brand"] for row in rows}) == 17
    assert {row["public_family"] for row in rows} == FAMILIES
    for row in rows:
        assert row["public_family"] in FAMILIES
        assert row["evidence"]["source_method"]
        assert row["evidence"]["physical_design_confidence"] in {"high", "medium", "low"}
        for section in ("behaviour", "conditions", "rider_fit"):
            assert all(isinstance(value, int) and 1 <= value <= 10 for value in row[section].values())


def test_explicit_family_assertions():
    expected = {
        ("Lost", "El Patron"): "performance_shortboard",
        ("Christenson", "Carrera"): "step_up",
        ("Christenson", "Fish"): "fish",
        ("Christenson", "Acid Phish"): "fish",
        ("Christenson", "Osprey"): "mid_length",
        ("Firewire", "Seaside"): "fish",
        ("Pyzel", "Ghost"): "performance_shortboard",
        ("Pyzel", "Phantom"): "daily_driver",
        ("Pyzel", "Gremlin"): "groveller",
    }
    for identity, family in expected.items():
        assert find_board_dna(*identity)["public_family"] == family
    assert find_board_dna("Christenson", "OP4")["public_family"] in {"performance_shortboard", "step_up"}


def test_ghost_is_hard_excluded_from_daily_driver_and_valid_for_performance_shortboard():
    ghost = find_board_dna("Pyzel", "Ghost")
    daily = score_dna_fit(ghost, RiderProfile(ability="Advanced"), {"public_family": "daily_driver"})
    performance = score_dna_fit(ghost, RiderProfile(ability="Advanced"), {"public_family": "performance_shortboard"})
    assert daily["valid"] is False
    assert performance["valid"] is True


def test_board_master_v2_is_final_editorial_authority():
    master = json.loads(
        (ROOT / "app/knowledge/curated/quivrr_board_master_matrix_v2.json").read_text(encoding="utf-8")
    )
    assert master["model_count"] == 431
    for authoritative in master["models"]:
        board = find_board_dna_by_id(authoritative["canonical_model_id"])
        assert board is not None
        assert board["brand"].casefold() == authoritative["manufacturer"].casefold()
        assert board["model"].casefold() == authoritative["model"].casefold()
        assert board["public_family"] == authoritative["public_family"]


def test_family_behaviour_is_materially_differentiated():
    rows = _models()
    family = lambda name: [row for row in rows if row["public_family"] == name]
    assert _average(family("performance_shortboard"), "behaviour", "sensitivity") > _average(family("daily_driver"), "behaviour", "sensitivity")
    assert _average(family("step_up"), "conditions", "powerful_waves") > _average(family("daily_driver"), "conditions", "powerful_waves")
    assert _average(family("groveller"), "conditions", "weak_waves") > _average(family("step_up"), "conditions", "weak_waves")
    assert _average(family("mid_length"), "behaviour", "glide") > _average(family("performance_shortboard"), "behaviour", "glide")


def test_every_metric_has_catalogue_distribution():
    rows = _models()
    for section in ("behaviour", "conditions", "rider_fit"):
        for metric in rows[0][section]:
            assert len({row[section][metric] for row in rows}) >= 5, f"{section}.{metric} is clustered"


def test_identical_behaviour_vectors_do_not_override_manufacturer_identity():
    moonstone = find_board_dna("Album", "Moonstone")
    black_baron = find_board_dna("JS Industries", "Black Baron")
    assert moonstone["behaviour"] == black_baron["behaviour"]
    assert moonstone["public_family"] == "mid_length"
    assert black_baron["public_family"] == "fish"


def test_source_generation_is_deterministic_before_timestamp_wrapping():
    from scripts.generate_board_dna_v1 import build

    assert build() == build()


def test_alias_lookup_similarity_and_fit_are_deterministic():
    seaside = find_board_dna("Firewire", "Seaside")
    ghost = find_board_dna("Pyzel", "Ghost")
    assert find_board_dna_by_id(seaside["canonical_model_id"]) == seaside
    assert dna_similarity(seaside, seaside) == 100
    assert 0 <= dna_similarity(seaside, ghost) < 100
    profile = RiderProfile(ability="Advanced", preferred_board_type="fish", desired_feel="fast and loose", wave_type="reef")
    brief = resolve_dna_brief("I want a fast and loose fish with more hold for a Bali reef", profile)
    result = score_dna_fit(seaside, profile, brief)
    assert result["valid"] is True
    assert result["score"] > 0
    explanation = explain_dna_fit(seaside, profile, brief)
    assert "trade-off" in explanation.lower()


def test_relationship_graph_v3_is_complete_and_resolved():
    graph = json.loads((ROOT / "app/knowledge/generated/board_relationship_graph_v3.json").read_text(encoding="utf-8"))
    assert graph["schemaVersion"] == 3
    assert graph["boardCount"] == 431 == len(graph["boards"])
    ids = {row["boardModelId"] for row in graph["boards"]}
    for row in graph["boards"]:
        assert len(row["relationships"]) == 14
        for edges in row["relationships"].values():
            for edge in edges:
                assert edge["canonical_model_id"] in ids
                assert edge["canonical_model_id"] != row["boardModelId"]
                assert 0 <= edge["similarity"] <= 100
                assert edge["dna_differences"]


def test_generation_audits_expose_review_queue():
    audit = json.loads((ROOT / "app/knowledge/audits/board_dna_audit.json").read_text(encoding="utf-8"))
    distribution = json.loads((ROOT / "app/knowledge/audits/board_dna_distribution.json").read_text(encoding="utf-8"))
    assert audit["model_count"] == 431
    assert sum(audit["by_public_family"].values()) == 431
    assert distribution["model_count"] == 431
    assert (ROOT / "app/knowledge/audits/board_dna_review_required.csv").exists()
    family_review = json.loads((ROOT / "app/knowledge/audits/public_family_review_v2.json").read_text(encoding="utf-8"))
    assert family_review["model_count"] == 431
    assert sum(family_review["proposed_family_counts"].values()) == 431
    assert len(family_review["records"]) == 431


def test_active_brief_inherits_family_region_and_stock_requirement():
    profile = RiderProfile(preferred_board_type="fish", region="ID", ability="Advanced", target_volume_litres=28.6)
    first = resolve_dna_brief("The Sampler is a hybrid shorty, not a fish. Show me a proper fish.", profile)
    second = resolve_dna_brief("OK, what is in stock in Indo?", profile, first)
    assert second["public_family"] == "fish"
    assert second["region"] == "ID"
    assert second["stock_required"] is True
