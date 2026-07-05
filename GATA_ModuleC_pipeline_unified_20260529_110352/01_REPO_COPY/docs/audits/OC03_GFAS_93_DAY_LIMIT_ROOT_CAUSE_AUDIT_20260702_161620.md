# Auditoria OC03 GFAS 93-Day Limit

## 1. Executive diagnosis

El runtime auditado `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027` uso exactamente `93` fechas GFAS PM2P5FIRE por ano porque el decoder comprometido que produjo ese runtime imponia un tope duro de `93` mensajes PM por archivo anual y cortaba el bucle real de decode al llegar a ese limite.

La concentracion enero-abril no proviene de metadatos pequenos que prueben datos truncados, ni de un resume path de ese runtime, ni de una auditoria posterior que solo resumiera mal. El log del runtime registra `planned_pm_messages=93`, despues `processed_pm=93`, y luego `GFAS decoder planned PM message count reached`, ano por ano.

El problema principal es de codigo del decoder. Despues, otro bloque de codigo, los gates OC-03C y sus tests comprometidos normalizaron el recorte como si `930` fechas y `24180` filas fueran el contrato correcto.

## 2. Primary diagnosis category

`CODE_HARDCAP_93`

## 3. Evidence table: file/function/line/block

| Archivo | Funcion / bloque | Lineas | Evidencia | Conclusión |
| --- | --- | --- | --- | --- |
| `pipeline/moduleC_pipeline_v2.py` en commit `adee1226ec0df7d0d052d0a0b146daba8ce0c0cb` | `_planned_pm_message_count` | `1943-1947` | `return max(1, min(93, planned))` | Tope duro explicito a `93` mensajes PM planificados por archivo anual. |
| `pipeline/moduleC_pipeline_v2.py` en commit `adee1226ec0df7d0d052d0a0b146daba8ce0c0cb` | `_fallback_gfas_pm_rows_from_gribs` | `1868-1875` | fallback fabrica `"message_count": "93"` | Segundo embebido de `93`; no viene de datos crudos. |
| `pipeline/moduleC_pipeline_v2.py` en commit `adee1226ec0df7d0d052d0a0b146daba8ce0c0cb` | `decode_gfas_era5_gdal_proxy` | `2450-2477` | `processed_pm += 1` y `if processed_pm >= planned_pm_messages: break` | El limite se aplica durante el decode real, no solo en reporte. |
| `qa/report_auditoria_v2.txt` del runtime auditado | log de decoder GFAS | `16-85` | Cada ano inicia con `planned_pm_messages=93` y termina en `processed_pm=93` alrededor de abril | Confirmacion operativa directa del hard-cap. |
| `tables/smoke_day_score_nuts3_daily.csv` del runtime auditado | tabla diaria emitida | primera fecha `2015-01-02`, ultima fecha `2024-04-03`, `band_index=93` en la cola | La ventana diaria emitida termina en el dia 93 del ano decodificado. |
| `qa/gfas_era5_decoder_daily_spatial_audit.tsv` del runtime auditado | auditoria diaria | archivo completo | `daily_rows=24180`, `unique_dates=930`, `unique_years=10`, `unique_units=26` | Salida final consistente con `93 x 10 x 26`. |
| `pipeline/moduleC_pipeline_v2.py` en `HEAD` comprometido `b9950ac0a755a01e3f1bd5035f74667761ced7e3` | constantes OC-03C | `256-260` | `OC03C_BASE_SMOKE_EXPECTED_DAILY_ROWS = 24180`, `OC03C_BASE_SMOKE_EXPECTED_UNIQUE_DATES = 930` | El gate posterior esperaba exactamente el runtime truncado. |
| `pipeline/moduleC_pipeline_v2.py` en `HEAD` comprometido `b9950ac0a755a01e3f1bd5035f74667761ced7e3` | `run_base_smoke_contract_for_oc03c` | `3964-4019`, `4032-4038` | compara `daily_rows` con `24180` y `unique_dates` con `930`, luego `single_year_fallback_detected=0` | OC-03C aprobaba el runtime truncado como contrato valido. |
| `tests/test_spatial_collapse_contracts.py` en `HEAD` comprometido | `test_direct_decoder_helpers_expand_coverage_and_preserve_multi_point_variation` | `122-127` | assert de `_planned_pm_message_count(730, 2) == 93` y `_planned_pm_message_count(366, 1) == 93` | La bateria de tests fijaba el cap como correcto. |
| `tests/test_oc03c_portuguese_aq_validation.py` en `HEAD` comprometido | fixture valida de base smoke | `206-216`, `379-389` | `daily_dates ... for offset in range(93)`, `daily_rows=24180`, `unique_dates=930` | Los tests del gate OC-03C validaban explicitamente el recorte. |
| `pipeline/smoke_route_selector.py` | `detect_smoke_sources`, `select_smoke_route` | `187-294`, `297-375` | descubre GFAS/ERA5 y selecciona `v0_gfas_era5_real` | Aqui no nace el `93`; solo enruta al decoder. |
| `pipeline/moduleC_pipeline_v2.py` en worktree actual no comprometido | diff contra `HEAD` | diff local | elimina `min(93, planned)`, elimina fallback `"93"`, elimina expectativas fijas `930/24180` | El worktree actual ya contiene una reparacion local no comprometida; el runtime auditado no pudo haberse generado con este estado. |

