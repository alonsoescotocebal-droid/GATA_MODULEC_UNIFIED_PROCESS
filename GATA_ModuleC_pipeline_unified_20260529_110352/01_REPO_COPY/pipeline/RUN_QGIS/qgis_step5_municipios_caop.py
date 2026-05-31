import os, sys, json, argparse, datetime, traceback, importlib, zipfile, time
from pathlib import Path

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

def as_vsizip(zip_path, inner):
    z = zip_path.replace("\\", "/")
    inner = inner.replace("\\", "/")
    return f"/vsizip/{z}/{inner}"

def pick_best_member(members, keywords):
    def score(name):
        low = name.lower()
        hit = any(k in low for k in keywords)
        return (0 if hit else 1, len(name), name)
    return sorted(members, key=score)[0]

def pick_inner_vector(zip_path):
    with zipfile.ZipFile(zip_path, "r") as z:
        names = [n for n in z.namelist() if not n.endswith("/") and "__MACOSX" not in n]
    gpkg = [n for n in names if n.lower().endswith(".gpkg")]
    shp  = [n for n in names if n.lower().endswith(".shp")]
    if gpkg:
        inner = pick_best_member(gpkg, keywords=["mun", "conc", "concel", "municip"])
        return inner, "gpkg"
    if shp:
        inner = pick_best_member(shp, keywords=["mun", "conc", "concel", "municip"])
        return inner, "shp"
    raise RuntimeError(f"No encuentro .gpkg ni .shp dentro de: {zip_path}")

