# Phase 3C residual root-cause audit

Baseline: `c263d103aca3756abae3fa91fd2f24e0f58e9c07`
Structural evidence: `03_RUNTIMES/STRUCTURAL_CLOSURE_BEFORE_PHASE3C_20260725_203500`

This audit maps each residual to the producer, the direct baseline evidence, and the minimum correction. Phase 3B numerical surfaces and the existing `population_smoke_burden_proxy` are preserved.

| Residual | Direct evidence | First root cause | Producer/function | Minimal correction | Pre-test | PASS criterion |
|---|---|---|---|---|---|---|
| P3C-01 | Baseline `landcover_wui_input_inventory.tsv` has runtime/venv paths and the producer reads `paths.modulec_data`. | The inventory root is not the resolved effective DataRoot and lacks an absolute parent-child guard. | `pipeline/phase3_objective_closure.py::_feasibility_audits` | Read `paths.smoke_effective_data_root`; emit absolute/relative path, readability and exclusion metadata. | `test_phase3c_wui_inventory_is_authorized_and_metadata_complete` | Zero outside-root/runtime/venv rows. |
| P3C-02 | Baseline `population_weighted_smoke_feasibility.tsv` says no cell input without inspecting physical GFAS/GHSL/ERA5 paths. | Feasibility is inferred from aggregated outputs rather than resolved source inputs. | `pipeline/phase3_objective_closure.py::_feasibility_audits` | Persist a raw-input audit and distinguish evaluated raw inputs from a non-defensible additional proxy. | `test_phase3c_raw_grid_audit_does_not_use_aggregates_as_input` | Raw source presence is directly recorded and the historical proxy remains retained. |
| P3C-03 | Baseline municipal feasibility leaves required metrics `NOT_AVAILABLE`. | The producer has no raw-grid inspection branch and unconditionally emits placeholders. | `pipeline/phase3_objective_closure.py::_feasibility_audits` | Route the decision through raw-input evaluation and retain the NUTS3 allocation when direct municipal resolution is not defensible. | `test_phase3c_municipal_resolution_has_decision` | No unsupported `NOT_AVAILABLE` conclusion when physical inputs exist. |
| P3C-04 | Baseline warning inventory reads only four QA files. | External launcher, decoder, QGIS, Step9 and pytest logs are outside the scan set. | `pipeline/moduleC_pipeline_v2.py::refresh_warning_inventory_from_runtime_logs` | Add runtime-root log sources and machine-readable warning identity/source/reconciliation fields. | `test_phase3c_warning_inventory_includes_external_logs` | Every scanned warning line is classified and source-linked. |
| P3C-05 | Baseline brief is written as UTF-8 but has no mojibake audit. | Encoding correctness is assumed from the writer and is not checked on the final brief. | `pipeline/moduleC_pipeline_v2.py::complete_post_smoke_runtime` | Generate `qa/brief_encoding_audit.tsv` over the final brief. | `test_phase3c_brief_encoding_audit` | Mojibake and UTF-8 error counts are zero. |
| P3C-06 | Baseline `source_runtime_provenance.tsv` uses the first/last QA run-log lines and is written before final packaging. | Provenance is finalized before Step9/manifest/ZIP completion. | `pipeline/moduleC_pipeline_v2.py::write_source_runtime_provenance` | Reconcile runtime-root logs and final packaging timestamps before closure. | `test_modulec_runtime_source_provenance` | Runtime window encloses all required artifacts and the recorded SHA matches the executed SHA. |

## Authorized semantic boundary

The raw-grid audits are additive. They do not replace or recalculate Phase 3B scientific surfaces. Formal WUI, direct municipal atmospheric smoke, normalized IECH, individual exposure, health, epidemiological and causal claims remain blocked unless the authorized raw-input tests demonstrate their validity.
