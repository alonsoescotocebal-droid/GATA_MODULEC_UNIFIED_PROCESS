# Auditoria OC03 GFAS 93-Day Limit

## 1. Diagnostico ejecutivo

Diagnostico principal: `CODE_HARDCAP_93`.

La causa primaria de las `93` fechas GFAS PM2P5FIRE por ano no es un artefacto de resume ni una prueba de datos truncados enero-abril. El limite esta codificado en el decodificador activo:

- [`pipeline/moduleC_pipeline_v2.py`](D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py) funcion `_planned_pm_message_count`, bloque `1957-1961`, devuelve `max(1, min(93, planned))`.
- Ese valor se aplica de forma operativa en `decode_gfas_era5_gdal_proxy`, bloque `2455-2491`, donde el loop corta cuando `processed_pm >= planned_pm_messages`.

El runtime auditado confirma exactamente ese tope:

- `planned_pm_messages=93`
- `processed_pm=93`
- ultima fecha anual alrededor de `YYYY-04-03/04`
- `unique_dates=930`
- `daily_rows=24180 = 930 x 26`

Ademas, el mismo archivo contiene un segundo embebido de `93` en el fallback `_fallback_gfas_pm_rows_from_gribs`, bloque `1863-1892`, que fabrica `message_count="93"` por ano si falta `_grib_summary.csv`.

Conclusiones operativas:

- La categoria primaria correcta es `CODE_HARDCAP_93`.
- El pipeline tambien normalizo ese recorte como contrato valido de OC-03C al esperar exactamente `930` fechas y `24180` filas.
- La concordancia AQ portuguesa queda **provisional**, no final.

## 2. Categoria primaria de diagnostico

`CODE_HARDCAP_93`

## 3. Tabla de evidencia: archivo / funcion / linea-bloque

