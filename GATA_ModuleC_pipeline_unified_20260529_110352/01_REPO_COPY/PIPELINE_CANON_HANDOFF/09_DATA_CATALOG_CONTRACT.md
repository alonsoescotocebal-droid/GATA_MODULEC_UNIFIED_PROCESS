# 09 Data Catalog Contract

- Los datos físicos no se mueven ni reordenan.
- El pipeline debe leer por catálogo externo en CONTROL_ROOT.
- Referencias externas válidas:
  - master_dataset_catalog.csv
  - master_inputs_for_pipeline.csv
  - master_path_aliases.csv
- zip_manifest_items.csv puede requerir normalización externa adicional si quedan rutas sin resolver.
- Module C\Datos permanece DO_NOT_TOUCH por tamaño/riesgo.
