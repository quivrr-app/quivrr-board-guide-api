import unittest

from app.surf_domain import load_surf_domain_knowledge


class SurfDomainKnowledgePackTests(unittest.TestCase):
    def test_authoritative_pack_loads_immutable_and_complete(self):
        knowledge = load_surf_domain_knowledge()
        self.assertEqual(knowledge.pack_id, "bodhi_surf_knowledge_pack_v1")
        self.assertEqual(knowledge.version, "1.0.0")
        self.assertEqual(len(knowledge.documents), 20)
        self.assertIn("STAGE_1_TRUE_BEGINNER", knowledge.stage_matrix["rules"])
        with self.assertRaises(TypeError):
            knowledge.documents["x"] = "no"


if __name__ == "__main__":
    unittest.main()