## 4. Search terms used

- `93`
- `930`
- `planned_pm_messages`
- `processed_pm`
- `PM2P5FIRE`
- `GFAS_PM2P5FIRE`
- `gfas_era5_decoder`
- `message_count`
- `min(93, planned)`
- `range(93)`
- `24180`
- `smoke_day_score_nuts3_daily.csv`
- `smoke_days_unit_2015_2024.csv`
- `run_base_smoke_contract_for_oc03c`

## 5. Call-chain reconstruction

1. Descubrimiento de fuentes GFAS/ERA5:
   - `pipeline/smoke_route_selector.py::detect_smoke_sources` (`187-294`)
   - detecta `gfas_dir`, cuenta `.grib`, detecta `era5_zip`, elige `effective_data_root`.
2. Seleccion de ruta:
   - `pipeline/smoke_route_selector.py::select_smoke_route` (`297-375`)
   - con GFAS+ERA5 presentes pero `decoder_available=False`, deja la ruta en `BLOCKED_DECODER_REQUIRED`.
3. Arranque del decoder desde `main`:
   - `pipeline/moduleC_pipeline_v2.py::main` (`4534-4538`, `4589-4602`)
   - llama `detect_smoke_sources`, luego `select_smoke_route`, luego `decode_gfas_era5_gdal_proxy(...)` cuando la ruta exige decoder.
4. Descubrimiento de archivos PM por ano:
   - `pipeline/moduleC_pipeline_v2.py::_load_gfas_pm_summary_rows` (`1979-2025` actual; `1881-1894` fallback en `adee122`)
   - lee `_grib_summary.csv` o `_grib_edge_summary.csv`; si faltan, cae a `_fallback_gfas_pm_rows_from_gribs`.
5. Seleccion de archivos GFAS PM2P5FIRE:
   - `_fallback_gfas_pm_rows_from_gribs` busca `GFAS_PM2P5FIRE_*.grib` y deja uno preferido por ano.
6. Enumeracion de mensajes y fechas:
   - `decode_gfas_era5_gdal_proxy` (`2499-2588` actual)
   - construye `planned_pm_messages`, itera `_iter_grib_messages_by_next_grib`, deriva `fallback_date` con `base_date + day_offset`.
7. Punto exacto donde se limita la lista:
   - en el codigo comprometido del runtime, `_planned_pm_message_count` devolvia `min(93, planned)`.
   - luego el loop corta con `if processed_pm >= planned_pm_messages: break`.
8. Donde se incrementa `processed_pm`:
   - `decode_gfas_era5_gdal_proxy` (`2573-2579` actual; `2466-2477` en `adee122`).
9. Donde se escribe `smoke_day_score_nuts3_daily.csv`:
   - `pipeline/moduleC_pipeline_v2.py::smoke_prepare` (`2931-2983`)
   - consume `unit_daily_rows` ya truncadas por el decoder.
10. Donde se escribe `smoke_days_unit_2015_2024.csv`:
    - `pipeline/moduleC_pipeline_v2.py::smoke_prepare` (`2893-2929`)
    - consolida anual por unidad a partir de `annual_by_unit`.
11. Donde se calcula `unique_dates=930`:
    - `pipeline/moduleC_pipeline_v2.py::write_gfas_era5_decoder_daily_spatial_audit` (`1532-1594` actual; en `HEAD` antiguo hacia PASS con `>10`)
    - lee `smoke_day_score_nuts3_daily.csv`; no recorta fechas por si mismo.
12. Donde OC-03C aprueba el recorte:
    - `pipeline/moduleC_pipeline_v2.py::run_base_smoke_contract_for_oc03c`
    - en `HEAD` comprometido comparaba exactamente contra `24180` y `930`.

## 6. Runtime artifact evidence

Runtime inspeccionado:

`D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027`

Artefactos pequenos leidos:

- `qa/inputs_resolved.json`
  - `smoke_route_reason ... days_per_year=2015:93,...,2024:93`
  - `base_smoke_contract_for_oc03c_status = BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`
  - `base_smoke_contract_for_oc03c_daily_rows = 24180`
  - `base_smoke_contract_for_oc03c_unique_dates = 930`
- `qa/report_auditoria_v2.txt`
  - `planned_pm_messages=93` por cada archivo anual 2015-2024
  - `processed_pm=93` y `GFAS decoder planned PM message count reached`
  - progresion temporal solo enero-abril
- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
  - `daily_rows = 24180`
  - `unique_dates = 930`
  - `unique_years = 10`
  - `unique_units = 26`
- `qa/smoke_route_audit.tsv`
  - todos los anos quedan con `gfas_era5_proxy_p60_unit_daily_spatial_direct_year`
- `tables/smoke_day_score_nuts3_daily.csv`
  - arranca en `2015-01-02`
  - termina en `2024-04-03`
  - las ultimas filas llevan `band_index = 93`
