import os, sys, json, csv, argparse, datetime, traceback, importlib

# ---------------------------------------------------------------------
# CSV robustness (PT/ES locale): detect delimiter ; , \t and normalize
# ---------------------------------------------------------------------
KEY_PREF = ["unit_id","UNIT_ID","NUTS_ID","nuts_id","nuts3","unit","id","code","NUTS"]
YEAR_PREF = ["year","ano","anio"]
# value candidates per table type are handled in calls

def sniff_delimiter(path: str, sample_bytes: int = 65536) -> str:
    # Robust heuristic: count delimiters in sample
    with open(path, "rb") as f:
        b = f.read(sample_bytes)
    try:
        s = b.decode("utf-8-sig", errors="replace")
    except Exception:
        s = b.decode(errors="replace")
    counts = {
        ";": s.count(";"),
        ",": s.count(","),
        "\t": s.count("\t"),
    }
    # Choose highest count; default ';' if tie and ';' exists
    best = max(counts, key=lambda k: counts[k])
    if counts[best] == 0:
        return ","  # fallback
    return best

def read_csv_dicts(path: str):
    delim = sniff_delimiter(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter=delim)
        rows = list(r)
        header = r.fieldnames or []
    return header, rows, delim

def write_csv_dicts(path: str, fieldnames, rows, delimiter=","):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        w.writeheader()
        for row in rows:
            w.writerow(row)

def pick_col(header, candidates):
    hl = {c.lower(): c for c in (header or [])}
    for c in candidates:
        if c.lower() in hl:
            return hl[c.lower()]
    return None

def pivot_long_to_wide(csv_in, csv_out, key_pref, year_pref, val_pref, out_prefix):
    header, rows, delim = read_csv_dicts(csv_in)

    key  = pick_col(header, key_pref)
    year = pick_col(header, year_pref)
    val  = pick_col(header, val_pref)

    if not key:
        raise RuntimeError(f"[pivot] KEY no inferible en {os.path.basename(csv_in)}. header={header}")
    if not year:
        raise RuntimeError(f"[pivot] YEAR no inferible en {os.path.basename(csv_in)}. header={header}")

    if not val:
        for c in header:
            cl = c.lower()
            if cl in (key.lower(), year.lower()):
                continue
            if any(tok in cl for tok in ["iech","value","val","score","index","idx","days","pop","rec","mean","smoke"]):
                val = c
                break
    if not val:
        raise RuntimeError(f"[pivot] VALUE no inferible en {os.path.basename(csv_in)}. header={header}")

    data, years = {}, set()
    for row in rows:
        k = (row.get(key) or "").strip()
        y = (row.get(year) or "").strip()
        v = (row.get(val) or "").strip()
        if not k or not y:
            continue
        years.add(y)
        data.setdefault(k, {})[y] = v

    years_sorted = sorted(years)
    out_fields = [key] + [f"{out_prefix}{y}" for y in years_sorted]

    out_rows = []
    for k, yd in data.items():
        o = {key: k}
        for y in years_sorted:
            o[f"{out_prefix}{y}"] = yd.get(y, "")
        out_rows.append(o)

    # Normalize output to comma always (QGIS delimitedtext uses delimiter=,)
    write_csv_dicts(csv_out, out_fields, out_rows, delimiter=",")
    return {"mode":"pivot", "in_delim": delim, "key": key, "year": year, "value": val, "years": years_sorted}

def passthrough_normalize(csv_in, csv_out, key_pref, prefix):
    header, rows, delim = read_csv_dicts(csv_in)
    key = pick_col(header, key_pref)
    if not key:
        raise RuntimeError(f"[pass] KEY no inferible en {os.path.basename(csv_in)}. header={header}")

    out_fields = [key]
    for c in header:
        if c == key:
            continue
        out_fields.append(f"{prefix}{c}")

    out_rows = []
    for row in rows:
        o = {key: (row.get(key) or "").strip()}
        for c in header:
            if c == key:
                continue
            o[f"{prefix}{c}"] = (row.get(c) or "").strip()
        out_rows.append(o)

    write_csv_dicts(csv_out, out_fields, out_rows, delimiter=",")
    return {"mode":"passthrough", "in_delim": delim, "key": key, "prefixed": True}

