import csv
import json
import unittest

from scripts import audit_board_intelligence_sources as audit


class BoardIntelligenceSourceAuditTests(unittest.TestCase):
    def test_audit_is_model_level_global_and_reproducible(self):
        self.assertEqual(audit.main(), 0)
        paths = [
            audit.AUDIT_DIR / "board_intelligence_source_audit.json",
            audit.AUDIT_DIR / "board_intelligence_matrix_gap_report.csv",
            audit.AUDIT_DIR / "brand_metadata_coverage.csv",
            audit.AUDIT_DIR / "board_intelligence_priority_models.csv",
        ]
        first = {path: path.read_bytes() for path in paths}

        self.assertEqual(audit.main(), 0)
        self.assertEqual(first, {path: path.read_bytes() for path in paths})

        summary = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(summary["distinctModels"], 513)
        self.assertEqual(summary["canonicalProfileRows"], 573)
        self.assertEqual(summary["constructionVariantRowsCollapsed"], 60)
        self.assertIn("global canonical board intelligence", summary["scope"])
        reconciliation = summary["descriptionCoverageReconciliation"]
        self.assertEqual(reconciliation["modelsWithDescriptionAfterVariantMerge"], 503)
        self.assertEqual(reconciliation["modelsMissingDescriptionAfterVariantMerge"], 10)
        self.assertEqual(reconciliation["legacyVariantSelectionFalseMissing"], ["Lost Puddle Jumper HP"])

        with paths[1].open(encoding="utf-8", newline="") as handle:
            models = list(csv.DictReader(handle))
        with paths[2].open(encoding="utf-8", newline="") as handle:
            brands = list(csv.DictReader(handle))
        with paths[3].open(encoding="utf-8", newline="") as handle:
            priority = list(csv.DictReader(handle))

        self.assertEqual(len(models), 513)
        self.assertEqual(len(brands), 17)
        self.assertEqual(len(priority), 100)
        self.assertNotIn("regionCode", models[0])

    def test_legacy_default_ability_is_not_manufacturer_evidence(self):
        blob = "A versatile surfboard with plenty of speed."
        self.assertFalse(audit.has_pattern(blob, "ability"))


if __name__ == "__main__":
    unittest.main()
