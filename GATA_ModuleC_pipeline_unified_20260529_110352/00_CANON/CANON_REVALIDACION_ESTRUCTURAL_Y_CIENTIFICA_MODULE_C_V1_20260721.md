# CANON DE REVALIDACIÓN ESTRUCTURAL Y CIENTÍFICA — GATA MODULE C

**Canon ID:** `GATA_MODULEC_REVALIDATION_CANON_V1_20260721`
**Fase:** `UNIFICACIÓN ESTRUCTURAL DEL PIPELINE`
**Estado:** obligatorio antes de cualquier nueva validación científica, smokerun o runtime completo
**Autoridad de modificación:** usuario
**Base Git canónica:** `dbcda0b6f3e00d67a7e4a3701e0f2422f87253e9`

---

# 1. Propósito

El objetivo de esta fase es reconstruir una única cadena reproducible entre:

```text
Git
→ código
→ configuración
→ launcher
→ datos autorizados
→ runtime nuevo
→ artefactos
→ objetivos
→ decisión operativa
→ decisión científica
```

No se presume que los resultados del runtime histórico sean falsos.

Tampoco se presume que sean reproducibles desde el estado canónico actual.

Todo resultado previo queda clasificado como:

```text
HISTORICAL_EVIDENCE_PENDING_CANONICAL_REPRODUCTION
```

Hasta que un runtime completamente nuevo reproduzca directamente cada resultado desde el SHA canónico, ningún objetivo científico puede heredar automáticamente un `PASS`.

---

# 2. Línea base canónica obligatoria

## 2.1 Repositorio remoto

```text
alonsoescotocebal-droid/GATA_MODULEC_UNIFIED_PROCESS
```

## 2.2 Git top-level local

```text
D:\GATA_MODULEC_UNIFIED_PROCESS
```

## 2.3 Git dir

```text
D:\GATA_MODULEC_UNIFIED_PROCESS\.git
```

## 2.4 Rama

```text
codex/wrb-source-route-repair-b9cb373d
```

## 2.5 SHA

```text
dbcda0b6f3e00d67a7e4a3701e0f2422f87253e9
```

## 2.6 Estado Git inicial

```text
git status --short
```

debe producir una salida vacía.

## 2.7 Comandos iniciales obligatorios

Antes de leer, editar, probar o ejecutar:

```powershell
git rev-parse --show-toplevel
git rev-parse --absolute-git-dir
git branch --show-current
git rev-parse HEAD
git status --short
```

Resultados obligatorios:

```text
D:/GATA_MODULEC_UNIFIED_PROCESS
D:/GATA_MODULEC_UNIFIED_PROCESS/.git
codex/wrb-source-route-repair-b9cb373d
dbcda0b6f3e00d67a7e4a3701e0f2422f87253e9
git status vacío
```

Cualquier divergencia debe producir:

```text
BLOCKED_CANONICAL_GIT_BASELINE_MISMATCH
```

No puede corregirse automáticamente mediante reset, checkout, restore, clean o creación de un nuevo repositorio.

---

# 3. Separación obligatoria de dominios

## 3.1 Workspace de Codex

```text
D:\GATA_MODULEC_UNIFIED_PROCESS
```

Es el único workspace válido porque contiene el Git top-level y `.git`.

## 3.2 Contenedor del proyecto

```text
D:\GATA_MODULEC_UNIFIED_PROCESS\
GATA_ModuleC_pipeline_unified_20260529_110352
```

## 3.3 Raíz de código

```text
D:\GATA_MODULEC_UNIFIED_PROCESS\
GATA_ModuleC_pipeline_unified_20260529_110352\
01_REPO_COPY
```

Rol:

```text
código
tests
configuración versionable
documentación técnica versionable
```

No es Git top-level.

No puede recibir:

```text
runtimes
outputs científicos
work temporal
cachés de ejecución
descargas externas
```

## 3.4 Launchers

```text
D:\GATA_MODULEC_UNIFIED_PROCESS\
GATA_ModuleC_pipeline_unified_20260529_110352\
02_LAUNCHERS
```

Debe contener exactamente un launcher oficial activo para el runtime completo.

## 3.5 Runtimes

```text
D:\GATA_MODULEC_UNIFIED_PROCESS\
GATA_ModuleC_pipeline_unified_20260529_110352\
03_RUNTIMES
```

Cada ejecución debe crear:

```text
03_RUNTIMES\<RUNTIME_ID>\
    03_outputs\
    logs\
    work\
    provenance\
```

