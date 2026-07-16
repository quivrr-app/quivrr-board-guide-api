import json
from pathlib import Path


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
        "firewire::great-white-twin": ("groveller", "Small Wave Performance Twin", "Twin"),
        "firewire::taylor-jensen-twinzer": ("mid_length", "Performance Mid Length", "Twinzer"),
    }
    for canonical_key, (family, category, fin) in expected.items():
        assert models[canonical_key]["public_family"] == family
        assert models[canonical_key]["detailed_category"] == category
        if fin:
            assert models[canonical_key]["primary_fin_setup"] == fin


def test_phase_one_outputs_do_not_replace_runtime_sources():
    payload = json.loads(MASTER.read_text(encoding="utf-8"))
    assert "not yet consumed by runtime applications" in payload["phase"]
    validation = json.loads((AUDITS / "validation_report.json").read_text(encoding="utf-8"))
    assert validation["valid"] is True
    assert validation["model_count"] == 431
    assert validation["manufacturer_count"] == 17
    assert validation["public_family_count"] == 7
