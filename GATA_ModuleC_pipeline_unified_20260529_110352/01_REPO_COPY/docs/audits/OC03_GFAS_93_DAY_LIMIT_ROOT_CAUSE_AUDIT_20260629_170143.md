# Auditoria OC03 GFAS 93-Day Limit

## 1. Executive diagnosis

El runtime auditado `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027` uso exactamente `93` fechas GFAS PM2P5FIRE por ano porque el decoder comprometido en Git imponia `93` en codigo y luego los gates/tests de OC-03/OC-03C aceptaban `930` fechas y `24180` filas como cierre valido.

No es una prueba de datos realmente truncados a enero-abril. Tampoco es un artefacto de resume puro: el propio runtime registra ejecucion directa anual 2015-2024 y corte activo en `processed_pm=93`.

La evidencia mas fuerte es doble:

- `HEAD` comprometido `b9950ac0a755a01e3f1bd5035f74667761ced7e3` todavia contiene `return max(1, min(93, planned))` en `pipeline/moduleC_pipeline_v2.py`.
- El runtime auditado registra, por cada archivo anual, `planned_pm_messages=93`, `processed_pm=93` y ultima fecha en abril.

Contexto adicional importante:

- El working tree actual esta sucio y parcialmente reparado: la copia de trabajo ya no devuelve `min(93, planned)` en `pipeline/moduleC_pipeline_v2.py:2035-2048`.
- Esa reparacion no estaba comprometida en `HEAD` y no explica el runtime del 2026-06-25; al contrario, confirma que el arbol actual ya estaba corrigiendo el problema detectado.

## 2. Primary diagnosis category

`CODE_HARDCAP_93`

## 3. Evidence table: file / function / line / block