No se reutiliza ningún runtime anterior.

No se ejecuta con `resume` como sustituto de una corrida completa.

## 3.6 Auditorías

```text
04_AUDITS
```

Solo para dictámenes, inventarios y evidencia documental.

No es fuente científica del pipeline.

## 3.7 Manifiestos

```text
05_MANIFESTS
```

Solo para índices, SHA y registros generales autorizados.

## 3.8 Referencias externas

```text
99_EXTERNAL_DATA_REFERENCE_ONLY
```

Solo referencias y catálogos.

No debe contener copias de los datos masivos ni ser fuente activa del pipeline.

---

# 4. Regla absoluta contra contaminación

## 4.1 Principio fail-closed

Ante cualquier duda de raíz, procedencia, launcher, input u output:

```text
BLOQUEAR
```

Está prohibido:

```text
buscar una ruta parecida
crear una carpeta faltante
usar el primer archivo coincidente
recuperar un output histórico
usar una variable heredada
continuar mediante fallback silencioso
```

## 4.2 Estado fuente único

Un runtime solo puede declararse canónico cuando:

```text
tracked tree = clean
staged tree = clean
untracked executable source = 0
untracked tests = 0
untracked configuration = 0
```

Los outputs creados durante la ejecución deben quedar exclusivamente dentro del runtime nuevo y estar excluidos del árbol fuente por reglas explícitas.

## 4.3 Productores versionados

Antes del runtime completo deben estar versionados y asociados al SHA:

```text
pipeline principal
selector de humo
decodificador GFAS/ERA5
validación portuguesa AQ
cálculo de población
cálculo OC-05
WRB
matriz de screening
escenarios
QA gates
scientific gates
Step7
Step9
launcher oficial
configuración estática
tests ejecutados
```

Está prohibido producir un runtime desde scripts científicos no rastreados.

## 4.4 Huella de productores

Cada runtime debe registrar SHA256 de los productores principales en:

```text
provenance\producer_sha256.tsv
```

Campos mínimos:

```text
relative_path
git_blob_sha
sha256
tracked
modified
role
```

Todos deben quedar:

```text
tracked = 1
modified = 0
```

## 4.5 Entorno Codex

```text
.codex\environments\environment.toml
```

debe permanecer inerte.

No puede:

```text
descubrir rutas
crear launchers
crear runtimes
modificar Git
modificar .git/info/exclude
limpiar archivos
inyectar variables históricas
ejecutar tests
ejecutar el pipeline
emitir decisiones
```

## 4.6 Sandbox y ACL

Queda prohibida cualquier nueva intervención en:

```text
ACL
owner
CodexSandboxUsers
SID sintéticos
firewall
.codex\.sandbox
.codex\.sandbox-bin
environment.toml
```

salvo que aparezca una evidencia nueva, directa y distinta del fallo ya resuelto.

El pipeline nunca debe intentar reparar el sandbox.

---

# 5. Allowlist de datos externos

Solo se permite lectura desde:

```text
D:\Mestrado\GATA_2025_2026\
Prueba_aislada\
ISO_GATA_20260121_130505\
Complementariedad de analisis\
Module C\
Datos
```

```text
D:\Mestrado\GATA_2025_2026\
Prueba_aislada\
ISO_GATA_20260121_130505\
Complementariedad de analisis\
Module C\
Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024
```

```text
D:\Mestrado\GATA_2025_2026\
Prueba_aislada\
ISO_GATA_20260121_130505\
Complementariedad de analisis\
Module C\
Datos_RECOVERY_2015_2024
```

```text
D:\Mestrado\GATA_2025_2026\
Prueba_aislada\
ISO_GATA_20260121_130505\
Incendios_Nueva version
```

Todas son:

```text
READ_ONLY
```

La ruta GFAS/ERA5 válida es:

```text
...\Module C\
Datos\
Datos_RECOVERY_2015_2024_PIPELINE_GRIB
```

No constituye una quinta raíz: es una subcarpeta de `Datos`.

Está prohibido crear o utilizar:

```text
...\Module C\
Datos_RECOVERY_2015_2024_PIPELINE_GRIB
```

como carpeta hermana.

---

# 6. Eliminación de la ambigüedad de raíces

Los nombres siguientes deben tener un significado único:

```text
GIT_TOPLEVEL
PROJECT_CONTAINER_ROOT
PIPELINE_CODE_ROOT
MODULEC_DATA_ROOT
PORTUGUESE_AGENCIES_DATA_ROOT
RECOVERY_2015_2024_ROOT
INCENDIOS_DATA_ROOT
GFAS_ERA5_EFFECTIVE_ROOT
RUNTIME_ROOT
OUTPUT_ROOT
```

