# Phase 3C R3 final root-cause audit

## Scope

R2 is sealed and is not an input, output, source, or packaging target for R3. The baseline correction is `5df30dc7313b6b2186235b1029fcdc48e44fcc04` and the R3 runtime must be created from a new root after the corrective commit.

## Residual causes found in R2

| blocker | producer/caller | cause | corrective action |
|---|---|---|---|
| Brief mojibake | `pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py::generate_brief` | Double-encoded Spanish literals were written directly into the brief. | Replace only the corrupt producer literals with UTF-8 source text and keep the encoding audit as a blocking gate. |
| P3C-03 synthetic zero metrics | `pipeline/phase3_objective_closure.py::_feasibility_audits` | Municipal feasibility emitted zero placeholders without consuming CAOP geometry or raw GFAS metadata. | Evaluate CAOP geometry against raw GFAS raster metadata and persist p10/p50/p90, coverage, single-cell, ratio, edge and centroid sensitivity metrics; retain NUTS3 allocation. |
| Provenance absent | `moduleC_pipeline_v2.py::complete_post_smoke_runtime` | Global audit assertion ran before provenance finalization; an active audit blocker terminated the flow. | Persist launcher command/roots/exit and complete source/window provenance before packaging, and include them in the final payload. |
| Step9 absent | `complete_post_smoke_runtime` caller sequence | `assert_global_audit_status_clear` raised before `build_manifest_and_zip`. | Preserve the assertion, but make upstream audits truthful and complete so Step9 is reached only after all blockers are resolved. |
| Comparison mis-scoped | `run_phase3_phase2_scientific_comparison` / `phase3_scientific_comparison.py` | The runtime compared against a Phase 2 path and emitted non-contractual status vocabulary. | Compare against the immutable Phase 3B runtime and emit the contractual classification vocabulary plus Phase3C/Phase3B aliases. |

## Gate preservation

The correction does not alter `population_smoke_burden_proxy`, Portuguese AQ anchoring, normalized IECH/health/causal blocked claims, or the municipal NUTS3 allocation semantics. R2 remains immutable. R3 is the first runtime eligible for final closure.