| Fuente | Funcion / bloque | Lineas / bloque | Contexto commit | Evidencia |
| --- | --- | --- | --- | --- |
| `pipeline/moduleC_pipeline_v2.py` | `_planned_pm_message_count` | `HEAD` `1943-1947` | `b9950ac` | `return max(1, min(93, planned))`. Hard-cap explicito del numero de mensajes PM a procesar por archivo anual. |
| `pipeline/moduleC_pipeline_v2.py` | `_planned_pm_message_count` | `main` `1943-1947` | `adee1226ec0df7d0d052d0a0b146daba8ce0c0cb` | El mismo cap ya existia en `main`. No fue introducido solo por la rama actual. |
| `pipeline/moduleC_pipeline_v2.py` | `_planned_pm_message_count` | `bcecb01` `1948`; `1e339dd` `1961` | `bcecb01ba5c7d9a42e171bc1afd07862ca36de9e`, `1e339dd007e1e426b34d3355ca6dc44c40ac3f80` | El cap persistio en commits posteriores de la rama OC-03C. |
| `pipeline/moduleC_pipeline_v2.py` | `_fallback_gfas_pm_rows_from_gribs` | `HEAD` `1881-1892` | `b9950ac` | Si faltan resumenes utiles, fabrica `minDate=YYYY0101`, `message_count="93"` y `pm_stride_hint="1"` por ano. |
| `pipeline/moduleC_pipeline_v2.py` | `_load_gfas_pm_summary_rows` | `HEAD` `1895-1939` | `b9950ac` | Intenta leer `_grib_summary.csv` o `_grib_edge_summary.csv`; si no puede construir filas PM validas, cae al fallback anterior. |
| `pipeline/moduleC_pipeline_v2.py` | `decode_gfas_era5_gdal_proxy` | `HEAD` `2407-2417`, `2449-2491` | `b9950ac` | Carga `pm_rows`, calcula `planned_pm_messages`, incrementa `processed_pm` y hace `break` cuando `processed_pm >= planned_pm_messages`. El cap corta el decode real, no solo el reporte. |
| `pipeline/moduleC_pipeline_v2.py` | `write_gfas_era5_decoder_daily_spatial_audit` | `HEAD` `1524-1575` | `b9950ac` | Calcula `unique_dates` a partir de `smoke_day_score_nuts3_daily.csv` y solo exige `> 10` para `PASS`; por tanto reporta `930` sin validar cobertura anual completa. |
| `pipeline/moduleC_pipeline_v2.py` | constantes OC-03C base smoke | `HEAD` `256-260` | `b9950ac` | `OC03C_BASE_SMOKE_EXPECTED_DAILY_ROWS = 24180`, `OC03C_BASE_SMOKE_EXPECTED_UNIQUE_DATES = 930`, etc. |
| `pipeline/moduleC_pipeline_v2.py` | `run_base_smoke_contract_for_oc03c` | `HEAD` `3930-4018` | `b9950ac` | Aprueba explicitamente `daily_rows == 24180` y `unique_dates == 930`. |
| `pipeline/scientific_threshold_gate.py` | `evaluate_direct_decoder_contract` | `HEAD` `312-318`, `331` | `b9950ac` | Considera suficiente `unique_years >= 10` y `unique_dates > 900`. `930` pasa. |
| `pipeline/validate_modulec_objectives_canon.py` | `_check_oc03_v13_direct_contract` | `HEAD` `371-376`, `392-394` | `b9950ac` | Vuelve a aceptar `unique_dates > 900` como contrato directo suficiente. |
| `tests/test_spatial_collapse_contracts.py` | `test_direct_decoder_helpers_expand_coverage_and_preserve_multi_point_variation` | `HEAD` `125-127` | `b9950ac` | Los tests afirmaban que `_planned_pm_message_count(730, 2) == 93` y `_planned_pm_message_count(366, 1) == 93`. |
| `tests/test_oc03c_portuguese_aq_validation.py` | `_seed_base_smoke_contract_inputs` | `HEAD` `208-215` | `b9950ac` | Los fixtures validos sembraban `daily_rows=24180`, `unique_dates=930` y `range(93)` por ano como runtime correcto. |
| `tests/test_oc03_v13_recovery_contract.py` | fixture decoder audit | `HEAD` `100-103` | `b9950ac` | El contrato de recovery aceptaba `unique_dates=930`. |
| `tests/test_oc03_v13_scientific_gate_recovery_path.py` | fixtures / assertions | `HEAD` `45`, `83`, `94` | `b9950ac` | El gate cientifico de recovery tambien normalizaba `930` y esperaba `unique_dates=930` en el detalle. |
| `tests/test_oc03_v12_decoder_summary_fallback_contract.py` | expectativa de log | `HEAD` `23-27` | `b9950ac` | Un test esperaba el concepto de ventana acotada: `GFAS decoder bounded direct window reached:`. No causa el cap, pero muestra que estaba mentalmente contractualizado. |
| runtime `qa/report_auditoria_v2.txt` | decode real GFAS 2015-2024 | lineas `16-85` | runtime auditado | Cada ano arranca con `planned_pm_messages=93`, progresa `1/31/62/93`, registra `GFAS decoder planned PM message count reached`, y termina en abril. |
| runtime `qa/inputs_resolved.json` | `meta.smoke_route_reason` | JSON | runtime auditado | Publica `days_per_year=2015:93,...,2024:93` y `base_smoke_contract_for_oc03c_status=BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`. |
| runtime `qa/gfas_era5_decoder_daily_spatial_audit.tsv` | metricas resumidas | TSV | runtime auditado | `daily_rows=24180`, `unique_dates=930`, `unique_years=10`, `unique_units=26`. |
| runtime `qa/oc03c_base_smoke_contract_gate.tsv` | gate base smoke | TSV | runtime auditado | `daily_rows 24180 PASS`, `unique_dates 930 PASS`, `final_state BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`. |
| recovery root small metadata | `_grib_edge_summary.csv` | 1 linea total | input real del runtime | Solo contiene cabecera; no aporta `minDate` ni `message_count`, por lo que empuja al fallback codificado en `93`. |
| original root small metadata | `_grib_summary.csv` | lineas `2` y `10` | input de referencia | Hay filas `pm2p5fire` con `message_count=728` y `message_count=730`. Esto contradice que el producto sea intrinsecamente de `93` mensajes por ano. |

## 4. Search terms used

- `93`
- `930`
- `24180`
- `planned_pm_messages`
- `processed_pm`
- `message_count`
- `PM2P5FIRE`
- `GFAS_PM2P5FIRE`
- `gfas_era5_decoder`
- `unique_dates`
- `daily_rows`
- `range(93)`
- `bounded direct window`
- `contract-sized`
- `smoke_day_score_nuts3_daily.csv`

## 5. Call-chain reconstruction

1. Descubrimiento de fuentes GFAS/ERA5
   - `pipeline/smoke_route_selector.py::detect_smoke_sources` (`187-294`)
   - Descubre `gfas_dir`, `gfas_grib_count`, `era5_zip`, `effective_data_root`.
   - En el runtime auditado selecciono `Datos_RECOVERY_2015_2024_PIPELINE_GRIB` con `gfas_grib_count=12`.

2. Seleccion del route activo
   - `pipeline/smoke_route_selector.py::select_smoke_route` (`297-369`)
   - Si hay GFAS + ERA5 y el decoder esta disponible, selecciona `v0_gfas_era5_real`.

3. Entrada del pipeline principal
   - `pipeline/moduleC_pipeline_v2.py` bloque principal alrededor de `4588-4606`
   - Llama `smoke_prepare(...)` con `decoder_payload`.

