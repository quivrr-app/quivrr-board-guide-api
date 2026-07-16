import json
from pathlib import Path

from scripts.build_board_master_matrix_v2 import apply_review_override


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "app" / "knowledge" / "curated" / "quivrr_board_master_matrix_v2.json"
REVIEWS = ROOT / "manufacturer_reviews"
AUDITS = ROOT / "app" / "knowledge" / "audits" / "board_master_matrix_v2"


def load_master():
    return json.loads(MASTER.read_text(encoding="utf-8"))["models"]


def test_master_matrix_has_complete_unique_governed_coverage():
    models = load_master()
    assert len(models) == 431
    assert len({model["canonical_model_id"] for model in models}) == 431
    assert len({model["canonical_key"] for model in models}) == 431
    assert len({model["manufacturer"] for model in models}) == 17
    assert {model["public_family"] for model in models} == {
        "fish", "groveller", "daily_driver", "performance_shortboard", "step_up", "mid_length", "longboard"
    }
    for model in models:
        assert model["official_url"].startswith("https://")
        assert model["detailed_category"]
        assert model["primary_fin_setup"]
        assert model["board_dna"]
        assert len(model["board_dna"]["behaviour"]) == 14


def test_every_manufacturer_review_matches_the_master_matrix():
    models = load_master()
    review_models = []
    for path in sorted(REVIEWS.glob("*_v1.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["authority"] == "Current official manufacturer website"
        assert payload["model_count"] == len(payload["models"])
        review_models.extend(payload["models"])
    assert len(review_models) == 431
    assert {row["canonical_model_id"] for row in review_models} == {row["canonical_model_id"] for row in models}


def test_identified_editorial_regressions_are_corrected():
    models = {model["canonical_key"]: model for model in load_master()}
    expected = {
        "lost::el-patron": ("performance_shortboard", "Large-Rider High Performance Shortboard", "Thruster"),
        "lost::big-rig-driver": ("performance_shortboard", "Large-Rider High Performance Shortboard", "Thruster"),
        "lost::driver-3-0-grom": ("performance_shortboard", "Competition HPSB", "Thruster"),
        "lost::rnf-96": ("fish", "Performance Fish", None),
        "pyzel::ghost-swallow": ("performance_shortboard", "Quality-Wave High Performance Shortboard", "Thruster"),
        "pyzel::power-tiger": ("performance_shortboard", "Quality-Wave Performance Shortboard", "Thruster"),
        "pyzel::power-tiger-grom": ("performance_shortboard", "Youth Quality-Wave Performance Shortboard", "Thruster"),
        "firewire::great-white-twin": ("fish", "Performance Fish", "Twin"),
        "firewire::taylor-jensen-twinzer": ("mid_length", "Performance Mid Length", "Twinzer"),
    }
    for canonical_key, (family, category, fin) in expected.items():
        assert models[canonical_key]["public_family"] == family
        assert models[canonical_key]["detailed_category"] == category
        if fin:
            assert models[canonical_key]["primary_fin_setup"] == fin

    great_white = models["firewire::great-white-twin"]
    assert great_white["alternative_fin_setup"] == ["Twin + Trailer"]
    assert "fish" in great_white["recommendation_lanes"]
    assert "performance_fish" in great_white["recommendation_lanes"]
    assert "fish" not in great_white["excluded_recommendation_lanes"]
    assert "performance_fish" not in great_white["excluded_recommendation_lanes"]


def test_deterministic_review_path_reapplies_editorial_overrides():
    record = {
        "canonical_model_id": 7965,
        "manufacturer": "Firewire",
        "model": "Great White Twin",
        "public_family": "groveller",
        "public_family_label": "Groveller",
        "detailed_category": "Small Wave Performance Twin",
        "board_type": "Groveller",
        "primary_fin_setup": "Twin",
        "alternative_fin_setup": [],
        "recommendation_lanes": ["performance_twin"],
        "excluded_recommendation_lanes": ["fish", "performance_fish"],
        "editorial_notes": ["stale"],
        "ability_range": ["intermediate", "advanced"],
        "previous_public_family": "groveller",
        "previous_detailed_category": "performance_twin",
    }
    override = {
        "canonical_model_id": 7965,
        "brand": "Firewire",
        "model": "Great White Twin",
        "public_family": "fish",
        "detailed_category": "Performance Fish",
        "board_type": "Fish",
        "primary_fin_setup": "Twin",
        "alternative_fin_setup": ["Twin + Trailer"],
        "editorial_notes": ["governed"],
    }
    updated = apply_review_override(record, override)
    assert updated["public_family"] == "fish"
    assert updated["detailed_category"] == "Performance Fish"
    assert updated["alternative_fin_setup"] == ["Twin + Trailer"]
    assert updated["editorial_notes"] == ["governed"]
    assert "fish" in updated["recommendation_lanes"]
    assert "performance_fish" not in updated["excluded_recommendation_lanes"]


def test_phase_one_outputs_do_not_replace_runtime_sources():
    payload = json.loads(MASTER.read_text(encoding="utf-8"))
    assert "not yet consumed by runtime applications" in payload["phase"]
    validation = json.loads((AUDITS / "validation_report.json").read_text(encoding="utf-8"))
    assert validation["valid"] is True
    assert validation["model_count"] == 431
    assert validation["manufacturer_count"] == 17
    assert validation["public_family_count"] == 7
