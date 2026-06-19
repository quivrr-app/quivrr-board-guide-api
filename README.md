# Quivrr Board Guide API

Segregated backend for Quivrr Board Guide.

Working persona:
Bodhi, the Core Lord

Purpose:
- Serve the board guide chat API
- Integrate with Azure OpenAI
- Keep LLM traffic separate from quivrr-backend
- Combine global board intelligence and rider-fit guidance with read-only regional availability

## Production state

Bodhi is deployed on [quivrr.surf](https://quivrr.surf) and served by `quivrr-board-guide-api`. It provides:

- deterministic rider-fit volume guidance
- manufacturer board descriptions and generated intelligence
- region-aware recommendations for active AU, EU, and ID runtime regions
- live manufacturer-direct and retailer availability supplied by `quivrr-backend-api`

`RegionCode` is mandatory for availability. An EU request may use only EU stock and URLs; an AU request may use only AU stock and URLs. There is no silent AU fallback for invalid regions and no AU availability fallback for EU or ID.

## Board knowledge architecture

The canonical surfboard catalogue is global. Regional manufacturer and retailer records are
availability only and are queried at recommendation time with an explicit `AU`, `EU`, or `ID`
filter.

Description precedence is:

1. Manufacturer description captured in `canonical_board_profiles.json`.
2. Quivrr-reviewed intelligence override.
3. A generated factual summary when no manufacturer description exists.
4. Retailer descriptions only as explicitly labelled, non-authoritative fallback context.

Retailer descriptions are not canonical board truth and the description scraper never reads
retailer pages. Run the manufacturer enrichment as a read-only dry run first:

```powershell
python scripts/scrape_manufacturer_board_descriptions.py --report description_audit.json
```

After reviewing coverage and samples, `--apply` updates generated JSON only. It never writes SQL.

## Board Intelligence Platform

The intelligence pipeline is:

1. Manufacturer source descriptions and metadata.
2. Global canonical board profiles.
3. Global deterministic board-intelligence layer.
4. Rider-fit engine.
5. Board-equivalency engine.
6. Bodhi recommendation engine.
7. Read-only live regional inventory lookup.

The canonical catalogue and board intelligence are global. Region affects stock, price, currency, retailer/manufacturer source, product URL, and location. Region does not affect board identity, descriptions, category, wave fit, or surfer-fit taxonomy.

The generated intelligence records board category, daily-driver/performance/groveller/fish/step-up/mid-length/longboard/twin-fin/hybrid flags, wave type and power, surfer level, published wave range, recommendation tags, and deterministic confidence. No LLM is used for classification.

Current June 2026 coverage:

- 513 distinct canonical model profiles
- 430 models with manufacturer descriptions after construction-variant evidence is merged
- 192 deterministically classified models
- 321 deliberately unclassified models
- 83 models missing manufacturer descriptions (the legacy audit reports 84 because it selects a
  description-free Lost Puddle Jumper HP construction variant)

Unclassified and low-confidence results remain visible in `app/knowledge/generated/board_intelligence_audit.json`; the classifier must not invent weak matches.

The Phase 2 manufacturer intelligence discovery audit, target Board Intelligence Matrix, brand
coverage, priority remediation queue, and Phase 3 plan are documented in
[`docs/BOARD_INTELLIGENCE.md`](docs/BOARD_INTELLIGENCE.md). Reproduce its stable read-only outputs
with:

```powershell
python scripts/audit_board_intelligence_sources.py
```

Phase 3 harvests reviewed global manufacturer metadata into a separate model-level companion file
without changing production recommendation behaviour:

```powershell
python scripts/harvest_canonical_board_intelligence.py
python scripts/harvest_canonical_board_intelligence.py --apply
```

See the Board Intelligence documentation for the source-index refresh workflow, field-level
confidence rules, and coverage report.

Phase 4 builds the deterministic global taxonomy, Board DNA, comparison layer, rider archetypes,
and recommendation graph without changing live recommendation behaviour:

```powershell
python scripts/generate_board_recommendation_graph.py
```

The graph covers 512 of 513 canonical models. Runtime inventory remains a separate explicit-region
input to the replacement-ranking helper.

## Rider Fit And Availability

The rider-fit engine uses weight, ability, fitness, surf frequency, waves, preferred board type, current volume, age when supplied, and desired feel. It returns a volume range rather than a single prescriptive value and explains adjustment factors. Volume is guidance, not the whole fit decision.

Recommendation ranking considers board/category/volume fit first, then verified availability in the selected region, manufacturer-direct stock, retailer stock, and close controlled alternatives. If no regional stock exists, Bodhi says so instead of inventing availability.

## Seven-phase roadmap

1. Architecture, documentation, and governance.
2. Manufacturer intelligence discovery audit.
3. Canonical intelligence harvesting.
4. Board classification engine.
5. Board equivalency engine.
6. Rider fit and intake workflow.
7. Full Bodhi recommendation integration with live regional inventory.

The phases are architectural workstreams rather than hard release boundaries; several are already implemented and continue to improve as catalogue coverage grows.