El parámetro histórico:

```text
--gata-root
```

no puede continuar representando simultáneamente:

```text
Git top-level
raíz de código
raíz ISO externa
raíz de datos
```

Antes de modificar su contrato se debe auditar:

```text
cada consumidor de gata_root
cada función llamada
cada concatenación de rutas
cada búsqueda recursiva
cada fallback
cada test asociado
```

Mientras se mantenga por compatibilidad, el launcher debe registrar:

```text
valor exacto
significado declarado
funciones que lo consumen
alcance potencial de descubrimiento
inputs finalmente resueltos
```

No puede aprobarse un runtime si `gata_root` permite explorar fuera de la allowlist y el guard no demuestra que cada input resuelto pertenece a una raíz autorizada.

---

# 7. Launcher oficial

Debe crearse exactamente un launcher activo bajo:

```text
02_LAUNCHERS
```

El launcher debe:

1. comprobar Git top-level;
2. comprobar Git dir;
3. comprobar rama;
4. comprobar SHA inicial;
5. comprobar árbol limpio;
6. rechazar fuentes o tests no rastreados;
7. validar las cuatro raíces externas;
8. validar la ruta GFAS/ERA5 anidada;
9. validar la ruta correcta de incendios;
10. crear un runtime nuevo y vacío;
11. rechazar un runtime preexistente;
12. rechazar outputs históricos;
13. limpiar variables heredadas dentro del proceso del launcher;
14. pasar rutas explícitas;
15. registrar el comando completo;
16. registrar variables efectivas;
17. registrar hashes de configuración y productores;
18. ejecutar preflight;
19. permitir smokerun;
20. permitir runtime completo únicamente después del smokerun.

El launcher no debe:

```text
editar código
editar configuración
editar Git
editar sandbox
descubrir roots alternativos
crear datos faltantes
copiar outputs previos
usar resume
emitir GO científico
```

## 7.1 Launchers bloqueados

Deben quedar identificados como históricos y no ejecutables:

```text
tmp_launch_modulec_runtime.ps1
tmp_launch_modulec_runtime_v2.ps1
pipeline\run_pipeline_v2.cmd
cualquier launcher fuera de 02_LAUNCHERS
cualquier launcher con rutas históricas
```

No deben eliminarse sin una clasificación documental previa.

El launcher oficial debe detectar una invocación histórica y abortar con:

```text
BLOCKED_NON_CANONICAL_LAUNCHER
```

---

# 8. Gates estructurales obligatorios

Antes de editar código:

```text
G000_GIT_TOPLEVEL_MATCH
G001_GIT_DIR_MATCH
G002_BRANCH_MATCH
G003_HEAD_MATCH
G004_TRACKED_TREE_CLEAN
G005_UNTRACKED_SOURCE_ZERO
G006_UNTRACKED_TEST_ZERO
G007_ENVIRONMENT_INERT
```

Antes de ejecutar:

```text
P001_PIPELINE_CODE_ROOT_MATCH
P002_EXTERNAL_INPUT_ALLOWLIST
P003_GFAS_EFFECTIVE_ROOT_MATCH
P004_INCENDIOS_ROOT_MATCH
P005_OUTPUT_ROOT_NEW_AND_EMPTY
P006_NO_HISTORICAL_OUTPUT_REUSE
P007_NO_RESUME
```

Launcher:

```text
L001_SINGLE_CANONICAL_LAUNCHER
L002_LAUNCHER_TRACKED
L003_LAUNCHER_HASH_RECORDED
L004_HISTORICAL_LAUNCHERS_BLOCKED
L005_ROOT_SEMANTICS_UNAMBIGUOUS
```

Sandbox:

```text
S001_WORKSPACE_COVERS_GIT_TOPLEVEL
S002_NO_SANDBOX_MUTATION_BY_PIPELINE
```

Procedencia:

```text
R001_COMMAND_CAPTURED
R002_ENVIRONMENT_CAPTURED
R003_PRODUCER_HASHES_CAPTURED
R004_INPUT_ROOTS_CAPTURED
R005_INPUT_FILES_RESOLVED
R006_SOURCE_TREE_CLEAN_AT_START
R007_SOURCE_TREE_CLEAN_AT_END
```

Cualquier fallo produce:

```text
BLOCKED_STRUCTURAL_PROVENANCE
```