| Archivo | Funcion / bloque | Lineas | Evidencia | Interpretacion |
| --- | --- | --- | --- | --- |
| `pipeline/moduleC_pipeline_v2.py` | `_planned_pm_message_count` | `1957-1961` | `return max(1, min(93, planned))` | Tope duro explicito a `93` mensajes PM por archivo anual. |
| `pipeline/moduleC_pipeline_v2.py` | `decode_gfas_era5_gdal_proxy` | `2455-2491` | Calcula `planned_pm_messages`; incrementa `processed_pm`; corta con `if processed_pm >= planned_pm_messages: break` | El tope no es decorativo: corta el decode real. |
| `pipeline/moduleC_pipeline_v2.py` | `_fallback_gfas_pm_rows_from_gribs` | `1863-1892` | Fallback sintetiza `message_count: "93"` y `pm_stride_hint: "1"` | Segundo embebido de `93`; refuerza que no viene de datos crudos. |
| `pipeline/moduleC_pipeline_v2.py` | `_load_gfas_pm_rows` | `1895-1941` | Usa `_grib_summary.csv`; si falta o no hay filas PM, cae al fallback anterior | El path alternativo tambien queda sesgado a `93`. |
| `pipeline/moduleC_pipeline_v2.py` | constantes base smoke contract | `256-260` | `OC03C_BASE_SMOKE_EXPECTED_DAILY_ROWS = 24180`, `OC03C_BASE_SMOKE_EXPECTED_UNIQUE_DATES = 930` | El contrato QA posterior considera correcto el recorte `93 x 10`. |
| `pipeline/moduleC_pipeline_v2.py` | `write_gfas_era5_decoder_daily_spatial_audit` | `1524-1575` | Solo exige `> 10` para PASS del audit diario | El audit no valida cobertura anual completa. |
| `pipeline/moduleC_pipeline_v2.py` | `run_base_smoke_contract_for_oc03c` | `3930-4084` | Exige exactamente `24180` filas y `930` fechas para PASS | El pipeline aprueba explicitamente el recorte como contrato final de base smoke. |
| `pipeline/smoke_route_selector.py` | `detect_smoke_sources` | `187-294` | Descubre `gfas_dir`, `gfas_grib_count`, `era5_zip`, `effective_data_root` | Descubrimiento de fuentes; aqui no nace el `93`. |
| `pipeline/smoke_route_selector.py` | `select_smoke_route` | `297-369` | Selecciona `v0_gfas_era5_real` si GFAS+ERA5 existen y decoder esta disponible | Seleccion del route; aqui tampoco nace el `93`. |
| `qa/report_auditoria_v2.txt` runtime auditado | log de decode GFAS 2015-2024 | `16-87` | Cada ano inicia con `planned_pm_messages=93`, progresa `1/31/62/93`, corta en abril | Confirmacion directa del hard-cap en ejecucion real. |
| `qa/inputs_resolved.json` runtime auditado | `meta.smoke_route_reason` | `44` | `days_per_year=2015:93,...,2024:93` | El propio metadata final publica el recorte como resultado. |
| `qa/gfas_era5_decoder_daily_spatial_audit.tsv` runtime auditado | metricas resumidas | `2-9` | `daily_rows=24180`, `unique_dates=930`, `unique_years=10`, `unique_units=26` | Salida final consistente con `93 x 10`. |
| `qa/oc03c_base_smoke_contract_gate.tsv` runtime auditado | gate final | `5-15` | `unique_dates=930 PASS`, `daily_rows=24180 PASS`, `BASE_SMOKE_CONTRACT_FOR_OC03C_PASS` | El gate contractual valida el recorte. |
| `tests/test_spatial_collapse_contracts.py` | `test_direct_decoder_helpers_expand_coverage_and_preserve_multi_point_variation` | `122-127` | Assert de `_planned_pm_message_count(... ) == 93` | Las pruebas consolidan el cap. |
| `tests/test_oc03c_portuguese_aq_validation.py` | `_seed_base_smoke_contract_inputs` y tests de gate | `206-215`, `379-390` | Casos validos sembrados con `930` fechas y `range(93)` por ano; PASS del gate | La bateria de pruebas normaliza `930` como runtime valido. |

## 4. Terminos de busqueda usados

- `93`
- `930`
- `planned_pm_messages`
- `processed_pm`
- `PM2P5FIRE`
- `GFAS_PM2P5FIRE`
- `gfas_era5_decoder`
- `unique_dates`
- `daily_rows`
- `smoke_day_score_nuts3_daily`
- `smoke_days_unit_2015_2024`
- `contract`
- `direct_year`
- `fallback`
- `message_count`
- `gfas_grib_count`

## 5. Reconstruccion del call-chain GFAS v0 direct route

1. Descubrimiento de archivos GFAS/ERA5
   - [`pipeline/smoke_route_selector.py`](D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\smoke_route_selector.py) `detect_smoke_sources` (`187-294`)
   - Descubre `gfas_dir`, cuenta GRIBs, localiza `ERA5*.zip`, elige `effective_data_root`.

2. Seleccion de route
   - [`pipeline/smoke_route_selector.py`](D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\smoke_route_selector.py) `select_smoke_route` (`297-369`)
   - Con GFAS + ERA5 + decoder disponible, selecciona `v0_gfas_era5_real`.

3. Entrada al decoder
   - [`pipeline/moduleC_pipeline_v2.py`](D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py) main flow (`4274-4383`)
   - Llama `decode_gfas_era5_gdal_proxy(...)`.

4. Seleccion de archivos anuales GFAS
   - `decode_gfas_era5_gdal_proxy` (`2358-2684`)
   - Carga filas PM desde `_load_gfas_pm_rows`.
   - Filtra por `preferred_direct_years` en el bloque `2445-2448`.

5. Enumeracion de PM2P5FIRE / mensajes GRIB
   - `_iter_grib_messages_by_next_grib` (`1801-1807...`)
   - `_probe_gfas_pm_message_pattern` (`2162-2178...`) detecta `pm_start_index` y fecha base.

