# Bodhi Board Intelligence

## Architecture contract

Board identity, canonical catalogue data, manufacturer descriptions, classification, wave fit,
surfer-fit taxonomy, and equivalency are global. Inventory is regional. `AU`, `EU`, and `ID`
may change availability, price, currency, product URL, retailer, and manufacturer source, but must
not create different intelligence for the same canonical board model.

This Phase 2 audit is read-only. It does not alter recommendation behaviour, inventory, SQL,
scrapers, or Azure jobs.

## Board Intelligence Matrix

Each canonical brand-model identity should converge on this schema. Construction and size
variants belong beneath the identity; they must not multiply the model-level intelligence record.

| Group | Fields | Rules |
| --- | --- | --- |
| Identity | `brand`, `model`, `boardModelId`, `sourceUrl`, `sourceType`, `lastUpdatedUtc` | Canonical brand and model are global. Source URL must be a manufacturer source when manufacturer claims are recorded. |
| Description | `manufacturerDescription`, `shortDescription`, `descriptionConfidence`, `descriptionSource` | Preserve manufacturer meaning. A generated short description must be labelled as derived. |
| Category | `primaryCategory`, `secondaryCategories`, `manufacturerSeries`, `categoryConfidence`, `categorySource` | Allowed categories: `daily_driver`, `performance_shortboard`, `high_performance`, `groveller`, `fish`, `hybrid`, `step_up`, `mid_length`, `longboard`, `gun`, `softboard`, `foil`, `youth`. |
| Wave fit | `waveHeightMinFt`, `waveHeightMaxFt`, `waveTypes`, `wavePower`, `waveConfidence`, `waveSource` | Wave types: `beach_break`, `point_break`, `reef_break`, `wave_pool`. Power: `weak`, `average`, `powerful`. Do not infer a precise range from vague phrases. |
| Surfer fit | `abilityMin`, `abilityMax`, `surferProfiles`, `surferFitConfidence`, `surferFitSource` | Ability scale: `beginner`, `intermediate`, `advanced`, `expert`. A legacy default of Intermediate is not evidence. |
| Design | `outline`, `entryRocker`, `exitRocker`, `railType`, `tailShape`, `finSetup`, `constructionNotes`, `designConfidence`, `designSource` | Capture labelled manufacturer facts. Construction is not a separate model unless the manufacturer treats it as one. |
| Recommendation | `recommendationTags` | Allowed tags: `small_wave`, `daily_driver`, `one_board_quiver`, `high_performance`, `easy_paddling`, `high_wave_count`, `tube_riding`, `travel_board`, `speed_generation`, `hold_in_power`, `forgiving`, `loose`, `drivey`. |
| Equivalency | `similarBoards`, `alternativeBoards`, `replacesOrComparableTo`, `equivalencyConfidence` | Require explicit design evidence or a reviewed Quivrr relationship. Shared volume alone is insufficient. |
| Audit | `confidence`, `missingFields`, `extractionNotes`, `reviewedByQuivrr`, `reviewedAtUtc` | Missing data remains null. Review metadata must distinguish deterministic extraction from human curation. |

## Source hierarchy and confidence

Use sources in this order:

1. Structured metadata on the official manufacturer model page.
2. Manufacturer model description or manufacturer catalogue copy.
3. Quivrr-reviewed override with recorded rationale.
4. Deterministic extraction from sourced manufacturer prose.
5. Generated factual summary, clearly labelled and never treated as manufacturer wording.

Retailer descriptions are not canonical truth. Regional manufacturer-availability rows may help
locate an official source page, but their regional stock record is not itself the global
intelligence record.

Confidence is field-specific:

- `high`: explicit structured or clearly labelled manufacturer value.
- `medium`: unambiguous deterministic extraction from manufacturer prose.
- `low`: useful but incomplete narrative evidence; do not use it as a hard filter.
- `none`: no evidence. Leave the field unset.

An overall confidence must not hide a low-confidence wave range or surfer level. Recommendation
logic should inspect the relevant field confidence.

## Current knowledge sources

| Source | Role | Safe use | Important limitation |
| --- | --- | --- | --- |
| `canonical_board_profiles.json` | Global model, construction, size, URL, and manufacturer-description profiles | Canonical identity/sizes and sourced descriptions | 573 profile rows collapse to 513 model identities; many design facts remain prose |
| `board_intelligence_generated.json` | Derived deterministic recommendation metadata | Use with evidence and confidence | Legacy category fields and newer classifier fields coexist |
| `board_intelligence_audit.json` | Existing classification coverage report | Diagnostics | Does not report manufacturer metadata field coverage |
| `catalogue_boards.json` | Reserved SQL catalogue export | Do not use | Placeholder with zero boards |
| `board_intelligence_overrides.json` | Reviewed deterministic overrides | Use after review | Must remain small and sourced, not become a shadow catalogue |
| `board_intelligence.json` | Legacy curated seed | Use with explicit provenance | Older schema and limited coverage |
| `board_intelligence_classifier.py` | Deterministic text classifier | Conservative derived signals | Small vocabulary and three model overrides; cannot replace structured extraction |
| `generate_bodhi_board_intelligence.py` | Builds generated intelligence and classifier audit | Repeatable generation | Mixes legacy inference/defaults with the Phase 3 classifier shape |
| `scrape_manufacturer_board_descriptions.py` | Reads official manufacturer pages and enriches JSON | Manufacturer descriptions after dry-run review | Extracts page-level descriptions, not structured design scales or series taxonomy |
| `model_recommendation_engine.py` | Ranks controlled board candidates | Current recommendation input | Still scores legacy category/tag shapes and prose tokens |
| `inventory_client.py` | Adds read-only regional stock after model selection | Regional availability only | Inventory is optional and must never become board intelligence |
| `rider_fit.py` | Produces rider volume/category guidance | Deterministic rider-fit guidance | Does not yet consume the full intelligence matrix |
| `prompts.py` | Gives Bodhi controlled context and operating rules | Presentation and guardrails | Prompt wording cannot compensate for missing structured evidence |