No puede degradarse a warning.

---

# 9. Reinicio de la verificación de objetivos

El estado de todos los objetivos debe reiniciarse como:

```text
UNVERIFIED_UNDER_CANONICAL_CLEAN_RUNTIME
```

La evidencia histórica puede usarse para:

```text
definir tests
identificar riesgos
comparar resultados
formular hipótesis
detectar regresiones
```

No puede usarse para:

```text
heredar PASS
omitir una fase
copiar un artefacto
cerrar un objetivo
evitar un runtime nuevo
```

---

# 10. Clasificación previa de objetivos

Antes de editar el pipeline debe construirse:

```text
00_CANON\
MODULE_C_OBJECTIVE_EXECUTION_CONTRACT.tsv
```

Cada objetivo debe incluir:

```text
objective_id
objective_name
original_requirement
required_input
input_currently_available
required_processing
code_producer
expected_artifact
scientific_claim
blocking_level
conditionality
historical_result
canonical_status
```

## 10.1 Objetivos obligatorios de núcleo

Deben recalcularse en el runtime nuevo:

```text
OC-01 base territorial
OC-02 incendios 2015–2024
OC-03 humo o proxy de humo
OC-03C concordancia portuguesa, cuando los datos resueltos la soporten
OC-04 población GHSL
OC-05 indicador de exposición o carga proxy con fórmula declarada
OC-06 recurrencia
OC-08 WRB estricto
OC-10 escenarios S0/S1
OC-11 brief y productos de comunicación
OC-12 cierre técnico reproducible
```

## 10.2 Objetivos que requieren definición semántica antes del runtime

```text
OC-05:
IECH normalizado
o
population_smoke_burden_proxy
o
ambos
```

```text
OC-07:
WUI formal
o
proxy built-up/fuel
```

```text
OC-09:
matriz causal inferencial
o
matriz integrada de screening/asociación
```

```text
Municipio:
estimación atmosférica municipal directa
o
asignación municipal bajo señal regional
```

No pueden quedar implícitos.

## 10.3 Objetivos condicionales

Solo son obligatorios cuando el inventario confirma los inputs necesarios:

```text
WUI formal con COS/CLC
pendiente
precipitación estival
GLM/GBM
validación espacial
Pareto de drivers
riesgo AAQD atribuible a humo
exposición sanitaria
resolución municipal independiente
comparación EFFIS–AGIF
```

La falta de un input debe producir:

```text
CONDITIONAL_OBJECTIVE_NOT_ACTIVATED_BY_AVAILABLE_INPUT
```

No puede presentarse como `PASS`.

Tampoco puede presentarse como defecto del código sin demostrar que el input sí estaba disponible y era procesable.

---

# 11. Secuencia de trabajo

## Fase 0 — Auditoría estructural de solo lectura

No editar.

Generar:

```text
git_baseline.tsv
project_structure_inventory.tsv
tracked_file_inventory.tsv
launcher_inventory.tsv
config_path_inventory.tsv
external_root_inventory.tsv
historical_runtime_inventory.tsv
objective_source_document_inventory.tsv
```

Decisión:

```text
READY_FOR_STRUCTURAL_EDIT
o
BLOCKED_STRUCTURAL_PROVENANCE
```

## Fase 1 — Contrato de objetivos

Reconstruir:

```text
objetivo
input real
procesamiento necesario
productor de código
artefacto esperado
claim permitido
condición de bloqueo
```

No utilizar el runtime histórico como sustitución.

## Fase 2 — Unificación mínima

Corregir únicamente:

```text
launcher oficial
semántica de raíces
configuración estática
configuración de runtime
guards
bloqueo de launchers históricos
.gitignore, después de clasificar
```

No modificar todavía fórmulas científicas salvo que una prueba aislada demuestre que la topología estructural impide ejecutarlas.

## Fase 3 — Pruebas aisladas

Ejecutar:

```text
test Git/path scope
test launcher
test allowlist
test output isolation
test smoke selector
test GFAS/ERA5 effective root
test incendios root
test no historical output reuse
test producer provenance
test objective contract
```

## Fase 4 — Smokerun

Crear un runtime nuevo.

El smokerun debe demostrar la cadena:

```text
launcher
→ configuración
→ datos
→ escritura
→ QA
→ artefactos
```

No demuestra cierre científico.

## Fase 5 — Cotejo del smokerun

Leer directamente:

```text
logs
inputs_resolved
path guards
source provenance
tablas mínimas
warnings
errores
```

