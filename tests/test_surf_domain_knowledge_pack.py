import unittest
from types import SimpleNamespace
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import surf_domain
from app.surf_domain import load_surf_domain_knowledge
from app.surfer_stage import STAGE_2, STAGE_3, stage_allows_board


class SurfDomainKnowledgePackTests(unittest.TestCase):
    def test_authoritative_pack_loads_immutable_and_complete(self):
        knowledge = load_surf_domain_knowledge()
        self.assertEqual(knowledge.pack_id, "bodhi_surf_knowledge_pack_v1")
        self.assertEqual(knowledge.version, "1.0.0")
        self.assertEqual(len(knowledge.documents), 20)
        self.assertIn("STAGE_1_TRUE_BEGINNER", knowledge.stage_matrix["rules"])
        with self.assertRaises(TypeError):
            knowledge.documents["x"] = "no"

    def test_stage_matrix_keeps_stage_three_conditionals_separate_from_exclusions(self):
        performance_daily = SimpleNamespace(
            authoritative_public_family="Performance Daily Driver",
            detailed_category=None, category=None, skill_fit="Intermediate to Advanced",
            board_model_id=None, brand="", model="",
        )
        forgiving_daily = SimpleNamespace(
            authoritative_public_family="Daily Driver", detailed_category=None,
            category=None, skill_fit="Intermediate", board_model_id=None, brand="", model="",
        )
        self.assertFalse(stage_allows_board(STAGE_2, performance_daily))
        self.assertFalse(stage_allows_board(STAGE_3, performance_daily))
        self.assertFalse(stage_allows_board(STAGE_3, forgiving_daily))

        governed_daily = SimpleNamespace(
            authoritative_public_family="Daily Driver", detailed_category=None,
            category=None, skill_fit="Intermediate", board_model_id=8115,
            brand="Album", model="Bullet",
        )
        self.assertTrue(stage_allows_board(STAGE_3, governed_daily))

    def test_malformed_required_pack_file_fails_loader_startup(self):
        with TemporaryDirectory() as temporary_directory:
            copied_pack = Path(temporary_directory) / "pack"
            copytree(surf_domain.PACK_ROOT, copied_pack)
            metadata = copied_pack / "knowledge" / "00_pack_metadata.json"
            metadata.write_text('{"version":"tampered"}\n', encoding="utf-8")
            load_surf_domain_knowledge.cache_clear()
            try:
                with patch.object(surf_domain, "PACK_ROOT", copied_pack):
                    with self.assertRaisesRegex(RuntimeError, "validation failed"):
                        load_surf_domain_knowledge()
            finally:
                load_surf_domain_knowledge.cache_clear()


if __name__ == "__main__":
    unittest.main()
