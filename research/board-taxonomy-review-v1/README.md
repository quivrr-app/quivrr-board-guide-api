# Quivrr Board Taxonomy Review v1

**Status:** Editorial review workspace only. Not approved for Bodhi, Quivrr Surf, Quivrr App, search or inventory runtime.

## Source authority

This review must use the current GitHub repositories and live generated data as the source authority. Uploaded architecture and source documents are not classification authority.

Primary inputs:

* `quivrr-app/quivrr-surf-frontend/seo-data/knowledge/board-reviews.json`
* `quivrr-app/quivrr-surf-frontend/seo-data/knowledge/review-search-index.json`
* `quivrr-app/quivrr-board-guide-api/app/knowledge/generated/board_expert_matrix.json`
* `quivrr-app/quivrr-board-guide-api/app/knowledge/generated/canonical_board_profiles.json`
* Current official manufacturer URLs retained in those running files

## Scope

The owner-review dataset must cover every currently published review model across all 17 governed manufacturers. Current production reports 425 qualified review models. Additional canonical candidates may be included separately, but they must not be mixed into the approved 425-model runtime set without an explicit status.

## Approval gate

No category, recommendation lane or relationship change may enter runtime until Nathan has reviewed the model-level results. Each row must support `approve`, `change` or `hold`, with reviewer notes.

## Required classification fields

Manufacturer, model, official source URL, existing category, proposed primary category, secondary categories, board family, design subtype, fin configuration, tail family, wave power, wave range, wave types, rider ability, paddle profile, forgiveness, performance profile, strengths, trade-offs, recommendation lanes, excluded lanes, manufacturer evidence, source confidence, change reason, review decision and review notes.

## Category principles

Dimensions and volume alone never determine category. A twin is not automatically a fish. A wide shortboard is not automatically a groveller. Stock availability may never promote a category-invalid board. The manufacturer description, design intent, outline, rocker, rails, bottom contours, tail, fin configuration, intended waves and rider level must be considered together.
