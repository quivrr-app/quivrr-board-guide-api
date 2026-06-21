# Board knowledge sources

Bodhi separates global board knowledge from regional availability. A board's design intent does not change between Australia, Europe and Indonesia; only verified stock does.

## Source precedence

1. Explicit, reviewable Quivrr overrides.
2. Manufacturer model descriptions and technical specifications.
3. Manufacturer category, family and series pages.
4. Deterministic mappings from the sources above.
5. Low-confidence catalogue fallbacks, clearly marked for review.

Manufacturer descriptions remain authoritative for design intent. Quivrr overrides may resolve taxonomy or crossover-lane ambiguity, but every override records a reason, reviewer and review time.

Retailer descriptions are not canonical because they are frequently shortened, duplicated, embellished, or applied to a particular construction or stock item rather than the model globally. They may help diagnose a listing, but cannot silently redefine the canonical board.

## Future review ingestion

External reviews may be supporting evidence only. A future review record should store the source URL, author or publication, publication date, a short original summary, relevant claims, evidence weight, and any disagreement with manufacturer or curated evidence. It must not store long copied passages. Copyrighted text should be quoted only in short, necessary excerpts with attribution.

The evidence model must permit disagreement: a reviewer may describe a board as demanding while a manufacturer presents it as accessible. Bodhi should retain both attributed claims, apply explicit weights, and explain uncertainty rather than flattening them into a false fact.

Live stock links and counts never come from this knowledge layer. They are added only after model selection through verified region-scoped inventory APIs.

## Curated expert override governance

`app/knowledge/curated/board_expert_overrides.json` is the reviewable expert layer for iconic and
high-value models. An override may set a primary lane, crossover lanes, board family, concise
reputation and fit notes, bounded design scores, confidence, evidence sources and review metadata.
Uncertain judgements stay medium confidence and retain a note; they are not promoted through fuzzy
matching. Defaults provide the full schema, while each model entry records the facts that are
specifically known about it.

Fish is deliberately not one undifferentiated category. A traditional keel fish, point-break twin,
performance fish, cruisy fish and small-wave fish can suit different waves and surfers even when
their outlines look related. Bodhi uses those sub-lanes to form advice before stock is queried.

Canonical recommendations and availability are separate statements. A strong canonical fit may be
named when no regional stock is found, but it must be labelled as unavailable. Only a successful
region-scoped inventory lookup can create a verified live card or direct purchase link.

## Relationship evidence precedence

Board-to-board relationships use the same evidence boundary:

1. explicit relationships in `board_relationship_overrides.json`;
2. shared expert-matrix lanes and reviewed model scores;
3. deterministic similarity and directional score differences.

Curated edges are high confidence only when both source and target exist in the canonical matrix.
Requested iconic names missing from that matrix are reported by the Phase 9 audit rather than being
silently invented. Generated edges remain medium or low confidence and are bounded to prevent the
graph from becoming an indiscriminate list of every vaguely similar surfboard.

Volume guidance is not an inventory fact and never changes regional stock. The v2 engine uses global
board-lane knowledge and user-provided rider context; inventory is queried only after a canonical
relationship or board fit has been selected and only when the user supplies a region.
