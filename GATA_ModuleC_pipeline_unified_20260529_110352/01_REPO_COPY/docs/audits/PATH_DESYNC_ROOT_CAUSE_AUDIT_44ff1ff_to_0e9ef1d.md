# PATH DESYNC Root Cause Audit (44ff1ff -> 0e9ef1d)

## Scope
- Canonical repo: `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY`
- Branch checked: `main`
- Base SHA checked: `ce7736d893a588ce85b21d725f1288d97c031bb6`
- Diff window: `44ff1ff903dbcc39ee8b7da289a5ced159a71384..ce7736d893a588ce85b21d725f1288d97c031bb6`

## Precheck Evidence
- `git branch --show-current` -> `main`
- `git rev-parse HEAD` -> `ce7736d893a588ce85b21d725f1288d97c031bb6`
- `git status --short` -> clean (no entries)

## Commit Delta (direct)
`git log --oneline 44ff1ff..0e9ef1d`:
- `c32f824` Add objectives gate, OC audits and final bundling
- `f362e18` Add global audit scan and scenario checks
- `0477a58` Improve scenario delta audit & global scan
- `0e9ef1d` Enhance global audit scan and QA outputs

## File-Level Delta (direct)
`git diff --name-status 44ff1ff 0e9ef1d`:
- `A PIPELINE_CANON_HANDOFF/12_OBJECTIVES_CANON_MODULEC_IECH.md`
- `M pipeline/RUN_ModuleC_Pipeline_OSGeo4W.cmd`
- `M pipeline/RUN_QGIS/STEP7_MATRIZ_CAUSAL/step7_matriz_causal.py`
- `M pipeline/RUN_QGIS/STEP9_FINAL_MASTER_PACK/run_step9_final_master_pack.ps1`
- `A pipeline/global_audit_status_scan.py`
- `M pipeline/moduleC_preflight.py`
- `M pipeline/qa_gate_v2.py`
- `A pipeline/validate_modulec_objectives_canon.py`

## Launcher Root-Cause Evidence (direct read)
From `pipeline/RUN_ModuleC_Pipeline_OSGeo4W.cmd` at SHA `0e9ef1d...`:
1. Header declares `dual-mode (ISO layout + GitHub export layout)`.
2. It marks `moduleC_local_pipeline` as `ISO_MARK=1` and `pipeline` as `EXPORT_MARK=1`.
3. It sets `RUNMODE=ISO` when wrapper path is `moduleC_local_pipeline`.
4. In ISO mode it derives:
   - `GATA_ROOT` from `PIPELINE_ROOT\..\..`
   - `DATOS_MODC` from `...\Complementariedad de analisis\Module C\Datos`
   - `OUTPUT_ROOT` from `...\Complementariedad de analisis\Module C\03_outputs`
5. In EXPORT mode it requires:
   - `GATA_EXTERNAL_DATOS_MODC`
   - `GATA_EXTERNAL_OUTPUT_ROOT`
   and optionally reads them from `config\local_paths.ps1`.

## Why desync happened
- One launcher accepted two code roots (`moduleC_local_pipeline` and `pipeline`) as valid.
- ISO mode enabled execution directly from lateral `_qa_catalogs\moduleC_local_pipeline`.
- Export mode used canonical repo path but could target overlapping external outputs.
- Result: source-of-truth ambiguity and stale payload risk in final packaging.

## Detection paths implemented by launcher (as-is pre-fix)
- Detects `moduleC_local_pipeline`: `PIPELINE_DIRNAME == moduleC_local_pipeline`.
- Detects `pipeline`: `PIPELINE_DIRNAME == pipeline`.
- ISO DATOS/OUTPUT derivation: hardcoded from inferred `GATA_ROOT`.
- EXPORT DATOS/OUTPUT derivation: env/config via `GATA_EXTERNAL_DATOS_MODC` and `GATA_EXTERNAL_OUTPUT_ROOT`.

## Why `_qa_catalogs\moduleC_local_pipeline` must be blocked as editable code
- It is a divergent copy (different SHA and runtime-only artifacts).
- It is outside canonical Git governance for Module C fixes.
- Running code from there reintroduces path-source ambiguity and legacy carry-over.

## Root Cause Decision
- `PATH-DESYNC CONFIRMED`
- Causal class: `dual code-root acceptance + mixed derivation of data/output roots`

## Required correction direction
- Keep `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY` as only editable/executable code root.
- Block `moduleC_local_pipeline` as runner root (`BLOCKED_FORBIDDEN_CODE_ROOT`).
- Remove active `RUNMODE=ISO`; keep only diagnostic reference (`ISO_DIAGNOSTIC_REFERENCE_ONLY`).
- Enforce path scope guard before pipeline and objectives execution.