6. Extraccion o carga de la lista de mensajes/dates
   - `_load_gfas_pm_rows` (`1895-1941`) lee `_grib_summary.csv` o `_grib_edge_summary.csv`.
   - Si no existen o no contienen filas PM, cae a `_fallback_gfas_pm_rows_from_gribs` (`1863-1892`).

7. Punto exacto donde se limita la lista
   - `_planned_pm_message_count` (`1957-1961`) impone `min(93, planned)`.
   - `decode_gfas_era5_gdal_proxy` (`2455-2491`) corta el loop al alcanzar ese numero.

8. Donde se incrementa `processed_pm`
   - `decode_gfas_era5_gdal_proxy` (`2480`).

9. Donde se escribe `smoke_day_score_nuts3_daily.csv`
   - `smoke_prepare` (`2838-2864` aprox.; inicio del bloque visible `2839-2844`).

10. Donde se calcula `unique_dates=930`
    - `write_gfas_era5_decoder_daily_spatial_audit` (`1524-1575`), leyendo `smoke_day_score_nuts3_daily.csv`.

11. Donde el pipeline lo acepta como contrato
    - `run_base_smoke_contract_for_oc03c` (`3930-4084`), con constantes `24180/930/10/26/0`.

12. Momento real del recorte
    - El recorte ocurre **durante el decode**, no solo en el audit ni solo en reporting.

## 6. Evidencia de artefactos del runtime

Runtime inspeccionado:

- `D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\03_RUNTIMES\ModuleC_RUNTIME_OC03_OC03C_FULL_REBUILD_20260625_113027`

Evidencia directa:

- `qa/report_auditoria_v2.txt`
  - `2015`: `planned_pm_messages=93`, `processed_pm=93`, ultima fecha `2015-04-04`
  - `2016`: ultima fecha `2016-04-03`
  - `2017`: ultima fecha `2017-04-04`
  - ...
  - `2024`: ultima fecha `2024-04-03`

- `qa/inputs_resolved.json`
  - `smoke_route_selected = v0_gfas_era5_real`
  - `smoke_route_reason = ... days_per_year=2015:93, ... 2024:93`
  - `base_smoke_contract_for_oc03c_unique_dates = 930`

- `qa/gfas_era5_decoder_daily_spatial_audit.tsv`
  - `daily_rows = 24180`
  - `unique_dates = 930`
  - `unique_years = 10`
  - `unique_units = 26`

- `tables/smoke_day_score_nuts3_daily.csv`
  - Primeras fechas visibles: `2015-01-02`, `2015-01-03`, `2015-01-04`
  - Metodo espacial: `MULTI_POINT_UNIT_FOOTPRINT_GFAS`
  - El patron concuerda con la ventana enero-abril.

- `qa/oc03c_base_smoke_contract_gate.tsv`
  - `unique_dates = 930 PASS`
  - `daily_rows = 24180 PASS`
  - `BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`

- `qa/portuguese_aq_validation_gate.tsv`
  - El runtime consumio AQ portuguesa y produjo `PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR`
  - Esa conclusion debe reinterpretarse como provisional porque el comparador GFAS ya venia recortado por codigo.

## 7. Si `93` es hard-coded, derivado o artefact-only

Respuesta: **hard-coded**.

Desglose:

- Hard-coded primario:
  - `_planned_pm_message_count` impone `93`.

- Hard-coded secundario:
  - `_fallback_gfas_pm_rows_from_gribs` fabrica `message_count="93"`.

- No es un mero artefacto de resume:
  - El runtime ejecuta el loop de decode y registra `planned_pm_messages=93` por ano.

- No es evidencia de datos realmente truncados:
  - No se inspeccionaron metadatos GRIB completos.
  - El limite nace antes de cualquier conclusion de cobertura anual real.