4. Descubrimiento de archivos anuales GFAS PM
   - `pipeline/moduleC_pipeline_v2.py::decode_gfas_era5_gdal_proxy`
   - En `2407` carga `pm_rows = _load_gfas_pm_summary_rows(gfas_dir)`.
   - En `2408-2417` deriva `preferred_direct_years` y exige cobertura 2015-2024.

5. Carga de metadata ligera por archivo
   - `pipeline/moduleC_pipeline_v2.py::_load_gfas_pm_summary_rows` (`1895-1939`)
   - Intenta `_grib_summary.csv` y luego `_grib_edge_summary.csv`.
   - Si no puede formar filas PM con `file`, `minDate`, `message_count`, cae al fallback.

6. Seleccion por ano y fallback
   - `pipeline/moduleC_pipeline_v2.py::_fallback_gfas_pm_rows_from_gribs` (`1881-1892` en `HEAD`)
   - Recorre GRIBs preferidos por ano y fabrica `message_count="93"` por archivo anual.

7. Enumeracion de mensajes GRIB
   - `pipeline/moduleC_pipeline_v2.py::_iter_grib_messages_by_next_grib` (`1868`)
   - Stream de mensajes por frontera `GRIB`.

8. Deteccion de indice PM/base date
   - `pipeline/moduleC_pipeline_v2.py::_probe_gfas_pm_message_pattern` (`2249`)
   - Detecta `pm_start_index` y `base_date_iso`.

9. Calculo del limite de mensajes PM
   - `pipeline/moduleC_pipeline_v2.py::_planned_pm_message_count`
   - En `HEAD` comprometido (`1943-1947`) impone `min(93, planned)`.
   - En el working tree actual (`2035-2048`) ya no lo hace, pero ese estado no genero el runtime auditado.

10. Punto exacto donde se corta el decode
    - `pipeline/moduleC_pipeline_v2.py::decode_gfas_era5_gdal_proxy` (`2455`, `2480-2491`)
    - Calcula `planned_pm_messages`, incrementa `processed_pm`, y rompe el loop con `if processed_pm >= planned_pm_messages: break`.

11. Donde se escribe la tabla diaria
    - `pipeline/moduleC_pipeline_v2.py::smoke_prepare` (`2925-2940` y siguientes)
    - Si `route_selected == "v0_gfas_era5_real"` y hay `unit_daily_rows`, escribe `tables/smoke_day_score_nuts3_daily.csv`.

12. Donde se calcula `unique_dates=930`
    - `HEAD` `pipeline/moduleC_pipeline_v2.py::write_gfas_era5_decoder_daily_spatial_audit` (`1533-1568`)
    - Cuenta fechas distintas en `smoke_day_score_nuts3_daily.csv` y las vuelca a `qa/gfas_era5_decoder_daily_spatial_audit.tsv`.
    - El `930` aparece despues del decode real, como reflejo de la tabla ya cortada.

13. Donde el pipeline lo aprueba como contrato final
    - `HEAD` `pipeline/moduleC_pipeline_v2.py::run_base_smoke_contract_for_oc03c` (`3964-4018`)
    - Exige y aprueba exactamente `24180` filas y `930` fechas.
    - Despues, otros gates aguas abajo aceptan `unique_dates > 900`.

## 6. Runtime artifact evidence

Nota de ruta real: el prompt mencionaba `...\03_outputs\qa\...`, pero en el runtime inspeccionado los artefactos efectivos estan directamente bajo `...\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027\qa\...`.

- `qa/report_auditoria_v2.txt`
  - `2015`: `planned_pm_messages=93`, `processed_pm=93`, ultima fecha `2015-04-04`
  - `2016`: ultima fecha `2016-04-03`
  - `2017`: ultima fecha `2017-04-04`
  - `2018`: ultima fecha `2018-04-04`
  - `2019`: ultima fecha `2019-04-04`
  - `2020`: ultima fecha `2020-04-03`
  - `2021`: ultima fecha `2021-04-04`
  - `2022`: ultima fecha `2022-04-04`
  - `2023`: ultima fecha `2023-04-04`
  - `2024`: ultima fecha `2024-04-03`
  - El string real observado es `GFAS decoder planned PM message count reached:`. No encontre ese runtime usando exactamente `bounded direct window reached`.

- `qa/inputs_resolved.json`
  - `smoke_route_selected = v0_gfas_era5_real`
  - `smoke_effective_data_root = ...Datos_RECOVERY_2015_2024_PIPELINE_GRIB`
  - `smoke_route_reason = ... days_per_year=2015:93,...,2024:93`
  - `base_smoke_contract_for_oc03c_status = BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`
  - `portuguese_aq_matched_gfas_aq_day_count = 16155`

- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
  - `daily_rows = 24180`
  - `unique_dates = 930`
  - `unique_years = 10`
  - `unique_units = 26`

