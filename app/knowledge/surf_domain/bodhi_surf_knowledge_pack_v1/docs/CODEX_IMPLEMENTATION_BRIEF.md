# Codex Implementation Brief — Import Bodhi Surf Knowledge Pack

Integrate this pack into the current production Board Guide API without replacing canonical or inventory data.

## Work

1. Add JSON schema validation at application startup and in tests.
2. Build a typed loader with immutable cached objects.
3. Connect surfer-stage assessment to the existing conversation router.
4. Apply stage-family exclusions before ranking and inventory lookup.
5. Add design-trait thresholds to candidate filtering.
6. Replace volume-first logic with the ordered selection flow.
7. Add guidance-only responses where no safe supported model exists.
8. Use the premium-catalogue wording as controlled content.
9. Apply topic-pivot and correction rules before prior-context continuation.
10. Preserve existing active-board, exact BoardSizeId, profile proposal and regional inventory flows.
11. Add focused tests from `tests/regression_scenarios.json`.
12. Run all regular API/frontend tests and existing recognition/intelligence audits.
13. Commit, push and deploy to production.
14. Run production smoke tests for true beginner, progressing beginner, topic pivot, specific unsuitable board and advanced regression.

## Non-negotiable

- Do not invent foamie products.
- Do not hard-code model-specific claims from this general pack.
- Do not let availability override suitability.
- Do not let saved litres override a contradictory current beginner scenario.
- Do not allow the LLM to bypass deterministic exclusions.
