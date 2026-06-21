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
