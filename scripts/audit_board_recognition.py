"""Audit deterministic board-name recognition against the canonical catalogue."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.board_master import load_board_master
from app.board_resolver import BRAND_ALIASES, resolve_board


OUTPUT = ROOT / "app" / "knowledge" / "audits" / "board_recognition_audit.json"


def _brand_abbreviation(brand: str) -> str | None:
    return next((alias for alias, value in BRAND_ALIASES.items() if value == brand and alias != brand.lower()), None)


def main() -> int:
    failures, clarification_required, unresolved, total = [], [], [], 0
    match_types: dict[str, int] = {}
    explicit_total = explicit_resolved = alias_total = alias_resolved = 0
    for row in load_board_master()["models"]:
        forms = [
            (f"{row['manufacturer']} {row['model']}", True, "exact_brand_model"),
            (f"Tell me about {row['manufacturer']} {row['model']}", True, "natural_language_brand_model"),
            # A model-only request is allowed to ask for clarification when the
            # model name is shared or generic. It must never resolve incorrectly.
            (f"What is {row['model']} like", False, "model_only"),
        ]
        alias = _brand_abbreviation(row["manufacturer"])
        if alias:
            forms.append((f"{alias} {row['model']}", True, "brand_alias"))
        for form, must_resolve, form_kind in forms:
            total += 1
            if form_kind in {"exact_brand_model", "natural_language_brand_model"}:
                explicit_total += 1
            if form_kind == "brand_alias":
                alias_total += 1
            result = resolve_board(form)
            outcome = {"input": form, "expected": row["canonical_key"], "status": result.status,
                       "resolved": result.canonical_key, "alternatives": result.alternatives, "formKind": form_kind}
            if result.status == "resolved" and result.canonical_key == row["canonical_key"]:
                match_types[result.match_type or "unknown"] = match_types.get(result.match_type or "unknown", 0) + 1
                if form_kind in {"exact_brand_model", "natural_language_brand_model"}:
                    explicit_resolved += 1
                if form_kind == "brand_alias":
                    alias_resolved += 1
            elif result.status == "resolved":
                outcome["classification"] = "resolver_defect"
                failures.append(outcome)
            elif not must_resolve:
                outcome["classification"] = "genuine_ambiguity" if result.status == "ambiguous" else "expected_unsupported_form"
                clarification_required.append(outcome)
            else:
                outcome["classification"] = "resolver_defect"
                unresolved.append(outcome)
    hard_failures = [*failures, *unresolved]
    payload = {
        "auditVersion": "bodhi_board_recognition_v1",
        "canonicalModels": len(load_board_master()["models"]),
        "testCases": total,
        "resolved": total - len(hard_failures) - len(clarification_required),
        "recognitionRatePercent": round(100 * (total - len(hard_failures) - len(clarification_required)) / total, 2) if total else 0,
        "exactSupportedBrandAndModelRatePercent": round(100 * explicit_resolved / explicit_total, 2) if explicit_total else 0,
        "normalisedBrandAndModelRatePercent": round(100 * explicit_resolved / explicit_total, 2) if explicit_total else 0,
        "brandAliasRatePercent": round(100 * alias_resolved / alias_total, 2) if alias_total else 0,
        "explicitBrandAndModelForms": explicit_total,
        "brandAliasForms": alias_total,
        "matchTypes": match_types,
        "clarificationRequiredRequests": clarification_required,
        "unresolvedRequests": unresolved,
        "incorrectResolutions": failures,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Canonical models: {payload['canonicalModels']}")
    print(f"Recognition cases: {total}")
    print(f"Resolved: {payload['resolved']} ({payload['recognitionRatePercent']}%)")
    print(f"Model-only requests requiring clarification: {len(clarification_required)}")
    print(f"Incorrect or unresolved: {len(hard_failures)}")
    return 0 if not hard_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