Corregir cualquier desviación mediante:

```text
diagnóstico
→ hipótesis causal
→ prueba
→ edición mínima
→ test
→ nuevo smokerun desde cero
```

## Fase 6 — Runtime completo nuevo

Solo después de un smokerun limpio.

Condiciones:

```text
runtime nuevo
sin resume
sin outputs previos
sin rutas históricas
sin fuentes no rastreadas
sin warnings no clasificados
```

## Fase 7 — Auditoría de objetivos

Cada objetivo debe comprobarse mediante lectura directa de:

```text
input resuelto
log de ejecución
tabla principal
auditoría específica
manifest
hash
brief o mapa, cuando aplique
```

No basta con que el archivo exista.

## Fase 8 — Decisiones separadas

Emitir:

```text
OPERATIONAL_DECISION
SCIENTIFIC_DECISION
SEMANTIC_LIMITATIONS
CONDITIONAL_OBJECTIVES
OPEN_CODE_DEFECTS
OPEN_DATA_LIMITATIONS
```

---

# 12. Regla de iteración

Todo fallo debe seguir:

```text
evidencia directa
→ primera causa observable
→ hipótesis causal
→ prueba de hipótesis
→ edición mínima
→ test aislado
→ smokerun nuevo
→ cotejo
→ runtime completo nuevo cuando corresponda
→ lectura directa
```

Está prohibido acumular múltiples correcciones no probadas antes de volver a ejecutar.

Una limitación real de datos debe registrarse como:

```text
DATA_LIMITATION_CONFIRMED
```

Un defecto de código debe registrarse como:

```text
CODE_DEFECT_CONFIRMED
```

Una ambición original incompatible con los datos debe registrarse como:

```text
OBJECTIVE_REFORMULATION_REQUIRED
```

No deben mezclarse.

---

# 13. Criterios de cierre

## 13.1 Cierre estructural

```text
GO_STRUCTURAL_CANON
```

requiere:

```text
Git correcto
SHA correcto
árbol limpio
launcher único
roots explícitos
allowlist cumplida
runtime aislado
procedencia completa
```

## 13.2 Cierre operativo

```text
GO_OPERATIONAL_RUNTIME
```

requiere:

```text
runtime completo nuevo
sin resume
exit code registrado
sin errores
sin warnings no explicados
artefactos completos
manifest y SHA coherentes
```

## 13.3 Cierre científico

```text
GO_SCIENTIFIC_WITH_DECLARED_SCOPE
```

requiere:

```text
objetivos obligatorios reproducidos
fórmulas declaradas
claims compatibles
proxies nombrados como proxies
objetivos condicionales separados
lectura directa de resultados
```

## 13.4 Cierre total

Solo puede declararse:

```text
GO_TOTAL_CANONICAL_MODULE_C
```

cuando:

```text
GO_STRUCTURAL_CANON
+
GO_OPERATIONAL_RUNTIME
+
GO_SCIENTIFIC_WITH_DECLARED_SCOPE
```

estén simultáneamente demostrados.

---

# 14. Prohibiciones absolutas

```text
git reset --hard
git clean
git restore masivo
git checkout destructivo
force push
git init
mover .git
recrear el repositorio
usar 01_REPO_COPY como Git top-level
abrir solo 01_REPO_COPY como workspace
editar ACL
editar owner
editar SID
editar .sandbox
editar .sandbox-bin
reactivar environment.toml
crear rutas inexistentes
usar output histórico
usar runtime histórico como input
usar resume
ejecutar pipeline\run_pipeline_v2.cmd
ejecutar launchers temporales
usar una raíz ISO amplia como descubrimiento no controlado
producir runtime con scripts no rastreados
cerrar por ZIP
cerrar por manifest
cerrar por exit code
cerrar por qa_flag
cerrar por respuesta anterior
```

---

# 15. Declaración canónica obligatoria

```text
El repositorio canónico es D:\GATA_MODULEC_UNIFIED_PROCESS y la raíz
de código es 01_REPO_COPY. El entorno Codex es inerte, los datos
externos son de solo lectura y los runtimes nacen exclusivamente bajo
03_RUNTIMES. Ningún resultado histórico hereda validez canónica.
Cada objetivo debe reproducirse desde el SHA limpio vigente mediante
el launcher oficial, rutas explícitas, procedencia completa y lectura
directa de artefactos. Toda discrepancia bloquea la ejecución; no se
resuelve mediante rutas laterales, fallbacks silenciosos, reutilización
de outputs ni inferencia.
```
