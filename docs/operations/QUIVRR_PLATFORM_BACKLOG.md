# Quivrr Platform Backlog

## 2026-07-23 — Bodhi selected-region model-card correction

- Affected areas: Board Guide API canonical model-card hand-off; no inventory or profile data was changed.
- Issue: a direct canonical board answer could produce a model-only card using the public-card Australia fallback before stock lookup, despite the caller selecting another region.
- Change: direct board-detail cards now preserve the requested region and canonical model ID; broader recommendation cards retain their deliberate existing behaviour.
- Verification: direct Album Plasmic Indonesia link regression added; 110 targeted API tests and the 254-test discovery suite passed.
- Follow-up: engineering and architecture documents are unchanged pending owner approval.

## 2026-07-23 — Bodhi canonical availability regression closure

- Affected areas: Board Guide API active-board inventory response and its regression coverage; no profile or catalogue data was changed.
- Issue: legacy discovery tests still asserted the retired exact-location route after canonical active-board availability was introduced. Returned exact-size cards also omitted the verified seller source URL.
- Change: aligned the guard tests to the authoritative per-model regional availability contract and retained the verified offer URL on each exact-size card.
- Verification: 253-test API discovery suite passed in 68.123 seconds; unit-test transport guarding kept ordinary tests off Azure and external manufacturer endpoints.
- Follow-up: engineering and architecture documents are unchanged pending owner approval.

## 2026-07-23 — Bodhi canonical handoff and active-board inventory remediation

- Affected areas: runtime, search, frontend and Azure deployment; no data-quality mutation or cleanup.
- Issue: Bodhi dropped canonical board identifiers while rendering regional links, regional pages then tried display-name preselection, and previous family-search context could override an explicit active-board availability or profile-update request.
- Change: canonical BoardSizeId handoffs now carry region and model identity and only auto-search when an exact size exists; regional pages resolve a BoardSizeId through a read-only core identity contract before selecting dropdowns; the conversation state stores the active canonical board and exact inventory context; explicit profile updates, active-board availability, comparisons and details now precede historical intent.
- Verification: added exact-size availability and BoardSize identity contracts, active Album Plasmic regression coverage, direct volume-proposal coverage, canonical URL widget tests and all-four-region query handling tests. Unit-test transport guarding prevents the new availability read from contacting Azure without an injected test transport.
- Follow-up: engineering and architecture documents are unchanged pending owner approval. Production deployment and smoke validation remain required before this entry is closed.

## 2026-07-23 — Bodhi performance-fish stock recovery

- Issue: a request for a “pro fish” in Indonesia was treated as an exact taxonomy lookup. Empty filtered results were presented as an inventory-verification failure, and follow-up “why?” or correction messages could repeat that failure.
- Change: mapped performance-fish language to the governed Fish family plus recommendation characteristics; added progressive fish/hybrid widening, deterministic recovery and response-state tracking, accurate empty-result language, and calm mild-profanity handling.
- Verification: targeted Bodhi intent tests, compilation checks, and the local automated suite.
- Follow-up: engineering and architecture documents were not changed pending owner approval.

## 2026-07-23 — Sprint 4 board-name resolution and Bodhi loading feedback

- Issue: direct model questions such as “tell me about the JS Monsta” could be routed through generic help before board lookup. A close typo (“JS Mosta”) was not reliably recovered, and the chat did not explain the stages of a longer search.
- Change: introduced one deterministic canonical-board resolver used before generic help, including manufacturer aliases, reviewed model aliases, bounded typo recovery, explicit ambiguity handling, canonical ID telemetry, and direct board-detail replies. Added a catalogue-wide recognition audit and progressive in-chat loading messages: catalogue, surfer-fit matching, then stock signals.
- Verification: 431 canonical models across 1,456 recognition forms: 99.79% automatically resolved, with 0 incorrect or unresolved required matches and 3 intentionally clarification-required model-only terms. Board Guide API tests (46), intent tests (39), resolver tests (3), source-audit tests (2), and frontend widget tests (14) passed.
- Validation limitation: `python -m unittest discover -s tests` did not complete within the four-minute local command bound, so the aggregate discovery result remains inconclusive despite the passing focused suites.
- Historical note: the legacy 518-profile classification figure is not the governed runtime metric. Its Sprint 4 coverage and profile-persistence conclusions are superseded by the completion record below.
- Follow-up: engineering and architecture documents were not changed pending owner approval.

## 2026-07-23 — Bodhi Sprint 4 completion: governed intelligence and profile confirmation

- Issue: Sprint 4 had an unresolved model-count narrative, no explicit release-quality gate for the governed runtime intelligence, and a profile-change conversation flow that needed a safe authenticated persistence hand-off.
- Change: reconciled the runtime to 431 active canonical board IDs; added model-universe and structured-intelligence coverage audits; reinforced controlled board explanations and conservative clarification behaviour; completed the explicit profile-proposal, confirmation, and allowlisted My Quivrr `PATCH /api/my-quivrr/profile` hand-off. Improved loading stages to run only for applicable work and made unavailable profile persistence fail visibly rather than report a false save.
- Verification: 1,456 recognition forms with 100% resolution for explicit brand-and-model forms, 0 incorrect/unresolved matches, and 3 intentional model-only clarification requests; 95.36% structured usable intelligence coverage with 20/431 (4.64%) weak records and no missing controlled fields; governed profile and resolver tests passed (5), as did frontend syntax and widget tests.
- Documentation: updated Board Guide intelligence authority, the core backend architecture profile contract, and this backlog. Historical legacy profile/classification counts are explicitly separated from the current runtime universe.
- Verification update: aggregate `python -m unittest discover -s tests` completed in 53.662 seconds with 251 passing tests. The prior inconclusive result was the local command boundary, not an external dependency or suite failure. No commit or deployment was performed at the time of this entry.

## 2026-07-23 — Bodhi Sprint 4 production release

- Release: deployed Board Guide API runtime commit `c19a885` to `quivrr-board-guide-api.azurewebsites.net` through the repository zip-package path. Azure reported `RuntimeSuccessful` with one successful instance and no failed instances. Surf frontend commit `b08181d` deployed through GitHub Actions run `30010565934` successfully.
- Production verification: Board Guide chat resolved the JS Monsta, JS Mosta, CI 2.Pro (canonical `ci-2-pro`), Lost RNF 96, Firewire FRK+, and Gremlin/Xero Gravity comparison prompts without generic fallback. The Board Guide CORS preflight permitted `https://quivrr.surf`; Surf and regional Quivrr pages returned HTTP 200; the unauthenticated core profile endpoint returned HTTP 401 as expected.
- Rollback points: Board Guide API `b9d75e2`; Surf frontend `71b9bdc`. Rebuild and deploy the Board Guide package from the API rollback commit, or redeploy the Surf rollback commit through its normal Azure Static Web Apps workflow, if the release causes a chat, authentication, CORS, search, or resolution regression.