def ogr_layer_names(ds_path):
    try:
        from osgeo import ogr
        ds = ogr.Open(ds_path)
        if ds is None:
            return []
        return [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
    except Exception:
        return []

def first_layername_in_gpkg(path):
    try:
        from osgeo import ogr
        ds = ogr.Open(path)
        if ds is None or ds.GetLayerCount() < 1:
            return None
        return ds.GetLayer(0).GetName()
    except Exception:
        return None

def load_caop_layer(caop_zip):
    from qgis.core import QgsVectorLayer
    inner, kind = pick_inner_vector(caop_zip)
    vsi = as_vsizip(caop_zip, inner)

    if kind == "gpkg":
        layers = ogr_layer_names(vsi)
        picked = None
        if layers:
            def score(n):
                low = n.lower()
                hit = any(k in low for k in ["mun", "conc", "concel", "municip"])
                return (0 if hit else 1, len(n), n)
            picked = sorted(layers, key=score)[0]
            uri = vsi + f"|layername={picked}"
            lyr = QgsVectorLayer(uri, "CAOP_MUNI", "ogr")
            return lyr, {"zip": caop_zip, "inner": inner, "vsi": vsi, "picked_layer": picked, "layers": layers}

        lyr = QgsVectorLayer(vsi, "CAOP_MUNI", "ogr")
        return lyr, {"zip": caop_zip, "inner": inner, "vsi": vsi, "picked_layer": None, "layers": layers}

    lyr = QgsVectorLayer(vsi, "CAOP_MUNI", "ogr")
    return lyr, {"zip": caop_zip, "inner": inner, "vsi": vsi, "picked_layer": None, "layers": []}

def infer_epsg_from_extent(ext):
    xmin, xmax, ymin, ymax = ext.xMinimum(), ext.xMaximum(), ext.yMinimum(), ext.yMaximum()
    if abs(xmin) <= 30 and abs(xmax) <= 30 and abs(ymin) <= 90 and abs(ymax) <= 90:
        return "EPSG:4326"
    if (0 <= xmin <= 800000) and (0 <= xmax <= 800000) and (3500000 <= ymin <= 5500000) and (3500000 <= ymax <= 5500000):
        return "EPSG:3763"
    return None

def parse_layer_uri(found_value):
    if not found_value:
        return None, None
    parts = found_value.split("|")
    gpkg = parts[0]
    layer = None
    for p in parts[1:]:
        if p.lower().startswith("layername="):
            layer = p.split("=", 1)[1]
            break
    return gpkg, layer

def safe_rm(path, tries=3):
    for _ in range(tries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except Exception:
            time.sleep(0.2)

def rename_reserved_fid(vlayer):
    # FIX: si existe un campo "fid" (case-insensitive), lo renombramos para que NUNCA interfiera con PK del GPKG
    import processing
    names = [f.name() for f in vlayer.fields()]
    lowmap = {n.lower(): n for n in names}
    if "fid" in lowmap:
        old = lowmap["fid"]
        new = "src_fid"
        if new in names:
            new = "src_fid_1"
        vlayer = processing.run("native:renametablefield", {
            "INPUT": vlayer,
            "FIELD": old,
            "NEW_NAME": new,
            "OUTPUT": "memory:"
        })["OUTPUT"]
    if "ogr_fid" in lowmap:
        old = lowmap["ogr_fid"]
        new = "src_ogr_fid"
        if new in [f.name() for f in vlayer.fields()]:
            new = "src_ogr_fid_1"
        vlayer = processing.run("native:renametablefield", {
            "INPUT": vlayer,
            "FIELD": old,
            "NEW_NAME": new,
            "OUTPUT": "memory:"
        })["OUTPUT"]
    return vlayer

def clone_unique_ids(vlayer, name="mem_unique"):
    # Copia a memory layer => IDs internos nuevos y únicos (extra seguro)
    from qgis.core import QgsVectorLayer, QgsFeature, QgsWkbTypes
    geom_str = QgsWkbTypes.displayString(vlayer.wkbType()).replace(" ", "")
    crs_auth = vlayer.crs().authid() if vlayer.crs().isValid() else "EPSG:3763"
    mem = QgsVectorLayer(f"{geom_str}?crs={crs_auth}", name, "memory")
    if not mem.isValid():
        raise RuntimeError("No pude crear memory layer (reindex ids).")
    pr = mem.dataProvider()
    pr.addAttributes(vlayer.fields())
    mem.updateFields()

    batch = []
    for f in vlayer.getFeatures():
        nf = QgsFeature(mem.fields())
        nf.setGeometry(f.geometry())
        nf.setAttributes(f.attributes())
        batch.append(nf)
        if len(batch) >= 500:
            pr.addFeatures(batch)
            batch = []
    if batch:
        pr.addFeatures(batch)

    mem.updateExtents()
    return mem

def write_gpkg_definitive(vlayer, gpkg_final, layer_name):
    # FIX definitivo:
    # 1) escribir a tmp gpkg
    # 2) forzar PK (FID) a un nombre distinto a "fid" (p.ej. qpk)
    # 3) replace atómico al final
    from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext

    gpkg_tmp = gpkg_final.replace(".gpkg", "__tmp.gpkg")
    safe_rm(gpkg_tmp); safe_rm(gpkg_tmp + "-wal"); safe_rm(gpkg_tmp + "-shm")

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    opts.fileEncoding = "UTF-8"
    # 🔑 clave: PK NO se llamará "fid"
    opts.layerOptions = ["FID=qpk"]

    ctx = QgsCoordinateTransformContext()
    err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(vlayer, gpkg_tmp, ctx, opts)
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"QgsVectorFileWriter error {err}: {msg}")

    # replace final (borrar final por si acaso)
    safe_rm(gpkg_final); safe_rm(gpkg_final + "-wal"); safe_rm(gpkg_final + "-shm")
    os.replace(gpkg_tmp, gpkg_final)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    args = ap.parse_args()

    gata_root = args.gata_root
    out_root  = os.path.join(gata_root, "Complementariedad de analisis", "Module C", "03_outputs")
    qa_dir    = os.path.join(out_root, "qa")
    qgis_dir  = os.path.join(out_root, "qgis")
    exports_dir = os.path.join(qgis_dir, "exports_step5_muni")
    deliver_dir = os.path.join(qgis_dir, "deliverables_step5_muni")
    os.makedirs(exports_dir, exist_ok=True)
    os.makedirs(deliver_dir, exist_ok=True)

    inputs_path = os.path.join(qa_dir, "inputs_resolved.json")
    if not os.path.isfile(inputs_path):
        raise RuntimeError(f"Falta inputs_resolved.json: {inputs_path}")
    with open(inputs_path, "r", encoding="utf-8") as f:
        inputs = json.load(f)

    caop_zip = inputs["paths"]["municipios_caop"]
    if not os.path.isfile(caop_zip):
        raise RuntimeError(f"CAOP zip no existe: {caop_zip}")

    # Preferir resolver NUTS3 desde report STEP3 (si existe)
    step3_report = os.path.join(qgis_dir, "qgis_step3_report.json")
    nuts_gpkg = None
    nuts_layername = None
    if os.path.isfile(step3_report):
        with open(step3_report, "r", encoding="utf-8") as f:
            rep3 = json.load(f)
        found = rep3.get("found", {})
        cand = found.get("nuts3_iech_enriched") or found.get("nuts3_iech") or None
        nuts_gpkg, nuts_layername = parse_layer_uri(cand)

    if not nuts_gpkg or not os.path.isfile(nuts_gpkg):
        candidates = [
            os.path.join(qgis_dir, "nuts3_iech_enriched.gpkg"),
            os.path.join(qgis_dir, "nuts3_iech.gpkg"),
            os.path.join(qgis_dir, "nuts3_iech_PT.gpkg"),
        ]
        nuts_gpkg = next((p for p in candidates if os.path.isfile(p)), None)
        nuts_layername = None
    if not nuts_gpkg:
        raise RuntimeError("No encuentro NUTS3 GPKG en 03_outputs\\qgis (STEP2/STEP3).")

    out_gpkg  = os.path.join(qgis_dir, "muni_iech_from_nuts3.gpkg")
    out_layer = "muni_iech_from_nuts3"
    rep_path  = os.path.join(qgis_dir, "qgis_step5_report.json")
    proj_path = os.path.join(qgis_dir, "ModuleC_STEP5_municipios.qgz")
    zip_path  = os.path.join(deliver_dir, "ModuleC_STEP5_MUNICIPIOS_deliverables.zip")

    report = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "INIT",
        "method": "inherit_nuts3_values_via_spatial_join",
        "inputs_resolved": inputs_path,
        "inputs": {
            "municipios_caop_zip": caop_zip,
            "nuts_source_gpkg": nuts_gpkg,
            "nuts_layername": nuts_layername,
            "step3_report_used": step3_report if os.path.isfile(step3_report) else None
        },
        "outputs": {
            "gpkg": out_gpkg,
            "layer": out_layer,
            "project": proj_path,
            "exports": [],
            "zip": zip_path,
            "report": rep_path
        },
        "counts": {}
    }

    qgs = qgis_init()
    try:
        import processing
        from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem, QgsProject

        target_crs = QgsCoordinateReferenceSystem("EPSG:3763")

        # CAOP
        muni_raw, muni_meta = load_caop_layer(caop_zip)
        report["inputs"]["caop_load_meta"] = muni_meta
        if not muni_raw.isValid():
            raise RuntimeError("No pude cargar CAOP municipios desde zip (inputs_resolved).")

        guessed = None
        if not (muni_raw.crs().isValid() and muni_raw.crs().authid()):
            guessed = infer_epsg_from_extent(muni_raw.extent())
            report["inputs"]["guessed_source_crs"] = guessed
            if guessed:
                muni_raw = processing.run("native:assignprojection", {
                    "INPUT": muni_raw,
                    "CRS": QgsCoordinateReferenceSystem(guessed),
                    "OUTPUT": "memory:"
                })["OUTPUT"]

        muni_fix = processing.run("native:fixgeometries", {"INPUT": muni_raw, "OUTPUT": "memory:"})["OUTPUT"]
        muni_3763 = muni_fix
        if muni_fix.crs() != target_crs:
            muni_3763 = processing.run("native:reprojectlayer", {
                "INPUT": muni_fix, "TARGET_CRS": target_crs, "OUTPUT": "memory:"
            })["OUTPUT"]
        muni_3763 = processing.run("native:promotetomulti", {"INPUT": muni_3763, "OUTPUT": "memory:"})["OUTPUT"]
        muni_3763 = clone_unique_ids(muni_3763, "MUNI_UNIQUE")

        # NUTS3
        if not nuts_layername:
            nuts_layername = first_layername_in_gpkg(nuts_gpkg) or "nuts3_iech_enriched"
        report["inputs"]["nuts_layername_final"] = nuts_layername

        nuts = QgsVectorLayer(nuts_gpkg + f"|layername={nuts_layername}", "NUTS3_SRC", "ogr")
        if not nuts.isValid():
            nuts = QgsVectorLayer(nuts_gpkg, "NUTS3_SRC", "ogr")
        if not nuts.isValid():
            raise RuntimeError(f"No pude cargar NUTS3 desde: {nuts_gpkg}")
        if nuts.crs() != target_crs:
            nuts = processing.run("native:reprojectlayer", {
                "INPUT": nuts, "TARGET_CRS": target_crs, "OUTPUT": "memory:"
            })["OUTPUT"]

        # Join espacial (herencia)
        joined = processing.run("native:joinattributesbylocation", {
            "INPUT": muni_3763,
            "JOIN": nuts,
            "PREDICATE": [0],
            "JOIN_FIELDS": [],
            "METHOD": 0,
            "DISCARD_NONMATCHING": False,
            "PREFIX": "N3_",
            "OUTPUT": "memory:"
        })["OUTPUT"]

        # 🔑 FIX 1: renombrar cualquier campo "fid"/"ogr_fid" (para que nunca se use como PK)
        joined = rename_reserved_fid(joined)
        # 🔑 FIX 2: IDs internos únicos
        joined = clone_unique_ids(joined, "JOINED_UNIQUE")

        # mean IECH
        fields = [f.name() for f in joined.fields()]
        year_fields = [f"N3_IECH_{y}" for y in range(2015, 2025) if f"N3_IECH_{y}" in fields]
        if year_fields:
            expr = "(" + " + ".join([f'coalesce("{f}",0)' for f in year_fields]) + f") / {len(year_fields)}"
            joined = processing.run("native:fieldcalculator", {
                "INPUT": joined,
                "FIELD_NAME": "IECH_mean_2015_2024",
                "FIELD_TYPE": 0,
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 6,
                "FORMULA": expr,
                "OUTPUT": "memory:"
            })["OUTPUT"]
            joined = rename_reserved_fid(joined)
            joined = clone_unique_ids(joined, "JOINED_UNIQUE_2")

        # 🔑 FIX 3: escritura definitiva (tmp + PK=qpk + replace)
        write_gpkg_definitive(joined, out_gpkg, out_layer)

        # QGZ
        proj = QgsProject.instance()
        proj.clear()
        proj.setCrs(target_crs)
        muni_disk = QgsVectorLayer(out_gpkg + f"|layername={out_layer}", out_layer, "ogr")
        if muni_disk.isValid():
            proj.addMapLayer(muni_disk)
        nuts_disk = QgsVectorLayer(nuts_gpkg + f"|layername={nuts_layername}", "nuts3_ref", "ogr")
        if nuts_disk.isValid():
            proj.addMapLayer(nuts_disk)
        proj.write(proj_path)

        report["status"] = "WARN"
        report["reason"] = "No hay tablas municipales en 03_outputs/tables (solo unit=NUTS3). Se heredan campos de NUTS3 a municipios por join espacial (intersects, first match)."
        report["counts"]["features"] = int(muni_disk.featureCount()) if muni_disk.isValid() else None
        report["counts"]["crs"] = muni_disk.crs().authid() if muni_disk.isValid() else None
        report["counts"]["fields"] = [f.name() for f in muni_disk.fields()] if muni_disk.isValid() else None

        with open(rep_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(out_gpkg,  arcname=os.path.basename(out_gpkg))
            z.write(proj_path, arcname=os.path.basename(proj_path))
            z.write(rep_path,  arcname=os.path.basename(rep_path))

        print("OK STEP5_MUNICIPIOS (WARN: heredado NUTS3)")
        print(" -", out_gpkg)
        print(" -", proj_path)
        print(" -", rep_path)
        print(" -", zip_path)

    except Exception as e:
        report["status"] = "FAIL"
        report["error"] = str(e)
        report["traceback"] = traceback.format_exc()
        try:
            with open(rep_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print("FAIL (report escrito):", rep_path)
        except Exception:
            pass
        print("FAIL:", e)
        raise

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    main()
