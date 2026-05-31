import os, sys, json, argparse, datetime, traceback, importlib

def ensure_plugins_path():
    pp = os.environ.get("QGIS_PREFIX_PATH") or ""
    if pp:
        plugins = os.path.join(pp, "python", "plugins")
        if os.path.isdir(plugins) and plugins not in sys.path:
            sys.path.insert(0, plugins)
    sys.modules.pop("processing", None)
    importlib.invalidate_caches()

def qgis_init():
    ensure_plugins_path()
    from qgis.core import QgsApplication
    pp = os.environ.get("QGIS_PREFIX_PATH")
    if not pp:
        raise RuntimeError("QGIS_PREFIX_PATH no está definido.")
    QgsApplication.setPrefixPath(pp, True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()
    return qgs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    args = ap.parse_args()

    gata_root = args.gata_root
    modc_root = os.path.join(gata_root, "Complementariedad de analisis", "Module C")
    qgis_dir  = os.path.join(modc_root, "03_outputs", "qgis")

    in_gpkg = os.path.join(qgis_dir, "nuts3_iech.gpkg")
    if not os.path.isfile(in_gpkg):
        raise RuntimeError(f"Falta input: {in_gpkg}")

    qgs = qgis_init()
    try:
        import processing
        from qgis.core import QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem

        in_uri = f"{in_gpkg}|layername=nuts3_iech"
        lyr = QgsVectorLayer(in_uri, "nuts3_iech", "ogr")
        if not lyr.isValid():
            raise RuntimeError("No pude abrir nuts3_iech desde GPKG.")

        # --- filtro PT NUTS3 ---
        expr = "\"CNTR_CODE\"='PT' AND \"LEVL_CODE\"=3"
        pt = processing.run("native:extractbyexpression", {
            "INPUT": lyr,
            "EXPRESSION": expr,
            "OUTPUT": "memory:"
        })["OUTPUT"]

        # --- limpiar duplicados típicos de join (unit_id_2..unit_id_5) si existen ---
        del_cols = [c for c in ["unit_id_2","unit_id_3","unit_id_4","unit_id_5"] if c in [f.name() for f in pt.fields()]]
        if del_cols:
            pt = processing.run("native:deletecolumn", {
                "INPUT": pt,
                "COLUMN": del_cols,
                "OUTPUT": "memory:"
            })["OUTPUT"]

        out_gpkg = os.path.join(qgis_dir, "nuts3_iech_PT.gpkg")
        if os.path.exists(out_gpkg):
            os.remove(out_gpkg)

        # guardar (ruta directa)
        processing.run("native:savefeatures", {"INPUT": pt, "OUTPUT": out_gpkg})

        # proyecto
        target_crs = QgsCoordinateReferenceSystem("EPSG:3763")
        proj = QgsProject.instance()
        proj.clear()
        proj.setCrs(target_crs)

        out_uri = out_gpkg  # abrir por archivo
        out_lyr = QgsVectorLayer(out_uri, "nuts3_iech_PT", "ogr")
        if not out_lyr.isValid():
            raise RuntimeError("Export OK pero no pude reabrir nuts3_iech_PT.gpkg")

        proj.addMapLayer(out_lyr)
        proj_path = os.path.join(qgis_dir, "ModuleC_IECH_PT.qgz")
        proj.write(proj_path)

        rep = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "filter": expr,
            "inputs": {"gpkg": in_gpkg, "layer": "nuts3_iech"},
            "outputs": {"gpkg": out_gpkg, "project": proj_path},
            "counts": {"features": int(out_lyr.featureCount()), "fields_n": len(out_lyr.fields())}
        }
        with open(os.path.join(qgis_dir, "qgis_build_report_PT.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)

        print("OK: PT subset created")
        print(" -", out_gpkg)
        print(" -", proj_path)

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAIL:", e)
        traceback.print_exc()
        raise
