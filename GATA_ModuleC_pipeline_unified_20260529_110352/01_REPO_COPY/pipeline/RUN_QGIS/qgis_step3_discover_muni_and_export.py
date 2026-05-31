import os, sys, json, argparse, datetime, traceback, importlib, re

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

def safe_to_real_expr(fieldname):
    # QGIS expression
    return f"to_real(replace(\"{fieldname}\", ',', '.'))"

def detect_iech_year_fields(fieldnames):
    out = []
    for fn in fieldnames:
        m = re.match(r'(?i)^iech[_]?(20\d{2})$', fn)
        if m:
            y = int(m.group(1))
            if 2015 <= y <= 2024:
                out.append((y, fn))
    out.sort(key=lambda x: x[0])
    return [fn for _, fn in out]

def build_array_mean_expr(field_list):
    inner = ",".join([f"\"{f}\"" for f in field_list])
    return f"array_mean(array_filter(array({inner}), @element is not null))"

def write_gpkg_layer(vlayer, gpkg_path, layer_name, overwrite_file=True):
    from qgis.core import QgsVectorFileWriter, QgsProject
    if overwrite_file and os.path.exists(gpkg_path):
        os.remove(gpkg_path)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    ret = QgsVectorFileWriter.writeAsVectorFormatV3(
        vlayer,
        gpkg_path,
        QgsProject.instance().transformContext(),
        opts
    )

    if isinstance(ret, tuple):
        err = ret[0]
        msg = ret[1] if len(ret) > 1 else ""
    else:
        err = ret
        msg = ""

    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"QgsVectorFileWriter error={err} msg={msg}")