## Phase 2 audit findings

The deterministic audit reads only committed knowledge files. It collapses construction variants,
does not call an LLM, and does not query live regional inventory. Canonical size breadth and brand
importance are used only to rank likely remediation value.

- 573 canonical profile rows
- 513 distinct brand-model identities
- 60 construction-variant rows collapsed
- 430 models with descriptions after merging construction variants
- 192 models with deterministic classification
- 83 models without descriptions after merging construction variants
- 321 deliberately unclassified models

The older `board_intelligence_audit.json` reports 84 missing descriptions. Its deduplication chooses
one highest-confidence construction row and therefore marks Lost Puddle Jumper HP missing even
though another canonical construction variant carries its description. Phase 2 merges evidence
across variants, producing the corrected model-level count of 83.

The following counts mean “captured today in Board Guide knowledge,” not “the upstream website is
incapable of exposing it.” Keyword evidence in prose is counted as present for discovery, but it is
not yet a normalised high-confidence field.

| Brand | Models | Description | Category | Wave range | Wave type | Ability | Design | Tags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Album | 19 | 8 | 6 | 0 | 0 | 0 | 5 | 4 |
| Channel Islands | 62 | 62 | 17 | 0 | 3 | 1 | 23 | 19 |
| Chemistry Surfboards | 38 | 36 | 7 | 0 | 1 | 2 | 10 | 18 |
| Chilli | 24 | 24 | 11 | 4 | 2 | 10 | 24 | 14 |
| Christenson | 31 | 0 | 3 | 0 | 0 | 0 | 0 | 3 |
| DHD | 23 | 22 | 13 | 16 | 3 | 14 | 13 | 11 |
| DMS Surfboards | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Firewire | 29 | 29 | 16 | 1 | 2 | 2 | 29 | 17 |
| Haydenshapes | 14 | 14 | 7 | 4 | 9 | 12 | 12 | 12 |
| JS Industries | 30 | 20 | 7 | 1 | 1 | 1 | 6 | 11 |
| Lost | 79 | 77 | 35 | 0 | 9 | 4 | 73 | 47 |
| Misfit Shapes | 12 | 12 | 1 | 0 | 0 | 0 | 4 | 0 |
| Pukas | 13 | 0 | 1 | 0 | 1 | 0 | 0 | 1 |
| Pyzel | 41 | 39 | 28 | 8 | 9 | 6 | 39 | 35 |
| Rusty | 49 | 46 | 17 | 0 | 5 | 5 | 36 | 19 |
| Sharp Eye | 20 | 20 | 15 | 2 | 0 | 6 | 20 | 16 |
| Simon Anderson | 21 | 21 | 5 | 1 | 0 | 0 | 10 | 9 |

Important discovery opportunities already visible in manufacturer material:

- Sharp Eye narratives expose outline/range, entry and exit rocker, rail, fin setup, ability, and
  sometimes explicit wave height. The current Board Guide capture preserves much of this as prose
  but not as structured scales.
- Pyzel source taxonomy distinguishes High Performance, Daily Drivers, Funformance, and Mid
  Length/Gun. That taxonomy should become `manufacturerSeries` plus categories, not model names.
- Lost source families distinguish Performance, Something Fishy, Grovellers, Recreational
  Vehicles, Mid Lengths, and Step Ups. Construction and marketing suffixes must not inflate models.
- JS source material distinguishes Charger, Performer, Daily, Fun, Youth, Foil, and Softboard
  series. Ten of 30 canonical JS models still lack descriptions in the current global profiles.
- Rusty descriptions often contain practical conditions and extra-volume guidance. This is useful
  surfer-fit evidence when stored as sourced guidance rather than converted into a universal rule.

## Highest-priority intelligence gaps

The full ranked list is in `app/knowledge/audits/board_intelligence_priority_models.csv`. The first
20 are:

| Rank | Brand | Model | Main next action |
| ---: | --- | --- | --- |
| 1 | Lost | Puddle Jumper | Extract category, waves, ability, and tags from manufacturer evidence |
| 2 | Pyzel | Gremlin | Extract category, wave fit, tags, and explicit comparables |
| 3 | JS Industries | Black Baron | Extract structured category, wave, surfer, and design metadata |
| 4 | Lost | Rad Ripper | Extract structured category, wave, and surfer fit |
| 5 | JS Industries | Monsta | Recover canonical manufacturer description and design evidence |
| 6 | Firewire | Dominator 2.0 | Extract category, wave fit, surfer fit, and equivalency |
| 7 | Firewire | Seaside | Extract category, wave power, surfer fit, and equivalency |
| 8 | Lost | RNF 96 | Capture wave range/type/power and surfer fit |
| 9 | JS Industries | Golden Child | Recover manufacturer description |
| 10 | JS Industries | Xero Gravity | Recover manufacturer description |
| 11 | Sharp Eye | Inferno 72 | Capture structured wave range/type and explicit alternatives |
| 12 | JS Industries | Golden Child Youth | Recover manufacturer description and youth series |
| 13 | Lost | Crowd Killer Round | Recover manufacturer description and verify variant identity |
| 14 | Haydenshapes | Hypto Krypto | Capture remaining design and equivalency evidence |
| 15 | Rusty | Dwart | Extract category, wave fit, ability, and tags |
| 16 | Lost | Party Crasher | Recover manufacturer description and verify canonical identity |
| 17 | Firewire | Mashup | Capture wave fit, surfer fit, and explicit relationships |
| 18 | JS Industries | Xero Gravity Easy Rider | Recover description; verify construction/size suffix versus model |
| 19 | Pyzel | Ghost | Capture structured wave type and explicit comparable models |
| 20 | JS Industries | Golden Child Easy Rider | Recover description; verify suffix semantics |

This ranking is an audit queue, not a recommendation ranking. A missing field receives additional
priority because filling it has high remediation value.

## Phase 3 implementation plan

| Brand | Phase 3 change | Expected gain | Risk | Effort | Curated override? |
| --- | --- | --- | --- | --- | --- |
| Album | Repair official model URLs/descriptions; extract family and category | High description gain on 11 models | Medium | Medium | Yes for ambiguous concepts |
| Channel Islands | Extract official family, wave guidance, design labels, and related models | High structured gain across 62 models | Medium | High | Only for unresolved aliases |
| Chemistry Surfboards | Repair source/model naming before metadata extraction | Moderate; two descriptions and most structure | High | Medium | Likely for catalogue aliases |
| Chilli | Normalise existing strong design prose into matrix fields | High structure with low description work | Low | Medium | Rare |
| Christenson | Build manufacturer-description capture before classification | Very high across 31 models | Medium | High | Yes for legacy families |
| DHD | Extract range, waves, ability, rocker, rail, tail, and fins | High; source already has useful coverage | Low | Medium | Rare |
| DMS Surfboards | Establish reliable official sources and descriptions | Very high across eight models | High | Medium | Likely |
| Firewire | Extract family, conditions, ability, design, and construction notes | High structured gain across 29 described models | Medium | Medium | For construction taxonomy only |
| Haydenshapes | Normalise waves, ability, design, and relationships | Moderate; current prose coverage is strong | Low | Low | Rare |
| JS Industries | Capture seven manufacturer series and repair ten descriptions | Very high | Medium | Medium | For suffix/model identity cases |
| Lost | Capture six source families and split marketing/construction suffixes | Very high across 79 models | High | High | Yes for model inflation review |
| Misfit Shapes | Add categories, waves, ability, and design extraction | High structure across 12 described models | Medium | Medium | Possibly |
| Pukas | Separate manufacturer model intelligence from retailer catalogue | Very high across 13 models | High | Medium | Likely for shaper/model mapping |
| Pyzel | Capture source taxonomy, waves, ability, design, and relationships | High; descriptions already cover 39 of 41 | Low | Medium | Rare |
| Rusty | Extract practical conditions and rider-volume guidance | High structured gain across 46 descriptions | Medium | Medium | Review volume claims |
| Sharp Eye | Parse labelled outline, wave, ability, rail, rocker, and fin fields | Very high-quality structured gain | Low | Medium | Rare |
| Simon Anderson | Extract categories, waves, surfer fit, and design data | High structure across 21 descriptions | Medium | Medium | Possibly for legacy models |

Implementation should proceed manufacturer by manufacturer behind snapshot tests. Phase 3 should
first produce a proposed matrix diff, then require review before replacing generated knowledge.
Recommendation behaviour should change only after field provenance and confidence are carried into
the runtime model.

## Reproducing the audit

```powershell
python scripts/audit_board_intelligence_sources.py
```

Outputs:

- `app/knowledge/audits/board_intelligence_source_audit.json`
- `app/knowledge/audits/board_intelligence_matrix_gap_report.csv`
- `app/knowledge/audits/brand_metadata_coverage.csv`
- `app/knowledge/audits/board_intelligence_priority_models.csv`

The outputs are intentionally stable: there is no timestamp, network request, SQL query, or LLM
call. Regeneration from unchanged committed inputs must produce an empty diff.
