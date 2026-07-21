from app.board_dna import find_board_dna
from app.board_expert_matrix import find_matrix_board
from app.board_master import board_master_indexes, category_key, find_master_board, load_board_master
from app.board_taxonomy import find_taxonomy


EXPECTED = {
    ("Firewire", "Great White Twin"): ("fish", "Performance Fish", "Twin"),
    ("Pyzel", "Ghost"): ("performance_shortboard", "High Performance Shortboard", "Thruster"),
    ("Pyzel", "Phantom"): ("daily_driver", "Performance Daily Driver", "Thruster"),
    ("Pyzel", "Gremlin"): ("groveller", "Performance Softboard Groveller", "5 Fin"),
    ("Lost", "El Patron"): ("performance_shortboard", "Large-Rider High Performance Shortboard", "Thruster"),
    ("Lost", "RNF 96"): ("fish", "Performance Fish", "Twin"),
    ("Channel Islands", "goldie"): ("step_up", "Reef and Barrel Step Up", "Thruster"),
    ("Album", "Moonstone"): ("mid_length", "Performance Mid Length", "Twin"),
    ("DHD", "MF Twin"): ("performance_shortboard", "Alternative Performance Twin", "Twin"),
    ("Pyzel", "Happy Twin"): ("groveller", "Groveller", "Thruster"),
    ("Pyzel", "Tiger Twin"): ("groveller", "Small Wave Performance Twin", "Twin"),
    ("Firewire", "Seaside"): ("fish", "Performance Fish", "Twin"),
    ("Firewire", "Seaside and Beyond"): ("fish", "Performance Fish", "Twin"),
    ("Firewire", "Taylor Jensen Twinzer"): ("mid_length", "Performance Mid Length", "Twinzer"),
}


def test_all_458_master_records_load_into_unique_runtime_indexes():
    assert load_board_master()["model_count"] == 458
    by_id, _ = board_master_indexes()
    assert len(by_id) == 458


def test_acceptance_classifications_are_consistent_across_runtime_consumers():
    for identity, (family, category, fin) in EXPECTED.items():
        master = find_master_board(*identity)
        dna = find_board_dna(*identity)
        taxonomy = find_taxonomy(*identity)
        expert = find_matrix_board(*identity)
        assert master is not None, identity
        assert dna is not None, identity
        assert taxonomy is not None, identity
        assert expert is not None, identity
        assert master["public_family"] == family
        assert master["detailed_category"] == category
        assert master["primary_fin_setup"] == fin
        assert dna["public_family"] == family
        assert dna["primary_category"] == category_key(category)
        assert taxonomy["public_family"] == family
        assert taxonomy["primary_category"] == category_key(category)
        assert expert["publicFamily"] == family
        assert expert["detailedCategory"] == category
        assert fin in expert["finSetup"]


def test_family_and_fin_setup_remain_independent():
    mf_twin = find_master_board("DHD", "MF Twin")
    happy_twin = find_master_board("Pyzel", "Happy Twin")
    assert mf_twin["primary_fin_setup"] == "Twin"
    assert mf_twin["public_family"] == "performance_shortboard"
    assert happy_twin["alternative_fin_setup"] == ["Twin"]
    assert happy_twin["public_family"] == "groveller"


def test_excluded_lanes_are_not_reintroduced_by_legacy_matrix_data():
    ghost = find_matrix_board("Pyzel", "Ghost")
    assert "daily_driver" in ghost["excludedLanes"]
    assert "daily_driver" not in ghost["boardLanes"]
    assert ghost["boardMasterAuthority"] == "quivrr_board_master_matrix_v2"
