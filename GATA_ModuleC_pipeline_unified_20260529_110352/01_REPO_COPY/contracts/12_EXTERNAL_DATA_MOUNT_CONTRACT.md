# 12_EXTERNAL_DATA_MOUNT_CONTRACT

## Proposito
Este repositorio GitHub limpio contiene codigo y contratos, **no datos masivos**.
El runtime local debe leer datos desde rutas externas configuradas localmente.

## Variables de entorno requeridas
- `GATA_REPO_ROOT`: raiz del repo limpio.
- `GATA_EXTERNAL_DATOS_MODC`: ruta externa a `Module C\Datos`.
- `GATA_EXTERNAL_INC_NEW`: ruta externa a `Incendios_Nueva version`.
- `GATA_EXTERNAL_OUTPUT_ROOT`: salida externa para resultados runtime.

## Archivos locales no versionados
- `config/local_paths.ps1`
- `config/local_paths.json` (si se usa)

Estos archivos estan excluidos por `.gitignore`.

## Flujo de carga recomendado
1. Crear `config/local_paths.ps1` desde `config/local_paths.example.ps1`.
2. Ejecutar `validation/validate_github_export.ps1`.
3. Ejecutar `validation/validate_external_data_mount.ps1`.
4. Solo si ambos pasan, continuar a fase de gate pre-runtime.

## Reglas de seguridad
- No copiar datos masivos al repo.
- No mover `Module C\Datos`.
- No mover `Incendios_Nueva version`.
- No usar backups como baseline activo.
- No escribir outputs en `data_placeholders`.

## Cambio de rutas en otro entorno
Si cambian las rutas locales, actualizar solo `config/local_paths.ps1`.
No editar codigo para rutas personales si puede resolverse por variables.

## Relacion con catalogos externos
El montaje externo se valida contra:
- `data_placeholders/master_dataset_catalog.csv`
- `data_placeholders/master_inputs_for_pipeline.csv`
- `data_placeholders/master_path_aliases.csv`

## Nota de runtime
Este contrato habilita montaje externo para una fase posterior de runtime controlado.
No implica cierre de runtime por si mismo.
