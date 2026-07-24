# Phase 3B Root-Cause Audit

Audit timestamp: 2026-07-24 12:35:00
Baseline: `5fc85e83b092559fe332f1aa5006b7d33d04b727`
Historical runtime: `PHASE3_OBJECTIVE_CLOSURE_20260723_1845_2dcc5e9`

This diagnosis is based on direct inspection of the historical runtime and
current source. Historical runtimes are immutable evidence and are not edited.

| ID | Direct evidence | First root cause | Minimal correction | Verification |
|---|---|---|---|---|
| F3B-01 | Provenance records executed SHA `2dcc5e952ab6c58d5afc97daec8f1281939b259c`, not final SHA `5fc85e83b092559fe332f1aa5006b7d33d04b727`. | Provenance captured from a pre-final source state. | Enforce clean pre-runtime SHA identity and persist it before processing. | Fresh provenance equals the pre-runtime SHA and clean status. |
| F3B-02 | Historical Step9/decision files have timestamps after runtime END. | Closure files were rewritten after execution completion. | Move all final artifact writes before one final package and add write-timeline audit. | No required artifact write occurs after END. |
| F3B-03 | Scientific gate executes before final objective/QA/global audits. | Decision consumes stale gate inputs. | Finalize semantic/cartographic/warning/objective/QA inputs before scientific gate and package. | Dependency freshness audit passes. |
| F3B-04 | Summary says HOLD while internal scientific decision says NO-GO. | Multiple independent decision writers. | Use one canonical decision token and distinguish blocked claims from failed proxy execution. | Decision surfaces are byte/token consistent. |
| F3B-05 | A 260-row unit-year smoke table is joined by unit only and produces one feature per source unit. | Temporal key omitted from spatial join. | Emit one feature per unit-year for temporal tables, with explicit key/year fields. | Source/output unit-year coverage and year uniqueness pass. |
| F3B-06 | Portugal LEVL3 filter does not exclude `PT200` or `PT300`. | Country/level filter was mistaken for Continente scope. | Exclude the two autonomous-region NUTS3 units in the canonical filter. | Fresh inventory has continental counts and no PT200/PT300. |
| F3B-07 | Fire audit has no invalid-before/after or repair accounting. | Geometry validity is not an explicit gate. | Validate and deterministic-repair each geometry; persist exact counts/method. | Final invalid geometry count is zero or exact HOLD list. |
| F3B-08 | No fire area reconciliation artifact exists. | Source/output area conservation is not computed. | Persist source/output/delta/tolerance and excluded-feature accounting. | Reconciliation audit passes declared tolerance. |
| F3B-09 | E1 uses aggregated tables and reports zero cell assignments. | Raw smoke/GHSL spatial inputs were not inspected. | Inventory raw authorized spatial inputs and emit `NOT_EVALUATED_WITH_RAW_SPATIAL_INPUTS` when absent. | E1 includes raw metadata or an exact unevaluated disposition. |
| F3B-10 | E2 lacks pixels, coverage, one-cell, ratio, and edge metrics. | Resolution feasibility is asserted without spatial diagnostics. | Persist the complete metric set and explicit direct-signal decision. | Full metric rows exist for the municipal inventory. |
| F3B-11 | WUI candidate metadata is blank and root exclusions are not recorded. | DataRoot inventory is incomplete and not provenance-complete. | Search only authorized data roots, exclude runtime/tooling paths, and record metadata/disposition. | Inventory proves root, exclusions, readability, year, CRS, coverage, classes. |
| F3B-12 | No persisted pytest command/stdout/stderr/environment/result summary is in the final surface. | Test evidence is not a runtime-owned deliverable. | Persist test evidence and collect it in the final inventory/manifest. | Direct test artifact audit passes. |
| F3B-13 | Historical manifest omits freshness, fire reconciliation, and test evidence. | Manifest is a partial hand-maintained list. | Add all consumed final gates and assert manifest/ZIP equivalence. | Required inventory is complete and ZIP members match. |
| F3B-14 | Brief contains repeated closure sections and mojibake. | Rewriter appends instead of replacing and does not validate encoding. | Idempotently replace the section and add encoding/duplicate checks. | Exactly one closure section and UTF-8-clean brief. |

All F3B-01..F3B-14 are OPEN implementation findings. No historical artifact or
prior test is treated as closure evidence for the fresh runtime.
