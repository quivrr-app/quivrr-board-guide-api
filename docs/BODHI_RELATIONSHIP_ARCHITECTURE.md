# Bodhi Relationship Architecture

Last updated: 2026-07-23 UTC

## Purpose

Sprint 3 moved Bodhi from simple recommendation ranking into relationship based surf shop reasoning.

The relationship layer supports questions such as:

* What is more performance than a Hypto?
* What is easier than a Phantom?
* What is like a Seaside but more performance?
* What should I ride after my current board?
* I ride a 29L Hypto and want more performance.

## Runtime position

The relationship graph lives inside the Bodhi API knowledge layer.

It does not change SQL, retailer inventory, manufacturer availability, importer scripts, MFA jobs, retailer jobs or Azure Container Apps jobs.

## Key files

| File | Purpose |
| --- | --- |
| `app/board_relationship_graph.py` | Loads and resolves board relationships |
| `app/knowledge/board_relationships.json` | Curated surf shop relationship guidance |
| `app/knowledge/curated/board_relationship_overrides.json` | Manual overrides and corrections |
| `scripts/generate_board_relationship_graph.py` | Generates relationship coverage |
| `tests/test_sprint3_relationships.py` | Behaviour coverage for Sprint 3 |
| `tests/test_sprint3_alias_integrity.py` | Canonical alias regression coverage |

## Behaviour model

Relationship intent is resolved before generic recommendation ranking. This prevents a progression request from being treated as a broad category search.

Supported relationship lanes include:

* similar
* more performance
* more forgiving
* more paddle
* better for points
* better for beach breaks
* better for small waves
* better for good waves
* step up
* step down
* fish alternative
* shortboard alternative

## Volume continuity

When the user provides a current board volume, that volume becomes a strong anchor.

For example, a 29L Hypto performance progression should generally remain near 28 to 30.5L unless the user asks for more paddle or easier wave entry.

## Region and inventory behaviour

Relationship cards continue to use the Sprint 2 regional CTA model:

* AU cards link to `/australia`
* EU cards link to `/europe`
* ID cards link to `/indonesia`
* visible CTA links open Quivrr search
* `sourceProductUrl` remains available separately
* stock checks must respect the current active relationship topic

## Sprint 3.1 alias cleanup

Three curated aliases were removed because they did not match canonical catalogue names:

* JS Industries Red Baron
* DHD Golden Child
* Christenson Fish

These were removed from the curated override layer only. Generated relationship coverage remains available where canonical profiles exist.

Regression coverage is provided by:

* `tests/test_sprint3_alias_integrity.py`