- `tables/smoke_days_unit_2015_2024.csv`
  - el metodo anual publicado es `gfas_era5_proxy_p60_unit_daily_spatial_direct_year`
- `qa/portuguese_aq_validation_gate.tsv`
  - `PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR`
- `qa/gfas_era5_vs_portuguese_aq_concordance.tsv`
  - la concordancia se calculo efectivamente sobre el comparador GFAS truncado

## 7. Whether 93 is hard-coded, derived, or artifact-only

`93` es principalmente hard-coded en el codigo comprometido que produjo el runtime auditado:

- `_planned_pm_message_count` imponia `min(93, planned)`.
- `_fallback_gfas_pm_rows_from_gribs` sembraba `"message_count": "93"`.
- el bucle real de decode cortaba cuando `processed_pm >= planned_pm_messages`.

No es solo artefact-only:

- el log operativo del runtime muestra el corte exactamente en `93`.

No es una mera derivacion de resume:

- el runtime auditado es un rebuild completo con artefactos diarios emitidos desde el decoder.

No hay evidencia suficiente para clasificarlo como `DATA_TRUNCATED_JAN_APR`:

- no se abrieron GRIBs grandes ni metadatos GRIB completos;
- pero tampoco hace falta para esta causa, porque el cap de codigo ya explica el comportamiento observado.

## 8. Whether the pipeline approved 930 dates as a final OC-03 contract

Si.

En `HEAD` comprometido:

- `OC03C_BASE_SMOKE_EXPECTED_DAILY_ROWS = 24180`
- `OC03C_BASE_SMOKE_EXPECTED_UNIQUE_DATES = 930`
- `run_base_smoke_contract_for_oc03c` aprobaba `PASS` si esos valores coincidian
- los tests sembraban `range(93)` por ano y `24180/930` como caso valido

Por tanto, el pipeline no solo sufria el cap; tambien lo certificaba como contrato final aceptable para OC-03C.

## 9. Whether Portuguese AQ concordance is invalidated or provisional

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

La conclusion correcta es:

`Portuguese AQ concordance cannot be considered final until GFAS/ERA5 coverage is verified as annual or intentionally redefined as a documented seasonal window.`

El runtime auditado si consumio AQ portuguesa y emitio concordancia, pero lo hizo sobre un comparador GFAS limitado a `93` fechas por ano. Eso vuelve la interpretacion final provisional.

## 10. Minimal correction required

Correccion minima, sin implementarla en esta auditoria:

1. Quitar el tope `min(93, planned)` de `_planned_pm_message_count` para devolver el total PM realmente planificado.
2. Quitar el fallback que fija `"message_count": "93"` en `_fallback_gfas_pm_rows_from_gribs`.
3. Sustituir el contrato OC-03C de `930/24180` por cobertura anual real observada o, si la intencion fuese estacional, por una ventana estacional explicitamente documentada y justificada.
4. Actualizar tests y fixtures que hoy fijan `93`, `930` o `24180` como comportamiento correcto.

## 11. Files that would need edits in a later implementation step

- `pipeline/moduleC_pipeline_v2.py`
- `tests/test_spatial_collapse_contracts.py`
- `tests/test_oc03c_portuguese_aq_validation.py`
- cualquier otro test que siembre `range(93)` o espere `930/24180`

## 12. Files that must not be edited

- los GRIB y ZIP bajo los roots de datos referenciados por el usuario
- los artefactos historicos del runtime auditado salvo nueva documentacion de auditoria
- cualquier archivo de datos brutos usado solo como evidencia de lectura

## 13. Final decision

`FINAL_DECISION = CODE_HARDCAP_93_FOUND`

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

`NEXT_STEP = REMOVE_OR_REPLACE_93_DAY_CAP_WITH_FULL_ANNUAL_OR_SEASONALLY_BALANCED_GFAS_COVERAGE`

## Commit context checked

- `git log --oneline --decorate --all -- pipeline/moduleC_pipeline_v2.py`
  - visible local chain: `b9950ac`, `1e339dd`, `bcecb01`, `adee122`, `14e67f2`, `4ddd05e`, `7e52fb9`, `fec12ab`
- `git log -S 'min(93, planned)' --oneline -- pipeline/moduleC_pipeline_v2.py`
  - devuelve `adee122`, que es el contexto comprometido localmente verificable del hard-cap
- `git diff adee122..HEAD -- pipeline/moduleC_pipeline_v2.py`
  - los SHAs existen localmente
- `git diff bcecb01..HEAD -- pipeline/moduleC_pipeline_v2.py`
  - los SHAs existen localmente
- `git diff 1e339dd..HEAD -- pipeline/moduleC_pipeline_v2.py`
  - los SHAs existen localmente

Nota de contexto:

- el worktree actual ya contiene cambios locales no comprometidos que eliminan el cap y relajan el contrato;
- por eso el runtime de `2026-06-25` debe explicarse contra el historial comprometido y los artefactos producidos, no contra el archivo actual sin commit.