## 8. Si el pipeline aprobo `930` fechas como contrato final OC-03

Si.

Prueba:

- [`pipeline/moduleC_pipeline_v2.py`](D:\GATA_MODULEC_UNIFIED_PROCESS\GATA_ModuleC_pipeline_unified_20260529_110352\01_REPO_COPY\pipeline\moduleC_pipeline_v2.py) lineas `256-260` fijan:
  - `24180` filas esperadas
  - `930` fechas unicas esperadas

- `run_base_smoke_contract_for_oc03c` (`3964-3977`, `4012-4019`, `4054-4084`) exige esos valores para `PASS`.

- El runtime auditado efectivamente cierra con `BASE_SMOKE_CONTRACT_FOR_OC03C_PASS`.

Por tanto, el recorte no solo existe en decode: tambien fue convertido en contrato aceptado.

## 9. Estado de la conclusion AQ portuguesa

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

Frase requerida:

`Portuguese AQ concordance cannot be considered final until GFAS/ERA5 coverage is verified as annual or intentionally redefined as a documented seasonal window.`

Interpretacion para este audit:

- No declaro invalidez matematica del archivo AQ.
- Si declaro que la interpretacion final de concordancia queda provisional porque el comparador GFAS fue capado a `93` dias por ano.

## 10. Correccion minima requerida

No implementar aun. Correccion minima requerida:

1. En `_planned_pm_message_count`, eliminar el tope `min(93, planned)` y devolver el total PM planificado real del archivo anual.
2. En `_fallback_gfas_pm_rows_from_gribs`, dejar de sembrar `message_count="93"`.
3. Reemplazar las expectativas contractuales `930` / `24180` por cobertura anual real o, si el objetivo fuese estacional, por una ventana estacional documentada y cientificamente justificada, no por `93` fijo.
4. Actualizar los tests que hoy fijan `93` y `930` como comportamiento correcto.

## 11. Archivos que requeririan edicion en una implementacion posterior

- `pipeline/moduleC_pipeline_v2.py`
- `tests/test_spatial_collapse_contracts.py`
- `tests/test_oc03c_portuguese_aq_validation.py`
- `tests/test_oc03c_blocks_degraded_smoke_runtime.py`
- `tests/test_oc03_v13_recovery_contract.py`
- Cualquier test adicional que siembre `range(93)`, `unique_dates=930`, `daily_rows=24180`

## 12. Archivos que no deben editarse en esta auditoria

- Cualquier GRIB GFAS
- Cualquier ZIP ERA5
- Cualquier salida existente del runtime auditado
- Cualquier tabla AQ portuguesa existente

## 13. Contexto de commit disponible

Contexto disponible por evidencia exportada, no por `git log` ejecutado en este turno:

- Branch reportado en auditorias previas del mismo repo exportado: `main`
- SHA reportado como `git rev-parse HEAD`: `ce7736d893a588ce85b21d725f1288d97c031bb6`
- Baseline esperado en `config/local_paths.ps1`: `ce7736d893a588ce85b21d725f1288d97c031bb6`
- Ventana de diff mencionada en auditoria previa: `44ff1ff903dbcc39ee8b7da289a5ced159a71384..ce7736d893a588ce85b21d725f1288d97c031bb6`

Limitacion:

- En esta copia `01_REPO_COPY` no hubo metadata `.git` utilizable por lectura directa para reconstruir el commit exacto introductor del cap.
- Por tanto, el contexto de commit es **parcial pero disponible**.

## 14. Decision final

`FINAL_DECISION = CODE_HARDCAP_93_FOUND`

`PORTUGUESE_AQ_CONCORDANCE_STATUS = PROVISIONAL_NOT_FINAL`

`NEXT_STEP = REMOVE_OR_REPLACE_93_DAY_CAP_WITH_FULL_ANNUAL_OR_SEASONALLY_BALANCED_GFAS_COVERAGE`