# ---------------------------------------------------------------------
# QGIS init
# ---------------------------------------------------------------------
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
        raise RuntimeError("QGIS_PREFIX_PATH no está definido (runner debería fijarlo).")
    QgsApplication.setPrefixPath(pp, True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()
    return qgs

def load_table_layer(csv_path, name):
    from qgis.core import QgsVectorLayer
    p = csv_path.replace("\\", "/")
    # tables wide normalized to comma
    uri = f"file:///{p}?type=csv&delimiter=,&useHeader=yes&detectTypes=yes&geomType=none"
    lyr = QgsVectorLayer(uri, name, "delimitedtext")
    if not lyr.isValid():
        raise RuntimeError(f"No pude cargar tabla CSV: {csv_path}")
    return lyr

def pick_field(layer, candidates):
    fm = {f.name().lower(): f.name() for f in layer.fields()}
    for c in candidates:
        if c.lower() in fm:
            return fm[c.lower()]
    return None

def infer_table_key(tab):
    fn = [f.name() for f in tab.fields()]
    # Prefer unit_id first (canónico)
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
    tables_dir= os.path.join(out_root, "tables")
    qa_dir    = os.path.join(out_root, "qa")
    qgis_out  = os.path.join(out_root, "qgis")
    wide_dir  = os.path.join(qgis_out, "_tables_wide")
    os.makedirs(wide_dir, exist_ok=True)
    os.makedirs(qgis_out, exist_ok=True)

    # --- rutas canónicas (anti-ambigüedad) ---
    inputs_json = os.path.join(qa_dir, "inputs_resolved.json")
    if not os.path.isfile(inputs_json):
        raise RuntimeError(f"Falta inputs_resolved.json: {inputs_json}")
    with open(inputs_json, "r", encoding="utf-8") as f:
        inputs = json.load(f)
    nuts_path = inputs["paths"]["nuts3"]

    # --- tablas mínimas ---
    iech_long   = os.path.join(tables_dir, "IECH_unit_2015_2024.csv")
    scen_long   = os.path.join(tables_dir, "IECH_scenarios_unit_2026_2030_mean.csv")
    pop_any     = os.path.join(tables_dir, "pop_unit_2015_2025_2030.csv")
    rec_file    = os.path.join(tables_dir, "recurrence_unit_2015_2024.csv")
    smoke_long  = os.path.join(tables_dir, "smoke_days_unit_2015_2024.csv")

    missing = [p for p in [iech_long, scen_long, pop_any, rec_file, smoke_long] if not os.path.isfile(p)]
    if missing:
        raise RuntimeError("Faltan tablas en 03_outputs\\tables:\n- " + "\n- ".join(missing))

    # --- wide outputs (comma) ---
    iech_wide   = os.path.join(wide_dir, "IECH_wide.csv")
    rec_wide    = os.path.join(wide_dir, "REC_wide.csv")
    smoke_wide  = os.path.join(wide_dir, "SMOKE_wide.csv")
    scen_wide   = os.path.join(wide_dir, "SCEN_mean_wide.csv")
    pop_wide    = os.path.join(wide_dir, "POP_wide.csv")

    meta = {}

    # IECH long -> pivot year
    meta["IECH"] = pivot_long_to_wide(
        iech_long, iech_wide,
        key_pref=KEY_PREF,
        year_pref=YEAR_PREF,
        val_pref=["IECH","iech","value","index","idx"],
        out_prefix="IECH_"
    )

    # SMOKE long -> pivot year
    meta["SMOKE"] = pivot_long_to_wide(
        smoke_long, smoke_wide,
        key_pref=KEY_PREF,
        year_pref=YEAR_PREF,
        val_pref=["smoke_days","days","smoke","value","idx"],
        out_prefix="SMOKE_"
    )

    # RECURRENCE: puede NO tener year (resumen 2015–2024) => passthrough
    header_rec, rows_rec, _ = read_csv_dicts(rec_file)
    year_col = pick_col(header_rec, YEAR_PREF)
    if year_col:
        meta["REC"] = pivot_long_to_wide(
            rec_file, rec_wide,
            key_pref=KEY_PREF,
            year_pref=YEAR_PREF,
            val_pref=["recurrence","rec","value","years","count","idx","total"],
            out_prefix="REC_"
        )
    else:
        meta["REC"] = passthrough_normalize(
            rec_file, rec_wide,
            key_pref=KEY_PREF,
            prefix="REC_"
        )

    # SCENARIOS: intentar pivot por scenario; si ya viene wide => passthrough/normalizar
    try:
        meta["SCEN"] = pivot_long_to_wide(
            scen_long, scen_wide,
            key_pref=KEY_PREF,
            year_pref=["scenario","escenario","scen","s0","s1","S0","S1"],
            val_pref=["IECH","iech","value","index","idx","mean"],
            out_prefix="SCEN_"
        )
    except Exception:
        meta["SCEN"] = passthrough_normalize(
            scen_long, scen_wide,
            key_pref=KEY_PREF,
            prefix="SCEN_"
        )

    # POP: puede venir wide con columnas año o long
    try:
        meta["POP"] = pivot_long_to_wide(
            pop_any, pop_wide,
            key_pref=KEY_PREF,
            year_pref=YEAR_PREF,
            val_pref=["pop","population","value","count"],
            out_prefix="POP_"
        )
    except Exception:
        # normalize wide by prefixing year-like columns
        header_pop, rows_pop, _ = read_csv_dicts(pop_any)
        key = pick_col(header_pop, KEY_PREF)
        if not key:
            raise RuntimeError(f"[POP] KEY no inferible en {os.path.basename(pop_any)}. header={header_pop}")
        years = [c for c in header_pop if c.strip().isdigit()]
        # If no pure-digit columns, fallback to passthrough
        if not years:
            meta["POP"] = passthrough_normalize(pop_any, pop_wide, key_pref=KEY_PREF, prefix="POP_")
        else:
            out_fields = [key] + [f"POP_{y.strip()}" for y in years]
            out_rows = []
            for row in rows_pop:
                o = {key: (row.get(key) or "").strip()}
                for y in years:
                    o[f"POP_{y.strip()}"] = (row.get(y) or "").strip()
                out_rows.append(o)
            write_csv_dicts(pop_wide, out_fields, out_rows, delimiter=",")
            meta["POP"] = {"mode":"wide_year_cols", "key": key, "years": years}

    # --- QGIS build ---
    qgs = qgis_init()
    try:
        import processing
        from qgis.core import QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem

        nuts = QgsVectorLayer(nuts_path, "NUTS3_2024", "ogr")
        if not nuts.isValid():
            raise RuntimeError(f"No pude cargar NUTS3: {nuts_path}")

        # prefer NUTS_ID-like field, but accept others
        nuts_key = pick_field(nuts, ["NUTS_ID","nuts_id","unit_id","UNIT_ID","NUTS","id","code"])
        if not nuts_key:
            raise RuntimeError("No pude inferir campo key en NUTS3 (NUTS_ID/nuts_id/unit_id/NUTS/id/code).")

        target_crs = QgsCoordinateReferenceSystem("EPSG:3763")
        if nuts.crs() != target_crs:
            nuts_3763 = processing.run("native:reprojectlayer", {
                "INPUT": nuts,
                "TARGET_CRS": target_crs,
                "OUTPUT": "memory:"
            })["OUTPUT"]
        else:
            nuts_3763 = nuts

        t_iech  = load_table_layer(iech_wide,  "IECH_wide")
        t_rec   = load_table_layer(rec_wide,   "REC_wide")
        t_smoke = load_table_layer(smoke_wide, "SMOKE_wide")
        t_pop   = load_table_layer(pop_wide,   "POP_wide")
        t_scen  = load_table_layer(scen_wide,  "SCEN_wide")

        def join(base, tab):
            tk = infer_table_key(tab)
            if not tk:
                raise RuntimeError(f"No pude inferir key en tabla {tab.name()}")
            return processing.run("native:joinattributestable", {
                "INPUT": base,
                "FIELD": nuts_key,
                "INPUT_2": tab,
                "FIELD_2": tk,
                "FIELDS_TO_COPY": [],
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
                "PREFIX": "",
                "OUTPUT": "memory:"
            })["OUTPUT"]

        j = nuts_3763
        for tab in [t_iech, t_rec, t_smoke, t_pop, t_scen]:
            j = join(j, tab)

        # Quality: avoid Polygon vs MultiPolygon warnings
        j2 = processing.run("native:promotetomulti", {"INPUT": j, "OUTPUT": "memory:"})["OUTPUT"]
        try:
            j2.setName("nuts3_iech")
        except Exception:
            pass

        out_gpkg = os.path.join(qgis_out, "nuts3_iech.gpkg")
        if os.path.exists(out_gpkg):
            try:
                os.remove(out_gpkg)
            except Exception:
                raise RuntimeError(f"No pude borrar {out_gpkg} (posible lock). Cierra QGIS y reintenta.")

        # CRÍTICO: OUTPUT = path (sin |layername=..., sin OutputLayerDefinition)
        processing.run("native:savefeatures", {"INPUT": j2, "OUTPUT": out_gpkg})

        # Proyecto
        proj_path = os.path.join(qgis_out, "ModuleC_IECH.qgz")
        proj = QgsProject.instance()
        proj.clear()
        proj.setCrs(target_crs)

        # Reabrir layer desde disco (si hay solo 1 layer en gpkg, esto basta)
        lyr = QgsVectorLayer(out_gpkg, "nuts3_iech", "ogr")
        if not lyr.isValid():
            # fallback: try open by URI layername for reading only
            uri = out_gpkg + "|layername=nuts3_iech"
            lyr = QgsVectorLayer(uri, "nuts3_iech", "ogr")
        if not lyr.isValid():
            raise RuntimeError("GPKG escrito, pero no pude reabrir la capa final.")

        proj.addMapLayer(lyr)
        proj.write(proj_path)

        rep = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "gata_root": gata_root,
            "nuts_source": nuts_path,
            "meta_tables": meta,
            "outputs": {
                "gpkg": out_gpkg,
                "project": proj_path,
                "wide_tables_dir": wide_dir
            },
            "counts": {
                "features": int(lyr.featureCount()),
                "fields": [f.name() for f in lyr.fields()],
                "crs": lyr.crs().authid()
            }
        }
        with open(os.path.join(qgis_out, "qgis_build_report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)

        print("OK: QGIS products created")
        print(" -", out_gpkg)
        print(" -", proj_path)
        print(" -", os.path.join(qgis_out, "qgis_build_report.json"))

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAIL:", e)
        traceback.print_exc()
        raise