- `qa/smoke_route_audit.tsv`
  - Todos los anos `2015-2024` quedan como `gfas_era5_proxy_p60_unit_daily_spatial_direct_year`
  - Esto muestra decode directo anual, pero no prueba cobertura anual completa.

- `qa/oc03c_base_smoke_contract_gate.tsv`
  - `daily_rows 24180 PASS`
  - `unique_dates 930 PASS`
  - `final_state BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`

- `qa/portuguese_aq_validation_gate.tsv`
  - `portuguese_aq_validation_status = PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR`
  - Este estado se emitio sobre un comparador GFAS ya limitado a `93` dias/ano.

- `qa/gfas_era5_vs_portuguese_aq_concordance.tsv`
  - Hay concordancias calculadas, por ejemplo `PM10 SPATIAL_MATCHED matched_day_count = 16155`
  - Esa concordancia existe, pero es metodologicamente provisional mientras el comparador GFAS no sea anual o estacionalmente documentado.

## 7. Whether 93 is hard-coded, derived, or artifact-only

Concluson:

- Primario: `hard-coded`
  - `_planned_pm_message_count` impone `min(93, planned)`.
  - `_fallback_gfas_pm_rows_from_gribs` fabrica `message_count="93"`.

- Secundario: `derived from a bad metadata path, but still code-caused`
  - El recovery root real del runtime solo tenia `_grib_edge_summary.csv` con una sola linea de cabecera.
  - Eso no permitia obtener `minDate` ni `message_count`.
  - El loader cayo al fallback fabricado en `93`.

- No es `artifact-only`
  - El runtime no solo heredo un TSV viejo: el log muestra ejecucion directa de decode por ano y corte activo en `processed_pm=93`.

- No hay base suficiente para `DATA_TRUNCATED_JAN_APR`
  - El recovery root contiene GRIBs anuales `GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib` ... `2024`.
  - El original root tiene un `_grib_summary.csv` pequeno con filas PM2P5FIRE de `message_count=728/730`.
  - Por tanto, no hay evidencia ligera que obligue a concluir que el producto disponible era realmente de `93` dias por ano.

## 8. Whether the pipeline approved 930 dates as a final OC-03 contract

Si.

Lo aprobo en al menos tres niveles:

1. `run_base_smoke_contract_for_oc03c` exigia exactamente `930` fechas y `24180` filas.
2. `scientific_threshold_gate.py` aceptaba `unique_dates > 900`.
3. `validate_modulec_objectives_canon.py` aceptaba `unique_dates > 900`.

Ademas, los tests reforzaban ese mismo contrato.

## 9. Whether Portuguese AQ concordance is invalidated or provisional

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

La formulacion correcta es:

`Portuguese AQ concordance cannot be considered final until GFAS/ERA5 coverage is verified as annual or intentionally redefined as a documented seasonal window.`

No declaro insuficiencia final de AQ portuguesa a partir de este runtime porque el comparador GFAS fue limitado a `93` fechas por ano y solo cubrio enero-abril.

## 10. Minimal correction required

Correccion minima requerida, sin implementarla en esta auditoria:

1. Eliminar `min(93, planned)` de `_planned_pm_message_count` y devolver el conteo PM real del archivo anual.
2. Eliminar el fallback `message_count="93"` de `_fallback_gfas_pm_rows_from_gribs`; si no hay metadata ligera usable, derivar el conteo real con un probe pequeno o fallar con blocker explicito.
3. Sustituir `930/24180` y `unique_dates > 900` por un contrato dinamico de cobertura anual:
   - anos `2015-2024` presentes
   - meses presentes por ano
   - conteo de fechas esperadas por ano
   - consistencia `daily_rows == date_unit_pairs`

## 11. Files that would need edits in a later implementation step

- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\scientific_threshold_gate.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\validate_modulec_objectives_canon.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\tests\test_spatial_collapse_contracts.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\tests\test_oc03c_portuguese_aq_validation.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\tests\test_oc03_v13_recovery_contract.py`
- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\tests\test_oc03_v13_scientific_gate_recovery_path.py`
- Cualquier test adicional que siga fijando `93`, `930`, `24180`, `range(93)` o el concepto de `bounded direct window`.

## 12. Files that must not be edited

- `D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos\...`
- `D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\...`
- `D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024\...`
- Los GRIBs brutos grandes.
- Los runtimes existentes bajo `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\...`, salvo lectura de artefactos pequenos.

## 13. Final decision

`FINAL_DECISION = CODE_HARDCAP_93_FOUND`

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

`NEXT_STEP = REMOVE_OR_REPLACE_93_DAY_CAP_WITH_FULL_ANNUAL_OR_SEASONALLY_BALANCED_GFAS_COVERAGE`

