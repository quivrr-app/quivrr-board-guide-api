# Integration Guide

## Recommended location

Copy the `knowledge` directory into:

`quivrr-board-guide-api/app/knowledge/surf_domain/`

Do not overwrite current canonical board profiles, generated Board DNA, aliases, inventory clients or manufacturer facts.

## Load order

1. Canonical catalogue and model-specific official data.
2. Existing manual model overrides.
3. This general surf-domain policy pack.
4. Deterministic recommendation engine.
5. Inventory and price data.
6. Generated response prose.

General knowledge must not overwrite a verified manufacturer-specific fact. It should interpret that fact.

## Suggested runtime objects

Load and validate:

- surfer stages
- board families
- stage-family matrix
- design traits
- selection engine
- conversation policy
- response contracts
- premium catalogue positioning

Expose a single immutable `SurfDomainKnowledge` object to the router, stage assessor, candidate filter, ranker and response builder.

## Required engine outputs

The deterministic engine should produce:

- `resolved_surfer_stage`
- `stage_source`
- `allowed_families`
- `excluded_families`
- `candidate_rejections`
- `safe_candidate_ids`
- `effective_rider_context`
- `volume_policy_applied`
- `inventory_checked`
- `response_mode`

The language model may explain those outputs but must not change them.

## Versioning

Include the pack version in structured logs. Any future edit should increment the version and run the regression suite.