def make_layout(project, layer, title, out_pdf, out_png, legend_title=None):
    from qgis.core import (
        QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend, QgsLayoutItemScaleBar,
        QgsLayoutItemLabel, QgsUnitTypes, QgsLayoutSize, QgsLayoutPoint, QgsLayoutExporter
    )

    # Limpieza preventiva: evita warning "PNG driver ... update access"
    for p in (out_pdf, out_png):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(title)

    pc = layout.pageCollection()
    page = pc.page(0)
    page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))  # A4 landscape

    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.setLayers([layer])
    map_item.zoomToExtent(layer.extent())
    map_item.attemptMove(QgsLayoutPoint(10, 15, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(277, 165, QgsUnitTypes.LayoutMillimeters))

    lbl = QgsLayoutItemLabel(layout)
    lbl.setText(title)
    layout.addLayoutItem(lbl)
    lbl.attemptMove(QgsLayoutPoint(10, 5, QgsUnitTypes.LayoutMillimeters))

    leg = QgsLayoutItemLegend(layout)
    leg.setTitle(legend_title or "Legend")
    leg.setLinkedMap(map_item)
    layout.addLayoutItem(leg)
    leg.attemptMove(QgsLayoutPoint(220, 25, QgsUnitTypes.LayoutMillimeters))
    leg.attemptResize(QgsLayoutSize(65, 60, QgsUnitTypes.LayoutMillimeters))

    sb = QgsLayoutItemScaleBar(layout)
    sb.setLinkedMap(map_item)
    sb.applyDefaultSize()
    sb.setUnitLabel("m")
    sb.setNumberOfSegments(4)
    sb.setNumberOfSegmentsLeft(0)
    layout.addLayoutItem(sb)
    sb.attemptMove(QgsLayoutPoint(10, 185, QgsUnitTypes.LayoutMillimeters))

    exp = QgsLayoutExporter(layout)

    pdf_settings = QgsLayoutExporter.PdfExportSettings()

    img_settings = QgsLayoutExporter.ImageExportSettings()
    if hasattr(img_settings, "generateWorldFile"):
        img_settings.generateWorldFile = False
    if hasattr(img_settings, "exportMetadata"):
        img_settings.exportMetadata = False

    if exp.exportToPdf(out_pdf, pdf_settings) != QgsLayoutExporter.Success:
        raise RuntimeError(f"Fallo export PDF: {out_pdf}")
    if exp.exportToImage(out_png, img_settings) != QgsLayoutExporter.Success:
        raise RuntimeError(f"Fallo export PNG: {out_png}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    args = ap.parse_args()

    gata_root = args.gata_root
    modc_root = os.path.join(gata_root, "Complementariedad de analisis", "Module C")
    out_root  = os.path.join(modc_root, "03_outputs")
    qgis_out  = os.path.join(out_root, "qgis")
    exports   = os.path.join(qgis_out, "exports_step3")
    os.makedirs(exports, exist_ok=True)

    report = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "gata_root": gata_root,
        "found": {},
        "exports": [],
        "notes": []
    }

    nuts_gpkg = os.path.join(qgis_out, "nuts3_iech.gpkg")
    nuts_uri  = nuts_gpkg + "|layername=nuts3_iech"

    qgs = qgis_init()
    try:
        import processing
        from qgis.core import QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem

        target_crs = QgsCoordinateReferenceSystem("EPSG:3763")
        proj = QgsProject.instance()
        proj.clear()
        proj.setCrs(target_crs)

        nuts = QgsVectorLayer(nuts_uri, "nuts3_iech", "ogr")
        if not nuts.isValid():
            raise RuntimeError("No pude abrir nuts3_iech (uri).")
        report["found"]["nuts3_iech"] = nuts_uri

        # Dump campos (QA)
        fnames = [f.name() for f in nuts.fields()]
        dump_path = os.path.join(qgis_out, "step3_nuts3_fields.txt")
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write("\n".join(fnames))
        report["found"]["nuts3_fields_dump"] = dump_path

        # Enriquecer en memoria
        nuts_work = nuts

        # Mean IECH 2015–2024 si no existe
        if pick_field(nuts_work, ["IECH_mean_2015_2024"]) is None:
            iech_fields = detect_iech_year_fields(fnames)
            if iech_fields:
                mean_expr = build_array_mean_expr(iech_fields)
                nuts_work = processing.run("native:fieldcalculator", {
                    "INPUT": nuts_work,
                    "FIELD_NAME": "IECH_mean_2015_2024",
                    "FIELD_TYPE": 0,
                    "FIELD_LENGTH": 20,
                    "FIELD_PRECISION": 6,
                    "FORMULA": mean_expr,
                    "OUTPUT": "memory:"
                })["OUTPUT"]
                report["found"]["computed_mean_fields_used"] = iech_fields
            else:
                report["notes"].append("NUTS3: no detecté campos IECH_2015..2024; no calculo mean.")
        else:
            report["notes"].append("NUTS3: IECH_mean_2015_2024 ya existe; no recalculo.")

        # Casts escenario a real (si aplica)
        for src, dst in [
            ("SCEN_IECH_S0_mean_2026_2030", "SCEN_S0_mean_2026_2030_real"),
            ("SCEN_IECH_S1_mean_2026_2030", "SCEN_S1_mean_2026_2030_real"),
            ("SCEN_delta_S1_minus_S0",      "SCEN_delta_S1_minus_S0_real")
        ]:
            if pick_field(nuts_work, [src]) and pick_field(nuts_work, [dst]) is None:
                nuts_work = processing.run("native:fieldcalculator", {
                    "INPUT": nuts_work,
                    "FIELD_NAME": dst,
                    "FIELD_TYPE": 0,
                    "FIELD_LENGTH": 20,
                    "FIELD_PRECISION": 6,
                    "FORMULA": safe_to_real_expr(src),
                    "OUTPUT": "memory:"
                })["OUTPUT"]
                report["found"][f"cast_{src}_to"] = dst

        # Escribir GPKG enriched (driver explícito, determinista)
        nuts_enriched_gpkg = os.path.join(qgis_out, "nuts3_iech_enriched.gpkg")
        write_gpkg_layer(nuts_work, nuts_enriched_gpkg, "nuts3_iech_enriched", overwrite_file=True)

        enriched_uri = nuts_enriched_gpkg + "|layername=nuts3_iech_enriched"
        nuts_enriched = QgsVectorLayer(enriched_uri, "nuts3_iech_enriched", "ogr")
        if not nuts_enriched.isValid():
            raise RuntimeError("Escribí nuts3_iech_enriched.gpkg pero no pude reabrir layer.")
        proj.addMapLayer(nuts_enriched)
        report["found"]["nuts3_iech_enriched"] = enriched_uri

        # Exports
        out_pdf1 = os.path.join(exports, "IECH_NUTS3_mean_2015_2024.pdf")
        out_png1 = os.path.join(exports, "IECH_NUTS3_mean_2015_2024.png")
        make_layout(proj, nuts_enriched, "IECH NUTS3 mean 2015–2024", out_pdf1, out_png1, legend_title="IECH mean 2015–2024")
        report["exports"].extend([out_pdf1, out_png1])

        delta_field = pick_field(nuts_enriched, ["SCEN_delta_S1_minus_S0_real","SCEN_delta_S1_minus_S0"])
        if delta_field:
            out_pdf2 = os.path.join(exports, "IECH_NUTS3_delta_S1_minus_S0_2026_2030.pdf")
            out_png2 = os.path.join(exports, "IECH_NUTS3_delta_S1_minus_S0_2026_2030.png")
            make_layout(proj, nuts_enriched, "IECH NUTS3 Δ(S1−S0) mean 2026–2030", out_pdf2, out_png2, legend_title="Δ(S1−S0) 2026–2030")
            report["exports"].extend([out_pdf2, out_png2])
        else:
            report["notes"].append("NUTS3: no encontré campo delta escenario; export 2 omitido.")

        proj_path = os.path.join(qgis_out, "ModuleC_STEP3_exports.qgz")
        proj.write(proj_path)
        report["found"]["project"] = proj_path

        rep_path = os.path.join(qgis_out, "qgis_step3_report.json")
        with open(rep_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        report["found"]["report"] = rep_path

        print("OK STEP3 (v4)")
        for p in report["exports"]:
            print(" -", p)
        print(" - report:", rep_path)
        print(" - project:", proj_path)

    finally:
        qgs.exitQgis()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAIL:", e)
        traceback.print_exc()
        raise
