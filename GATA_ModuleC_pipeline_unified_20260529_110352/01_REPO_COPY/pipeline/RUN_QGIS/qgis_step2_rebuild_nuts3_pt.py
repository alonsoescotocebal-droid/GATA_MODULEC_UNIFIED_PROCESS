import os, sys, json, argparse, datetime, traceback, importlib

KEY_PREF = ["unit_id","UNIT_ID","NUTS_ID","nuts_id","nuts3","unit","id","code","NUTS"]

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

def pick_field(layer, candidates):
    fm = {f.name().lower(): f.name() for f in layer.fields()}
    for c in candidates:
        if c.lower() in fm:
            return fm[c.lower()]
    return None

def load_table_layer(csv_path, name):
    from qgis.core import QgsVectorLayer
    p = csv_path.replace("\\", "/")
    uri = f"file:///{p}?type=csv&delimiter=,&useHeader=yes&detectTypes=yes&geomType=none"
    lyr = QgsVectorLayer(uri, name, "delimitedtext")
    if not lyr.isValid():
        raise RuntimeError(f"No pude cargar tabla CSV: {csv_path}")
    return lyr

def infer_table_key(tab):
    fn = [f.name() for f in tab.fields()]
    for c in KEY_PREF:
        for f in fn:
            if f.lower() == c.lower():
                return f
    return fn[0] if fn else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    args = ap.parse_args()

    gata_root = args.gata_root
    modc_root = os.path.join(gata_root, "Complementariedad de analisis", "Module C")
    out_root  = os.path.join(modc_root, "03_outputs")
    qa_dir    = os.path.join(out_root, "qa")
    qgis_out  = os.path.join(out_root, "qgis")
    wide_dir  = os.path.join(qgis_out, "_tables_wide")
    os.makedirs(qgis_out, exist_ok=True)

    inputs_json = os.path.join(qa_dir, "inputs_resolved.json")
    if not os.path.isfile(inputs_json):
        raise RuntimeError(f"Falta inputs_resolved.json: {inputs_json}")
    with open(inputs_json, "r", encoding="utf-8") as f:
        inputs = json.load(f)

    nuts_path = inputs["paths"]["nuts3"]

    # Wide tables (creadas en step1)
    iech_wide  = os.path.join(wide_dir, "IECH_wide.csv")
    rec_wide   = os.path.join(wide_dir, "REC_wide.csv")
    smoke_wide = os.path.join(wide_dir, "SMOKE_wide.csv")
    pop_wide   = os.path.join(wide_dir, "POP_wide.csv")
    scen_wide  = os.path.join(wide_dir, "SCEN_mean_wide.csv")

    missing = [p for p in [iech_wide, rec_wide, smoke_wide, pop_wide, scen_wide] if not os.path.isfile(p)]
    if missing:
        raise RuntimeError("Faltan wide tables en 03_outputs\\qgis\\_tables_wide (rerun Step1):\n- " + "\n- ".join(missing))

    qgs = qgis_init()
    try:
        import processing
        from qgis.core import QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem

        nuts = QgsVectorLayer(nuts_path, "NUTS_SRC", "ogr")
        if not nuts.isValid():
            raise RuntimeError(f"No pude cargar NUTS: {nuts_path}")

        # 필trado PT + level 3 (NUTS3)
        cntr = pick_field(nuts, ["CNTR_CODE"])
        levl = pick_field(nuts, ["LEVL_CODE"])
        nuts_id = pick_field(nuts, ["NUTS_ID","nuts_id","NUTS","id","code"])
        if not levl or not nuts_id:
            raise RuntimeError("NUTS source no tiene LEVL_CODE o NUTS_ID para filtrar.")

        if cntr:
            expr = f"\"{cntr}\" = 'PT' AND \"{levl}\" = 3"
        else:
            # fallback: NUTS_ID prefix PT
            expr = f"left(\"{nuts_id}\",2) = 'PT' AND \"{levl}\" = 3"

        nuts_pt3 = processing.run("native:extractbyexpression", {
            "INPUT": nuts,
            "EXPRESSION": expr,
            "OUTPUT": "memory:"
        })["OUTPUT"]

        fc = nuts_pt3.featureCount()
        if fc < 20 or fc > 40:
            raise RuntimeError(f"Filtro PT+LEVL3 dio {fc} features (esperado ~26). Revisa expr={expr}")

        # Reproject to EPSG:3763
        target_crs = QgsCoordinateReferenceSystem("EPSG:3763")
        nuts_3763 = processing.run("native:reprojectlayer", {
            "INPUT": nuts_pt3,
            "TARGET_CRS": target_crs,
            "OUTPUT": "memory:"
        })["OUTPUT"]

        # Join base key
        base_key = pick_field(nuts_3763, ["NUTS_ID","nuts_id","id","code"])
        if not base_key:
            raise RuntimeError("No pude inferir key en NUTS3 filtrado.")

        # Load tables
        t_iech  = load_table_layer(iech_wide,  "IECH_wide")
        t_rec   = load_table_layer(rec_wide,   "REC_wide")
        t_smoke = load_table_layer(smoke_wide, "SMOKE_wide")
        t_pop   = load_table_layer(pop_wide,   "POP_wide")
        t_scen  = load_table_layer(scen_wide,  "SCEN_wide")

        def join_clean(base, tab):
            tk = infer_table_key(tab)
            if not tk:
                raise RuntimeError(f"No pude inferir key en tabla {tab.name()}")
            fields_to_copy = [f.name() for f in tab.fields() if f.name() != tk]  # evita unit_id_2..5
            return processing.run("native:joinattributestable", {
                "INPUT": base,
                "FIELD": base_key,
                "INPUT_2": tab,
                "FIELD_2": tk,
                "FIELDS_TO_COPY": fields_to_copy,
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
                "PREFIX": "",
                "OUTPUT": "memory:"
            })["OUTPUT"]

        j = nuts_3763
        for tab in [t_iech, t_rec, t_smoke, t_pop, t_scen]:
            j = join_clean(j, tab)

        # Promote-to-multi
        j2 = processing.run("native:promotetomulti", {"INPUT": j, "OUTPUT": "memory:"})["OUTPUT"]
        try:
            j2.setName("nuts3_iech")
        except Exception:
            pass

        # Overwrite output
        out_gpkg = os.path.join(qgis_out, "nuts3_iech.gpkg")
        if os.path.exists(out_gpkg):
            try:
                os.remove(out_gpkg)
            except Exception:
                raise RuntimeError(f"No pude borrar {out_gpkg} (lock). Cierra QGIS y reintenta.")

        processing.run("native:savefeatures", {"INPUT": j2, "OUTPUT": out_gpkg})

        # Write project (overwrite)
        proj_path = os.path.join(qgis_out, "ModuleC_IECH.qgz")
        proj = QgsProject.instance()
        proj.clear()
        proj.setCrs(target_crs)

        lyr = QgsVectorLayer(out_gpkg, "nuts3_iech", "ogr")
        if not lyr.isValid():
            uri = out_gpkg + "|layername=nuts3_iech"
            lyr = QgsVectorLayer(uri, "nuts3_iech", "ogr")
        if not lyr.isValid():
            raise RuntimeError("GPKG escrito, pero no pude reabrir nuts3_iech.")

        proj.addMapLayer(lyr)
        proj.write(proj_path)

        rep = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "filter_expression": expr,
            "feature_count": int(lyr.featureCount()),
            "crs": lyr.crs().authid(),
            "outputs": {"gpkg": out_gpkg, "project": proj_path}
        }
        with open(os.path.join(qgis_out, "qgis_step2_report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)

        print("OK STEP2: nuts3_iech rebuilt as PT NUTS3")
        print(" -", out_gpkg)
        print(" - features:", lyr.featureCount())
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
